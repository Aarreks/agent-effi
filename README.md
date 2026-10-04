# EffiGov Voice Desk

Local LiveKit voice intake → FastAPI + SQLite → Next.js staff dashboard. The narrow workflow records one confirmed municipal service request per call, retrieves an existing request by case ID or phone, and adds resident notes. Staff change service status. Calls and case changes appear through WebSocket notifications with polling recovery.

## Run on Windows

Prerequisites: Python 3.11–3.13, uv, and Node 22.22 or newer.

```powershell
.\setup.ps1
# Connect LiveKit Cloud, or add OPENAI_API_KEY to .env using a local editor.
.\run.ps1
```

Open http://127.0.0.1:3060 (API docs: http://127.0.0.1:8060/docs). Allow microphone access and start a call. The launcher starts the API and configured voice worker, and starts a local LiveKit server when the URL uses localhost. Cloud mode uses the Cloud room server. API and worker logs are in `data/`. Ctrl+C stops processes created by the launcher. For Chrome system-audio sharing during the debrief, open the same localhost URL in Chrome.

The default `VOICE_PROVIDER=auto` uses LiveKit Inference when Cloud credentials are configured. This supplies speech recognition, the conversation model, speech synthesis, and structured call analysis through one LiveKit project, with no separate OpenAI, Deepgram, or voice-provider keys. Install the optional [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/) on Windows with `winget install LiveKit.LiveKitCLI`. Authenticate with `lk cloud auth`, then run `lk app env --write --destination .env.local`. Copy its `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` values into `.env`, preserving the other settings. Alternatively, obtain those three values from the LiveKit Cloud project settings and enter them locally. Never include either credentials file in a source archive. Set `VOICE_PROVIDER=livekit` explicitly if desired. Models and voice IDs are configurable in `.env`.

The alternative `VOICE_PROVIDER=openai` uses OpenAI Realtime and structured Responses analysis. With the local LiveKit server, only `OPENAI_API_KEY` needs external account access and credit. Missing credentials disable voice explicitly; they do not silently substitute a simulated conversation. All model/provider choices are implementation choices, not additional take-home requirements.

## Demo

See [DEMO.md](DEMO.md) for a microphone rehearsal, a five-minute debrief, and troubleshooting.
The running plain-language presentation notes are in [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

1. “I want to report missed trash collection.” Supply a name, phone and location; confirm the read-back. The agent calls the case API and returns its case number.
2. Open that case on the dashboard. Change its status to In progress and add a staff note.
3. Start another call, provide the case ID or phone, and ask for an update. Add new information; confirm the resident note appears.
4. End the call. Review the transcript, structured analysis, and case change history.

Calls are visible before a case exists. Recognized speech appears as a temporary live caption; finalized turns form the saved transcript. Collected details and issue category appear in a live intake preview before confirmation. A separate background AI checks the agent's factual claims and speaks grounded corrections when needed. AI analysis is separate from staff-controlled case data and never silently overwrites it. Only successful backend writes may be spoken as confirmed. A case is a recorded request, not dispatched or resolved work.

## Code and checks

`backend/main.py` owns HTTP/WebSocket routes and analysis scheduling. `store.py` owns transactions, retry handling and audit records. `agent.py` owns the LiveKit session, four API tools, and the background review loop. `supervision.py` checks reply claims and constructs corrections from backend facts. `analysis.py` owns structured post-call extraction. The frontend uses one-origin HTTP rewrites and a direct localhost WebSocket.

```powershell
.\check.ps1
# With local LiveKit running, check actual media transport without AI charges:
.\.venv\Scripts\python.exe tools\check_transport.py
```

Tests exercise create → triage → lookup → note, concurrent retries, changed-request conflicts, stale revisions, transcript replay, persistence, WebSocket updates and analysis failure. AI/tool selection and audio interaction still require a live call to validate; passing API tests does not establish those behaviors. Any `mode=test` call in the local demo is labeled API test and was not an AI voice call.

Staff sign-in protects the dashboard, case/call APIs, and live event stream. Setup generates a local password in `data/staff-login.txt`, a signing secret, and a separate voice-worker credential. Staff sessions use an expiring HttpOnly SameSite cookie. The worker can access its current call and linked case, create a confirmed request, or append a resident note; it cannot list the database or edit staff status. The model sees four fixed tools and never receives these credentials or SQL access. Calls are launched from this internal staff workspace. Phone lookup is convenience rather than proof of resident identity; public resident access would need identity verification. All demo records are fictional. It is not a deployed service or telephony integration.

## Manual start on macOS/Linux with LiveKit Cloud

Run `uv sync --frozen`, copy `.env.example` to `.env`, enter the three Cloud credentials, and run `uv run python tools/configure_auth.py`. Sign in using `data/staff-login.txt`. Then keep three terminals open, starting from this directory:

```sh
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8060
uv run python -m backend.agent dev
cd frontend && npm ci && npm run dev -- --hostname 127.0.0.1 --port 3060
```

Each line above belongs in a separate terminal. Cloud mode needs no local LiveKit server. Python and frontend dependencies are pinned by the included lockfiles.

## Sources

Implementation references: [LiveKit Python starter](https://github.com/livekit-examples/agent-starter-python), [LiveKit local server](https://docs.livekit.io/transport/self-hosting/local/), [OpenAI realtime plugin](https://docs.livekit.io/agents/models/realtime/plugins/openai/), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs). No application template source was copied. The small JSON client was reused from this workspace's preparation kit.

The emergency direction follows the [National 911 Program's calling guidance](https://www.911.gov/calling-911/). This application provides no emergency connection or dispatch capability. `backend/policy.py` holds the demo capability rules and the narrow fast path for explicit urgent phrases; the broader emergency behavior is also part of the voice instructions.
