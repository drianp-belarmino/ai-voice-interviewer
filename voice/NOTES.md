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

## Turn-taking tuning

Filled in during Task 6.

| Run | Parameter changed | Value | Interruptions in 10 min |
|---|---|---|---|
| | | | |
