# ElevenLabs Agents — viability check

Run after Dograh was ruled out. Same four questions, answered from ElevenLabs'
own docs before installing anything.

## Verdict: viable. Everything the app needs exists, and two known UX problems
## have direct fixes.

| Requirement | ElevenLabs | Status |
|---|---|---|
| Start a call from a browser page | `@elevenlabs/client`, `Conversation.startSession()` | Confirmed |
| Inject different questions per call | `overrides.agent.prompt.prompt` | Confirmed |
| Capture the transcript | `onMessage` callback | Confirmed |
| Stop interrupting thinking pauses | Turn Eagerness "Patient" + `turn.turn_timeout` up to 30s | Confirmed |
| Fix awkward silence after speaking | Soft Timeout, speaks filler while the LLM works | Confirmed |
| Cap spend per call | `conversation.max_duration_seconds` (60-7200) | Confirmed |
| Free tier | 15 min/month, **renewing** | Confirmed |

## Per-call prompt injection

The single question that killed the Dograh plan. ElevenLabs supports it:

```javascript
const conversation = await Conversation.startSession({
  agentId: "agent_xxx",
  overrides: {
    agent: {
      prompt: { prompt: "Custom system prompt here" },
      firstMessage: "Hi, thanks for making time today."
    }
  },
  onMessage: (message) => { /* transcript */ }
});
```

Requires enabling the overridable fields first in the agent's **Security** tab.
Without that toggle the overrides are silently ignored.

## Turn-taking — better equipped than Vapi for this specific problem

Both symptoms reported during Vapi testing have named settings here:

- **"It interrupts me when I pause mid-sentence."** Turn Eagerness has a
  **Patient** mode, documented as allowing more time before treating a pause as
  an opening. Separately, `turn_timeout` accepts up to **30 seconds**, with the
  docs recommending 10-30s "when users need more thinking time." Vapi's
  equivalent was tuned to 4.5s.
- **"Sometimes it won't respond after I finish."** Soft Timeout speaks a filler
  phrase while the LLM is still generating, so the silence is filled rather than
  dead.

## Pricing

| Tier | Cost | Minutes |
|---|---|---|
| Free | $0 | 15/month, renewing |
| Starter | $6/mo | 75 |
| Creator | $22/mo | 275 |
| Overage | $0.08/min | — |

LLM costs are billed separately, which is favourable here: bring Gemini's free
tier for the conversation turn and pay ElevenLabs only for speech and
orchestration.

For comparison, 75 minutes on Vapi costs about $7.43 at the measured rate of
$0.099/min, so Starter is cheaper *and* predictable rather than a draining
balance.

## Why this is structurally different from everything else tested

Every other option is a **depleting** balance that ends: Vapi's $10 trial,
Dograh's credits (which returned HTTP 402 on the first call). ElevenLabs' free
tier **renews monthly**. Fifteen minutes is thin, roughly one interview, but it
does not run out permanently.

## Migration effort

Maps almost one-to-one onto the existing Vapi frontend:

| Current (`index.html`) | ElevenLabs equivalent |
|---|---|
| `vapi.start({model:{messages:[{role:'system',...}]}})` | `Conversation.startSession({agentId, overrides:{agent:{prompt:{prompt}}}})` |
| `vapi.on('message', ...)` | `onMessage` callback |
| `vapi.on('call-end', ...)` | disconnect callback (needs confirming) |
| `startSpeakingPlan.waitSeconds` | `turn.turn_timeout` + Turn Eagerness |

Everything else in the app is untouched: both n8n workflows, the Supabase
schema, the scoring path, and Realtime.

## Still unverified

- The exact call-end / disconnect callback name in the JS SDK.
- Whether a custom LLM (Gemini) can be wired in, or whether their bundled LLM
  is mandatory. This affects cost but not viability.
- Whether the free tier requires a card at signup.
