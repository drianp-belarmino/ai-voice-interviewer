# Voice pipeline notes

## Task 1: environment

**Python:** 3.14.3 (system install, venv at `voice/venv`)
**Install succeeded on first try:** yes
**Command:** `pip install "pipecat-ai[deepgram,google,piper]"`

The plan flagged Python 3.14 as a risk because ML wheels often lag new releases.
It was not a problem. Every dependency resolved to a `cp314` wheel; only
`docopt` needed building, and that is pure Python.

**Installed:** pipecat-ai 1.8.1, deepgram-sdk 7.8.1, piper-tts 1.8.0,
google-genai 2.22.0, onnxruntime 1.24.4.

**Notable: no PyTorch.** VAD and Smart Turn run on ONNX Runtime instead, which
is far lighter. On a machine with 7.9 GB total this matters; torch alone would
have been a bigger install than everything here combined.

## Verified API surface (pipecat 1.8.1)

Checked by importing and reading constructor signatures, not from docs.

```python
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm  import GoogleLLMService
from pipecat.services.piper.tts   import PiperTTSService
from pipecat.audio.vad.silero     import SileroVADAnalyzer, VADParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
```

| Class | Signature (trimmed) |
|---|---|
| `DeepgramSTTService` | `(*, api_key, base_url='', encoding='linear16', sample_rate=None, live_options=None, ...)` |
| `GoogleLLMService` | `(*, api_key, model=None, system_instruction=None, params=None, tools=None, ...)` |
| `PiperTTSService` | `(*, voice_id=None, download_dir=None, force_redownload=False, use_cuda=False, ...)` |
| `PiperHttpTTSService` | `(*, base_url, aiohttp_session, voice_id=None, ...)` |
| `SileroVADAnalyzer` | plus `VADParams` |
| `LocalSmartTurnAnalyzerV3` | `(*, smart_turn_model_path=None, cpu_count=1, **kwargs)` |

## Three findings that improve on the plan's assumptions

**1. `PiperTTSService` runs in-process and downloads its own voice.**
The plan assumed Piper might need a separate server, and Task 5 anticipated a
"voice model missing" error. There is an HTTP variant (`PiperHttpTTSService`)
but the in-process one takes `download_dir` and handles the model itself. One
fewer process to run. It also accepts `use_cuda=True`, so the GTX 1050 is
available if CPU synthesis proves slow.

**2. `GoogleLLMService` takes `system_instruction` directly.**
This is exactly the per-call prompt injection the design needs. No prompt
templating or message-list surgery required; pass the generated interview
questions straight in when constructing the service for that session.

**3. `LocalSmartTurnAnalyzerV3` is present and takes `cpu_count`.**
Semantic end-of-turn detection, the local equivalent of the Vapi
`smartEndpointingPlan` that fixed the interruption problem. Confirmed available
in the installed version rather than assumed from a blog post.

## Deviation from the plan, and why

Task 1 Step 6 said to run Pipecat's own quickstart unmodified, because the plan
could not hardcode class names it had not verified. Introspecting the installed
package gave the same information more precisely: exact signatures rather than
one worked example. The quickstart was skipped as redundant.

**Still outstanding from Task 1:** the latency measurement, which needs a
microphone and a human. That now happens against our own server in Task 2
instead of a throwaway quickstart bot, which is a better test anyway since it
uses the actual services this project will run.

## Additional API findings (during Task 2 prep)

**The install command in the plan was incomplete.** `pipecat-ai[deepgram,google,piper]`
does not include FastAPI, so the websocket transport fails to import. The full
command is:

```
pip install "pipecat-ai[deepgram,google,piper,websocket]"
```

**Remaining verified names:**

```python
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner   # WorkerRunner also exists
```

`FastAPIWebsocketParams` fields that matter: `audio_in_enabled`,
`audio_out_enabled`, `serializer`, `session_timeout`, `allowed_origins`.

**VADParams defaults:** `confidence=0.7, start_secs=0.2, stop_secs=0.2,
min_volume=0.6`. Note `stop_secs=0.2` is very eager, consistent with Vapi's
0.4s default being far too quick to interrupt. This is the fallback knob if
Smart Turn is not doing enough on its own.

**VAD does not live in the transport params in 1.8.1.** It attaches to the user
side of the context aggregator pair, not to `FastAPIWebsocketParams`. The spec
assumed otherwise.

## Design correction: control channel vs audio channel

The spec and plan specify that the browser sends
`{"type": "start", "systemPrompt": "..."}` as the first WebSocket message, and
receives transcript events on that same socket.

**That does not fit how `FastAPIWebsocketTransport` works.** It expects to own
the socket for binary audio framed by its own serializer. Interleaving custom
JSON control messages means fighting that serializer.

**Corrected design, two channels:**

| Channel | Purpose |
|---|---|
| `POST /session` | Browser sends the generated system prompt, receives a session id |
| `WS /ws?session=<id>` | Pipecat owns this entirely for audio |

Transcript delivery still needs deciding: either a third channel (server-sent
events or a second websocket), or have the browser rely on Pipecat's own
transcription frames if the transport exposes a message path alongside audio.

**This is unresolved and is the first thing to settle when Task 2 resumes.**

## Turn-taking tuning

Filled in during Task 6.

| Run | Parameter changed | Value | Interruptions in 10 min |
|---|---|---|---|
| | | | |
