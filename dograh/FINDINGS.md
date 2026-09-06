# Dograh Findings

## 1. Are the bundled models local or remote?

**Probably remote. Not proven. The offline test in Task 2 is now decisive
rather than confirmatory.**

`docker-compose.yaml` declares nine services, and **none of them is a model
server**:

| Service | Image | Role |
|---|---|---|
| postgres | pgvector/pgvector:pg17 | database |
| redis | redis:7 | cache/queue |
| minio | minio/minio | object storage |
| dograh-init | bash:5.2 | one-shot setup |
| nginx | nginx:alpine | reverse proxy |
| coturn | coturn/coturn:4.8.0 | TURN server (WebRTC) |
| api | dograhai/dograh-api:latest | application backend |
| ui | dograhai/dograh-ui:latest | web frontend |
| cloudflared | cloudflare/cloudflared:latest | outbound tunnel |

No `whisper`, `piper`, `ollama`, `vllm`, or any STT/TTS/LLM service.

A grep for provider credentials across the whole compose file returns **no
Deepgram, ElevenLabs, OpenAI, Anthropic, Cartesia, or Groq keys**. The only
keys present are for Postgres, MinIO, optional AWS, and PostHog analytics.

So the API has model access without any provider key being supplied locally,
which matches the README's "ships with auto-generated keys and its own
LLM/TTS/STT stack." The most likely explanation is that `dograh-api` calls
Dograh's own hosted service using keys it provisions.

**The caveat that keeps this from being proven:** the `dograh-api` image could
bundle inference internally rather than running it as a separate container. The
compose file cannot rule that out. Only the offline test can.

## 2. Is there a browser call API?

**Very likely yes.** `coturn` is a TURN server, which exists specifically to
relay WebRTC media when a direct peer connection fails. Shipping one by default
means browser-based WebRTC calls are a first-class path, not an afterthought.
The exact client-side API still needs confirming in Task 3.

## 3. Kill check

**CONTINUE, but the premise is now in question.**

The Task 1 kill criterion as written was "stop if there is no browser call
path." That criterion is not met; there is almost certainly a browser path.

However, the *other* question came back badly. If the models are remote, the
justification for this whole project weakens sharply, because "self-hosted"
would then mean self-hosting the orchestrator while inference still runs on
someone else's infrastructure, on someone else's terms, with limits nobody has
documented.

## 3b. Dograh on localhost expects an internet tunnel

Discovered while installing, before the offline test was even attempted.

Their `docker-compose.yaml` states it plainly:

> When the value is non-public (localhost or a private/reserved IP), the API
> resolves a running Cloudflare tunnel's URL at runtime instead

So a localhost install is *designed* to reach out through Cloudflare. There is
no supported setting for "I am local and I do not want a tunnel."

Measured effect, same `/api/v1/health` endpoint:

| cloudflared | Response time |
|---|---|
| running | 0.008 - 0.03 s |
| stopped | 3.83 - 3.99 s |

With the tunnel stopped, the API blocks ~3.8s on failed tunnel discovery. The
UI health check times out at 3000ms, so the whole app shows "Backend connection
failed" until the tunnel is restored.

**Why this matters:** a product that genuinely ran offline would not put
internet-dependent tunnel discovery in its health path. This is independent
evidence, gathered before Task 2's offline call test, that Dograh assumes
connectivity. It does not prove where inference runs, but it points the same
direction as Task 1's finding.

Note also that running the tunnel means the instance is reachable on a public
`*.trycloudflare.com` URL with signup enabled. The URL is ephemeral and changes
on every restart, which also rules it out as a stable way to share the app.

## VERDICT: project stopped. Dograh does not solve the problem.

Confirmed by running it, not by reading marketing. The first test call failed:

```
quota_service.py:613  | Dograh run authorization passed for key ...ICyj2owb: 500.00 credits remaining
service_factory.py:263| Creating STT service: provider=ServiceProviders.DOGRAH, model=default
ERROR                 | STT error: server rejected WebSocket connection: HTTP 402
WARNING               | DograhFluxSTTService#0 connection closed by server
```

Three facts, all decisive:

1. **The STT provider is `ServiceProviders.DOGRAH`** — their hosted service, not
   anything running on this machine. Task 1's read of the compose file was right.
2. **There is a server-side credit system** (`500.00 credits remaining`), owned
   and metered by Dograh.
3. **HTTP 402 Payment Required.** The call was refused for payment reasons on the
   very first attempt, while online.

**What "self-hosted, no API keys needed" actually means here:** you host the
orchestrator, the workflow builder, and the database. Inference runs on Dograh's
cloud, against a credit balance they control, gated on payment.

That is the same shape as Vapi. A depleting balance that ends in a paywall. The
difference is that Vapi's already works, has better-tuned turn-taking, and needs
no Docker maintenance.

The offline test was never needed. The **online** test failed.

### Cost of finding out

About 90 minutes, no code written, no change to the working app. Tasks 4, 5 and 6
were never started. This is what the staged plan with early kill-checks was for.

### What this does not mean

Dograh is not bad software. The visual workflow builder is genuinely good and the
install was clean. It is a real Vapi alternative for someone willing to pay
Dograh instead of Vapi, or to wire in their own paid provider keys. It is simply
not a route to free voice AI, which was the only reason this project existed.

## 4. Notes

- The presence of `cloudflared` by default suggests outbound connectivity is
  expected as normal operation, not an edge case.
- Ports to watch for collisions: Dograh's UI is on 3010, MinIO binds 9000, the
  API health check references 8000. None of these collide with n8n on 5678 or
  the frontend on 3000.
- If the offline test fails, the honest reading is that Dograh replaces Vapi's
  *orchestration* for free but not Vapi's *inference*, which was the expensive
  part. That would not solve the problem this project exists to solve.
