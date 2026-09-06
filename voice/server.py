"""AI Interviewer voice server.

Runs one voice conversation per WebSocket connection using Deepgram for
speech-to-text, Gemini for the conversation turn, and Piper for speech locally.
Turn-taking uses Silero VAD plus Pipecat's LocalSmartTurnAnalyzerV3, which is
the default stop strategy and is what prevents the agent interrupting during
natural thinking pauses.

Flow:
    1. Browser POSTs /session with the generated interview prompt, the Supabase
       session id, and the rubric. Server stores it and returns ok.
    2. Browser opens WS /ws/{session_id}. Pipecat owns that socket for audio.
    3. On disconnect the server reads the conversation out of the LLM context,
       formats it as "Interviewer:" / "Candidate:" lines, and POSTs it to n8n's
       score-session webhook itself.

The browser never handles the transcript. It just waits for Supabase Realtime
to report status = scored, which it already does today.
"""

import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transcriptions.language import Language
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# "gemini-flash-latest" tracks whatever the current flash model is, so this does
# not go stale. Verified against this account's model list; note that
# "gemini-2.0-flash" is NOT available and would 404.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
PIPER_VOICE = os.getenv("PIPER_VOICE", "en_US-lessac-medium")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678/webhook")
PORT = int(os.getenv("PORT", "7860"))

# How long a silence must last before the turn machinery even considers that you
# might be finished. Smart Turn then decides whether you actually are. Raise this
# if it still clips you mid-sentence; see NOTES.md for tuning runs.
VAD_STOP_SECS = float(os.getenv("VAD_STOP_SECS", "0.6"))

# Vocabulary Deepgram would otherwise mangle. Every one of these is a word you
# will actually say in an automation interview and that a general speech model
# has no reason to know. Keyterm prompting is a nova-3 feature; without it
# "n8n" comes back as "N eight N" and "Supabase" as "supabase" or worse.
KEYTERMS = [
    "n8n",
    "Supabase",
    "Shopify",
    "Klaviyo",
    "Gemini",
    "Vapi",
    "ElevenLabs",
    "Deepgram",
    "Pipecat",
    "webhook",
    "webhooks",
    "API",
    "REST API",
    "Postgres",
    "Airtable",
    "HubSpot",
    "GoHighLevel",
    "Zapier",
    "Make.com",
    "Messenger",
    "Claude",
    "OpenAI",
    "LLM",
    "JSON",
    "automation",
    "workflow",
    "abandoned cart",
    "lead generation",
    "Taglish",
]

# session_id -> {"systemPrompt": str, "rubric": dict}
SESSIONS: dict[str, dict] = {}


class SessionRequest(BaseModel):
    """What the browser sends before opening the audio socket."""

    sessionId: str
    systemPrompt: str
    rubric: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Hold one aiohttp session for the life of the server."""
    async with aiohttp.ClientSession() as session:
        app.state.http = session
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Cheap liveness probe. The frontend uses this to say 'server offline'."""
    return {
        "status": "ok",
        "deepgram_key_present": bool(DEEPGRAM_API_KEY),
        "google_key_present": bool(GOOGLE_API_KEY),
        "active_sessions": len(SESSIONS),
    }


@app.post("/session")
async def create_session(req: SessionRequest):
    """Register an interview before its audio socket opens."""
    if not DEEPGRAM_API_KEY:
        return {"ok": False, "error": "DEEPGRAM_API_KEY is not set in .env"}
    if not GOOGLE_API_KEY:
        return {"ok": False, "error": "GOOGLE_API_KEY is not set in .env"}

    SESSIONS[req.sessionId] = {
        "systemPrompt": req.systemPrompt,
        "rubric": req.rubric,
    }
    logger.info(f"session registered: {req.sessionId}")
    return {"ok": True, "sessionId": req.sessionId}


def build_transcript(context: LLMContext) -> str:
    """Turn the conversation into the exact shape the n8n scorer expects.

    The scoring prompt depends on lines reading "Interviewer: ..." and
    "Candidate: ...", so this mapping is load-bearing. Do not change the labels.
    """
    lines: list[str] = []
    for message in context.get_messages():
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")

        if isinstance(content, list):
            content = " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("text")
            )
        if not isinstance(content, str) or not content.strip():
            continue

        if role == "assistant" or role == "model":
            lines.append(f"Interviewer: {content.strip()}")
        elif role == "user":
            lines.append(f"Candidate: {content.strip()}")

    return "\n".join(lines)


async def submit_for_scoring(http: aiohttp.ClientSession, session_id: str, transcript: str, rubric: dict):
    """POST the finished transcript to the existing n8n scoring workflow."""
    if not transcript.strip():
        logger.warning(f"{session_id}: empty transcript, not scoring")
        return

    url = f"{N8N_BASE_URL}/score-session"
    payload = {"sessionId": session_id, "rubric": rubric, "transcript": transcript}

    try:
        async with http.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            body = await resp.text()
            if resp.status == 200:
                logger.info(f"{session_id}: scored ok")
            else:
                logger.error(f"{session_id}: n8n returned {resp.status}: {body[:300]}")
    except Exception as exc:
        logger.error(f"{session_id}: could not reach n8n at {url}: {exc}")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Run one interview. Pipecat owns this socket for audio."""
    await websocket.accept()

    session = SESSIONS.get(session_id)
    if not session:
        logger.error(f"unknown session {session_id}; POST /session first")
        await websocket.close(code=4404)
        return

    logger.info(f"{session_id}: call starting")

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )

    # Deepgram defaults to nova-3-general, which is the right model, but with
    # keyterm=None and smart_format=False. In an automation interview almost
    # every important noun is jargon a general model mangles, so boost them.
    stt = DeepgramSTTService(
        api_key=DEEPGRAM_API_KEY,
        settings=DeepgramSTTService.Settings(
            model="nova-3-general",
            language=Language.EN,
            keyterm=KEYTERMS,
            smart_format=True,
            punctuate=True,
            interim_results=True,
            profanity_filter=False,
        ),
    )

    llm = GoogleLLMService(
        api_key=GOOGLE_API_KEY,
        model=GEMINI_MODEL,
        system_instruction=session["systemPrompt"],
    )

    tts = PiperTTSService(voice_id=PIPER_VOICE)

    context = LLMContext(messages=[])
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=VAD_STOP_SECS)),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )

    task = PipelineTask(pipeline)
    runner = PipelineRunner(handle_sigint=False)

    try:
        await runner.run(task)
    except Exception as exc:
        logger.error(f"{session_id}: pipeline failed: {exc}")
    finally:
        transcript = build_transcript(context)
        logger.info(f"{session_id}: call ended, {len(transcript.splitlines())} transcript lines")
        await submit_for_scoring(app.state.http, session_id, transcript, session["rubric"])
        SESSIONS.pop(session_id, None)


if __name__ == "__main__":
    missing = [
        name
        for name, value in (
            ("DEEPGRAM_API_KEY", DEEPGRAM_API_KEY),
            ("GOOGLE_API_KEY", GOOGLE_API_KEY),
        )
        if not value
    ]
    if missing:
        logger.warning(f"missing from .env: {', '.join(missing)} — calls will fail")

    logger.info(f"voice server on http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
