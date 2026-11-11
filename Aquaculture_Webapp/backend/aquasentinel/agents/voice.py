"""Spoken conversation with the lake's data, over the Gemini Live API (GEMINI_LIVE_MODEL in .env).

The browser opens /ws/voice and streams microphone audio (16 kHz, 16-bit mono PCM) as binary
frames. This module relays it to a Live session and sends back the model's speech (24 kHz PCM,
binary frames) and JSON events: {"type": "user" | "assistant", "text"} transcripts, "tool",
"interrupted", "turn_complete" and "error".

The model answers through the Reporter's read-only tools, the same ones Ask the Lake uses, so a
spoken answer is grounded in the same stored data as a typed one.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging

from google import genai
from google.genai import types

from .. import config
from . import tools

logger = logging.getLogger(__name__)

SESSION_LIMIT_S = 300
MAX_SESSIONS = 3
LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}
TOOLS = {f.__name__: f for f in tools.REPORTER_TOOLS}
_active = 0

INSTRUCTION = """You are the voice of AquaSentinel, an autonomous boat that surveys a lake in India for water pollution.
You are talking with a fish farmer or a water-quality officer, by voice.
Answer from your tools only: get_zone_health for risk to fish, get_parameter_stats and get_recent_readings for levels,
get_hotspots and list_diagnoses for pollution and its cause, get_boat_status for the boat. Never invent readings,
places or limits; if the data does not answer the question, say so.
Speak in short, plain sentences, two or three at a time, with no lists and no jargon. Lead with the answer.
For a farmer, end with what to do now when there is a risk. Say zone names in words (north-west, south).
{sim}
Speak {language} unless the person speaks to you in another language; then answer in theirs."""


def _config(language: str, simulated: bool) -> types.LiveConnectConfig:
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    decls = [types.FunctionDeclaration.from_callable(client=client, callable=f) for f in tools.REPORTER_TOOLS]
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=INSTRUCTION.format(
            language=LANGUAGE_NAMES.get(language, "English"),
            sim="The data comes from a built-in simulator, not a real lake; say so once if asked where it comes from." if simulated else ""),
        tools=[types.Tool(function_declarations=decls)],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


async def _call_tool(fc) -> types.FunctionResponse:
    fn = TOOLS.get(fc.name)
    try:
        if fn is None:
            raise KeyError(f"No tool named {fc.name}")
        out = fn(**dict(fc.args or {}))
        if inspect.isawaitable(out):
            out = await out
    except Exception as e:                      # the model is told the tool failed and can say so
        out = {"error": f"{type(e).__name__}: {e}"[:300]}
    return types.FunctionResponse(id=fc.id, name=fc.name, response=out if isinstance(out, dict) else {"result": out})


async def run_session(ws, language: str, simulated: bool) -> None:
    """Relay one browser socket to one Live session until either side stops or the time limit passes."""
    global _active
    if _active >= MAX_SESSIONS:
        await ws.send_json({"type": "error", "message": "Too many voice sessions are open. Try again in a minute."})
        return
    _active += 1
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        async with client.aio.live.connect(model=config.GEMINI_LIVE_MODEL, config=_config(language, simulated)) as session:
            await ws.send_json({"type": "ready", "model": config.GEMINI_LIVE_MODEL})

            async def from_browser():
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        return
                    if msg.get("bytes"):
                        await session.send_realtime_input(audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000"))
                    elif msg.get("text"):
                        try:
                            j = json.loads(msg["text"])
                        except ValueError:
                            continue
                        if j.get("type") == "stop":
                            return
                        if j.get("type") == "text" and str(j.get("text", "")).strip():
                            await session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part.from_text(text=str(j["text"])[:600])]), turn_complete=True)

            async def from_model():
                while True:                      # receive() ends after each model turn; keep listening for the next
                    got = False
                    async for m in session.receive():
                        got = True
                        sc = m.server_content
                        if sc:
                            if sc.model_turn:
                                for part in sc.model_turn.parts or []:
                                    if part.inline_data and part.inline_data.data:
                                        await ws.send_bytes(part.inline_data.data)
                            if sc.input_transcription and sc.input_transcription.text:
                                await ws.send_json({"type": "user", "text": sc.input_transcription.text})
                            if sc.output_transcription and sc.output_transcription.text:
                                await ws.send_json({"type": "assistant", "text": sc.output_transcription.text})
                            if sc.interrupted:
                                await ws.send_json({"type": "interrupted"})
                            if sc.turn_complete:
                                await ws.send_json({"type": "turn_complete"})
                        if m.tool_call and m.tool_call.function_calls:
                            for fc in m.tool_call.function_calls:
                                await ws.send_json({"type": "tool", "name": fc.name})
                            await session.send_tool_response(function_responses=[await _call_tool(fc) for fc in m.tool_call.function_calls])
                    if not got:
                        return                   # the session closed

            jobs = [asyncio.create_task(from_browser()), asyncio.create_task(from_model())]
            done, pending = await asyncio.wait(jobs, timeout=SESSION_LIMIT_S, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if not done:
                await ws.send_json({"type": "error", "message": "Voice session time limit reached. Start again to continue.", "code": "limit"})
            for t in done:
                if t.exception():
                    raise t.exception()
    finally:
        _active -= 1
