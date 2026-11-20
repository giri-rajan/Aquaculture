"""Record a benchmark run against a running AquaSentinel server.

For each pollution scenario it resets the demo, plants the plume, lets the boat survey, detect and trace it,
and records what the Benchmarks and Impact pages would show. End-to-end latency is measured here, as the
dashboard sees it: reading timestamp on the server to arrival over /ws/live. Results go to
backend/data/benchmarks/latest.json and latest.md; the dashboard's Benchmarks page shows them as the
last recorded run.

    ./run.sh                                   # in another terminal
    cd backend && .venv/bin/python scripts/run_benchmarks.py [--url http://127.0.0.1:8080] [--speed 16] [--no-visual]

Everything is measured against the simulator's hidden ground truth. These are not field results.
WARNING: this resets the demo's stored data.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import time
from pathlib import Path

import httpx
import websockets

SCENARIOS = ["sewage", "farm_runoff", "industrial", "algal_bloom"]
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "benchmarks"


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(len(v) * q))], 1)


async def listen(ws_url: str, headers: dict, lat_ms: list[float], stop: asyncio.Event) -> None:
    """Collect reading latency (server reading ts -> arrival here) until `stop` is set."""
    async with websockets.connect(ws_url, additional_headers=headers, max_size=None) as ws:
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), 1.0)
            except TimeoutError:
                continue
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            if msg.get("type") == "reading":
                lat_ms.append((time.time() - msg["reading"]["ts"]) * 1000)


async def run_scenario(c: httpx.AsyncClient, ws_url: str, headers: dict, kind: str, speed: float, timeout_s: float) -> dict:
    await c.post("/api/reset")
    await c.post("/api/boat/command", json={"action": "speed", "value": speed})
    # Fixed onboard re-plan rule, so a run measures detection and tracing rather than the Planner's choices
    await c.post("/api/boat/command", json={"action": "replan_mode", "value": "onboard"})
    await c.post("/api/scenarios", json={"kind": kind, "hours_ago": 3})
    lat_ms: list[float] = []
    stop = asyncio.Event()
    task = asyncio.create_task(listen(ws_url, headers, lat_ms, stop))
    t0, loc = time.time(), None
    try:
        while time.time() - t0 < timeout_s:
            await asyncio.sleep(3)
            b = (await c.get("/api/benchmarks")).json()
            loc = next((x for x in b.get("localisation") or [] if x["scenario"] == kind), None)
            if loc:
                await asyncio.sleep(20)          # let the diagnosis and first alert land for the Impact timings
                break
    finally:
        stop.set()
        await task
    b = (await c.get("/api/benchmarks")).json()
    imp = (await c.get("/api/impact")).json()
    print(f"  {kind}: source error {loc and loc['error_m']} m, {len(lat_ms)} readings, {time.time() - t0:.0f} s")
    return {"scenario": kind, "traced": bool(loc), "source_error_m": loc and loc["error_m"],
            "wall_seconds": round(time.time() - t0), "latency_ms": {"n": len(lat_ms), "p50": pct(lat_ms, 0.5), "p95": pct(lat_ms, 0.95)},
            "detector": b.get("detector"), "process_ms": b.get("process_ms"), "readings_per_hour": b.get("readings_per_hour"),
            "impact": {"median": imp.get("median"), "events": imp.get("events"), "speed_scale": imp.get("speed_scale")}}


def summarise(runs: list[dict], visual: dict | None) -> dict:
    tp = sum((r["detector"] or {}).get("tp", 0) for r in runs)
    fp = sum((r["detector"] or {}).get("fp", 0) for r in runs)
    fn = sum((r["detector"] or {}).get("fn", 0) for r in runs)
    lat = [r["latency_ms"]["p95"] for r in runs if r["latency_ms"]["p95"] is not None]
    errs = [r["source_error_m"] for r in runs if r["source_error_m"] is not None]
    rph = [r["readings_per_hour"] for r in runs if r["readings_per_hour"]]
    return {
        "latency_p95_ms_worst": max(lat) if lat else None,
        "detection_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "detection_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "source_error_m_median": round(statistics.median(errs), 1) if errs else None,
        "source_error_m_max": max(errs) if errs else None,
        "scenarios_traced": f"{sum(r['traced'] for r in runs)}/{len(runs)}",
        "visual_label_accuracy": visual and visual.get("label_accuracy"),
        "readings_per_hour": round(statistics.median(rph)) if rph else None,
    }


def markdown(rec: dict) -> str:
    s = rec["summary"]
    rows = [
        ("End-to-end latency (p95, worst scenario)", f"{s['latency_p95_ms_worst']} ms", "under 10 s"),
        ("Anomaly detection precision", s["detection_precision"], "0.85 or higher"),
        ("Anomaly detection recall", s["detection_recall"], "0.85 or higher"),
        ("Source localisation (median / worst)", f"{s['source_error_m_median']} / {s['source_error_m_max']} m", "under 25 m"),
        ("Visual inspector label accuracy", s["visual_label_accuracy"], "0.80 or higher"),
        ("Readings per hour (at demo speed)", s["readings_per_hour"], "10x manual"),
    ]
    out = [f"# Benchmark run {rec['recorded_at']}", "", f"Simulator, boat speed x{rec['speed']}, re-plan rule: onboard. "
           f"Gemini model: {rec['gemini_model']}. Not field results.", "", "| Metric | Measured | Target |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    out += ["", "| Scenario | Traced | Source error (m) | Latency p50 / p95 (ms) | Precision | Recall |", "|---|---|---|---|---|---|"]
    for r in rec["runs"]:
        d = r["detector"] or {}
        out.append(f"| {r['scenario']} | {'yes' if r['traced'] else 'no'} | {r['source_error_m']} | "
                   f"{r['latency_ms']['p50']} / {r['latency_ms']['p95']} | {d.get('precision')} | {d.get('recall')} |")
    return "\n".join(out) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.getenv("AQUASENTINEL_URL", "http://127.0.0.1:8080"))
    ap.add_argument("--speed", type=float, default=16)
    ap.add_argument("--timeout", type=float, default=600, help="seconds allowed per scenario")
    ap.add_argument("--no-visual", action="store_true", help="skip the visual-inspector benchmark (8 Gemini calls)")
    ap.add_argument("--scenarios", nargs="*", default=SCENARIOS, choices=SCENARIOS)
    args = ap.parse_args()

    auth = ("aquasentinel", os.environ["APP_PASSWORD"]) if os.getenv("APP_PASSWORD") else None
    headers = {}
    if auth:
        import base64
        headers["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    ws_url = args.url.replace("http", "ws", 1) + "/ws/live"

    async with httpx.AsyncClient(base_url=args.url, auth=auth, timeout=180) as c:
        status = (await c.get("/api/agents/status")).json()
        print(f"Server {args.url}, Gemini model {status.get('model')}. Running {len(args.scenarios)} scenarios at x{args.speed}.")
        runs = [await run_scenario(c, ws_url, headers, k, args.speed, args.timeout) for k in args.scenarios]
        visual = None
        if not args.no_visual and status.get("configured"):
            print("  visual inspector: 8 frames")
            r = await c.post("/api/benchmarks/visual")
            visual = r.json() if r.status_code == 200 else {"error": r.text[:300]}
        await c.post("/api/reset")                 # leave the demo in its normal state
        await c.post("/api/boat/command", json={"action": "speed", "value": 1})

    rec = {"recorded_at": time.strftime("%Y-%m-%d %H:%M:%S %z"), "server": args.url, "speed": args.speed,
           "gemini_model": status.get("model"), "host": platform.platform(), "simulated": True,
           "summary": summarise(runs, visual), "runs": runs, "visual": visual}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    (OUT_DIR / "latest.md").write_text(markdown(rec))
    print(markdown(rec))


if __name__ == "__main__":
    asyncio.run(main())
