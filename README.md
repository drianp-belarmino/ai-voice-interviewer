# AI Interviewer — running it yourself

Two apps share one backend. Start what you need, in any order.

| Service | Port | Survives a reboot? |
|---|---|---|
| n8n (workflows) | 5678 | **Yes.** Docker, `--restart unless-stopped` |
| Frontend (both apps) | 3000 | No. Start it each session |
| Voice server (local pipeline only) | 7860 | No. Start it each session |

## The two apps

| App | URL | Voice by | Cost per interview |
|---|---|---|---|
| Vapi version | `localhost:3000/index.html` | Vapi (cloud) | ~$1.50 |
| Local version | `localhost:3000/index-local.html` | Your own pipeline | ~$0.02 |

Both use the same n8n workflows, the same Supabase table, and the same scorecard.
Only the voice layer differs.

## First-time setup

The frontend reads its keys from `web/config.js`, which is gitignored. Copy the
template and fill in your own values:

```bash
cp web/config.example.js web/config.js
```

| Key | Where to get it |
|---|---|
| `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` | Supabase dashboard, Project Settings > API |
| `VAPI_PUBLIC_KEY` | Vapi dashboard (only needed for the Vapi version) |

The voice server reads its own keys from `voice/.env` — copy `voice/.env.example`
the same way.

**Note on the Supabase key.** `supabase/schema.sql` grants read access to any
holder of the publishable key. That is fine for a single-user local tool and not
fine for anything hosted. Tighten the RLS policy before putting this on a public
URL.

## Starting up

### 1. n8n — usually already running

```powershell
docker ps                 # is "n8n" listed?
docker start n8n          # only if it is not
```

Check: open http://localhost:5678

If Docker Desktop itself is closed, open it from the Start menu first and wait
for "Engine running" bottom-left.

### 2. Frontend — needed for both apps

```powershell
cd "C:\Users\Dell\Desktop\Project Demannu\.claude\worktrees\ai-interviewer\ai-interviewer\web"
npx serve .
```

Leave that window open. Closing it stops the site.

### 3. Voice server — only for the local version

```powershell
cd "C:\Users\Dell\Desktop\Project Demannu\.claude\worktrees\ai-interviewer\ai-interviewer\voice"
.\venv\Scripts\Activate.ps1
python server.py
```

Leave that window open too. Check: http://localhost:7860/health should report
both keys present.

**Close BlueStacks before a voice session.** It holds about 1.3 GB, which is the
difference between this running smoothly and stuttering.

## When something breaks

**"Voice server offline"** — you skipped step 3, or its window got closed.

**Page loads but "Could not reach n8n"** — n8n container is stopped. `docker start n8n`.

**Everything looks fine but nothing saves, or the app hangs on scoring** — the
Supabase free tier pauses after about a week idle. Check:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://YOUR-PROJECT.supabase.co/rest/v1/interview_sessions?select=id&limit=1 -H "apikey: YOUR-PUBLISHABLE-KEY"
```

`200` is healthy. `000` means it paused. Restore it at
https://supabase.com/dashboard/project/YOUR-PROJECT and wait a few minutes.
This will happen again. It is how the free tier works, not a fault.

**Interview dies partway through with a 429** — Gemini free-tier quota. Every
conversational turn is one API request, and free limits are as low as 20 per day
per model. Either wait, or enable billing on the API key's Google Cloud project,
which costs roughly two cents per interview. Note that a Google One / Gemini
Advanced subscription does **not** include API access; that is a separate product.

## Where things live

| | |
|---|---|
| Frontends | `ai-interviewer/web/` |
| Voice server | `ai-interviewer/voice/server.py` |
| n8n workflow exports | `ai-interviewer/n8n/` |
| Supabase schema | `ai-interviewer/supabase/schema.sql` |
| API keys | `ai-interviewer/voice/.env` (gitignored) |
| Findings and decisions | `ai-interviewer/voice/NOTES.md`, `ai-interviewer/dograh/FINDINGS.md` |

**The n8n workflows live inside the Docker volume `n8n_data`, not in this repo.**
The JSON exports in `ai-interviewer/n8n/` are backups you can re-import, but
credentials never export. Deleting that volume means re-entering the Gemini and
Supabase credentials by hand.

## Tuning the local voice pipeline

All in `ai-interviewer/voice/.env`, no code changes:

| Setting | Default | Raise it if |
|---|---|---|
| `DEEPGRAM_ENDPOINTING_MS` | 800 | It cuts you off mid-sentence |
| `DEEPGRAM_UTTERANCE_END_MS` | 1200 | Your speech arrives in fragments |
| `VAD_STOP_SECS` | 1.0 | It responds while you are still thinking |

Lower them if it feels sluggish. Change one at a time.

## Known gaps

Found on 2026-09-24 by deliberately breaking things. All verified, none fixed yet.

**The health check cannot detect a dead key.**
`/health` and `POST /session` both check only that `DEEPGRAM_API_KEY` and
`GOOGLE_API_KEY` are non-empty. Neither checks that the credential works. With a
revoked or quota-exhausted key both report success and the app registers an
interview it cannot finish, so the failure surfaces only once someone is
mid-sentence. A real check would make one cheap authenticated call at startup.

**A transient 503 from Gemini kills the interview before it starts.**
The Google Gemini node in the question-generation workflow has no retry
configured. Google returned 503 once during testing and the page showed
"n8n returned an empty or invalid response" with nothing recoverable. Fix is in
n8n: select the node, Settings, Retry On Fail, three tries with a wait between.

**Voice errors always read "unknown error".**
`onError` in `web/index-local.html` reads `msg.message`, but the RTVI error
object carries its payload in `msg.data`. The real cause reaches the browser and
is thrown away. The server side also logs the exception in `voice/server.py`
without sending anything over the socket, so a corrected handler still needs the
server to emit it.

**Teardown after a voice error runs out of order.**
A failed session leaves an uncaught promise rejection, "Session ended: please
call .begin() first". The media recorder keeps operating on a session that has
already closed.

**DNS caches a paused Supabase project.**
When the project pauses its hostname stops resolving, and your resolver caches
that answer. After restoring, the name still fails locally while public
resolvers already see it. Run `ipconfig /flushdns`. Confirm with
`nslookup <host> 8.8.8.8`, which resolves while your own resolver does not.
