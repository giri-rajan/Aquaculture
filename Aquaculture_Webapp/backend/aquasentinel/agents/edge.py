"""The first alert: two sentences written the moment an anomaly opens, before the plume is traced
and before the Gemini diagnosis.

It is written by a small Gemma model (GEMMA_MODEL in .env), the kind of model that can run on the
boat itself. Today the call goes to the Gemini API with the same key; running it on the boat is the
next step. Gemma gets a plain prompt: no tools, no system instruction and no JSON mode, so the same
prompt works on an on-device runtime.

With GEMMA_MODEL unset, or when the call fails, a fixed rule writes the alert instead. The dashboard
labels which of the two wrote it.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .. import config, cpcb

logger = logging.getLogger(__name__)

TIMEOUT_S = 25
SLOW_TIMEOUT_S = 100
LANGUAGE_NAMES = {"en": "English", "ta": "Tamil, in Tamil script", "hi": "Hindi, in Devanagari script"}
_client = None


def _facts(anomaly: dict, zone_health: dict | None) -> dict:
    """What the first alert may rely on: which sensors moved, which way, and the zone's fish-health status."""
    peak, base = anomaly.get("peak") or {}, anomaly.get("baseline") or {}
    changes = []
    for p in anomaly.get("params") or []:
        v, b = peak.get(p), base.get(p)
        changes.append({"param": p, "label": config.PARAM_META[p]["label"],
                        "direction": None if v is None or b is None else "up" if v > b else "down",
                        "limit": cpcb.status(p, v)})
    health = zone_health.get("health_status") if zone_health and zone_health.get("available") else None
    return {"zone": anomaly.get("zone"), "changes": changes, "fish_health": health}


def rule_alert(anomaly: dict, zone_health: dict | None) -> dict:
    """Fixed wording, no model. English here; the dashboard rebuilds it in the viewer's language from `facts`."""
    f = _facts(anomaly, zone_health)
    names = ", ".join(c["label"] for c in f["changes"]) or "water quality"
    return {"by": "rule", "model": None, "language": "en", "ts": time.time(), "facts": f,
            "title": f"Water change in zone {f['zone']}",
            "body": f"{names} moved away from normal in zone {f['zone']}. Check your fish and keep aerators ready; "
                    "the boat is tracing the source and a full diagnosis will follow."}


def _prompt(f: dict, language: str) -> str:
    lines = [f"- {c['label']}: " + ("changed" if c["direction"] is None else "higher than normal" if c["direction"] == "up" else "lower than normal")
             + (" (past the official limit)" if c["limit"] == "breach" else "") for c in f["changes"]]
    return (
        "You are a small model on a water-monitoring boat. The boat's sensors have just found a sudden change in a lake.\n"
        f"Zone: {f['zone']}\n"
        "Sensors that changed:\n" + "\n".join(lines) + "\n"
        f"Fish-health model for this zone: {f['fish_health'] or 'not available yet'}\n\n"
        "Write a first alert for a fish farmer who uses this water.\n"
        "Rules: a short title, then exactly two short sentences. Sentence one: what changed and in which zone. "
        "Sentence two: what to do now (watch the fish, keep aerators ready, feed less, do not pump lake water into ponds) "
        "and that the boat is tracing the source and a full diagnosis will follow. "
        "Do not name a cause. Do not give numbers. Use everyday words.\n"
        f"Write in {LANGUAGE_NAMES.get(language, 'English')}.\n"
        "Answer in exactly this form and nothing else:\n"
        "TITLE: <title>\n"
        "BODY: <two sentences>"
    )


def _parse(text: str) -> tuple[str, str]:
    title, body = "", ""
    for line in text.strip().splitlines():
        s = line.strip().lstrip("*# ").strip()
        if s.upper().startswith("TITLE:"):
            title = s[6:].strip(" *")
        elif s.upper().startswith("BODY:"):
            body = s[5:].strip(" *")
        elif body and s:
            body += " " + s
    if not title or not body:                      # the model ignored the form: first line is the title
        parts = [p.strip(" *#") for p in text.strip().splitlines() if p.strip()]
        if len(parts) < 2:
            raise ValueError("The model's reply had no title and body")
        title, body = parts[0], " ".join(parts[1:])
    return title[:120], body[:600]


async def quick_alert(anomaly: dict, zone_health: dict | None, language: str = "en") -> dict:
    """Returns {"by": "gemma" | "rule", "model", "title", "body", "language", "ts", "facts"}. Raises on API errors."""
    if not config.GEMMA_READY:
        return rule_alert(anomaly, zone_health)
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    f = _facts(anomaly, zone_health)
    prompt = _prompt(f, language)
    try:
        # A first alert has to be quick, so the model is asked not to deliberate (about 2 s instead of a minute)
        from google.genai import types
        fast = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"))
        res = await asyncio.wait_for(_client.aio.models.generate_content(model=config.GEMMA_MODEL, contents=prompt, config=fast), TIMEOUT_S)
    except asyncio.TimeoutError:
        raise
    except Exception as e:                         # this model does not take the setting: ask plainly and wait longer
        logger.info("Gemma fast mode unavailable (%s); retrying without it", str(e)[:100])
        res = await asyncio.wait_for(_client.aio.models.generate_content(model=config.GEMMA_MODEL, contents=prompt), SLOW_TIMEOUT_S)
    title, body = _parse(res.text or "")
    return {"by": "gemma", "model": config.GEMMA_MODEL, "language": language, "ts": time.time(), "facts": f, "title": title, "body": body}
