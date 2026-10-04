# EffiGov Voice Desk

Local LiveKit voice intake → FastAPI + SQLite → Next.js staff dashboard. The narrow workflow records one confirmed municipal service request per call, retrieves an existing request by case ID or phone, and adds resident notes. Staff change service status. Calls and case changes appear through WebSocket notifications with polling recovery.

## Run on Windows

Prerequisites: Git, Python 3.11–3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Node 22.22 or newer.

```powershell
git clone https://github.com/Aarreks/agent-effi.git
cd agent-effi
.\setup.ps1
# Complete the LiveKit Cloud credential steps below before launching.
.\run.ps1
```

Open http://127.0.0.1:3060/report to try resident reporting without a staff password. Open http://127.0.0.1:3060 for the protected staff workspace (API docs: http://127.0.0.1:8060/docs). Allow microphone access and start a call. The launcher starts the API and configured voice worker, and starts a local LiveKit server when the URL uses localhost. Cloud mode uses the Cloud room server. API and worker logs are in `data/`. Ctrl+C stops processes created by the launcher. For Chrome system-audio sharing during the debrief, open the same localhost URL in Chrome.

## Get your own voice credentials (recommended: LiveKit Cloud)

1. Sign in or create an account at [LiveKit Cloud](https://cloud.livekit.io/) and create a project. The project needs available LiveKit Inference usage or credit to run the voice models.
2. In that project's settings, copy its **Project URL** (starts with `wss://`). Obtain an **API key** and its **API secret** from the project's API keys settings. Use credentials from the same project.
3. Open the local `.env` created by `setup.ps1` (on macOS/Linux, copy `.env.example` to `.env` yourself). Replace all three local development values and select Cloud mode:

   ```dotenv
   VOICE_PROVIDER=livekit
   LIVEKIT_URL=wss://YOUR-PROJECT.livekit.cloud
   LIVEKIT_API_KEY=YOUR-PROJECT-API-KEY
   LIVEKIT_API_SECRET=YOUR-PROJECT-API-SECRET
   ```

4. Leave the other settings in place. `OPENAI_API_KEY` can stay empty: this mode uses LiveKit Inference for speech recognition, replies, speech synthesis, supervision, and analysis. It needs no separate OpenAI, Deepgram, or Fish Audio keys. Setup generates the local staff password and worker/signing secrets automatically.
5. Run `.\run.ps1`, keep the terminal open, and visit **http://127.0.0.1:3060/report**. To inspect staff records, visit **http://127.0.0.1:3060** and use the generated password in `data/staff-login.txt`.

The voice worker runs locally. You do not need to create or deploy an agent in the Cloud dashboard, buy a phone number, or start a local LiveKit server for this mode. Actual `.env` files and data are excluded from the repository; every reviewer supplies their own credentials. Restart the launcher after changing credentials. Models and voice IDs are configurable in `.env`. See the [LiveKit CLI setup guide](https://docs.livekit.io/reference/developer-tools/livekit-cli/) for account authentication and project setup.

Alternatively, install the CLI on Windows with `winget install LiveKit.LiveKitCLI`, authenticate using `lk cloud auth`, and run `lk app env --write --destination .env.local` from this repository. Copy its three `LIVEKIT_*` connection values into `.env`, preserving the other settings. The app reads `.env`; creating only `.env.local` is insufficient. Never include either credentials file in a source archive.

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

`backend/main.py` owns HTTP/WebSocket routes and analysis scheduling. `store.py` owns transactions, retry handling and audit records. `agent.py` owns the LiveKit session, four API tools, and the background review loop. `locations.py` extracts explicit address correction notes without changing saved fields. `supervision.py` checks reply claims and constructs corrections from backend facts. `analysis.py` owns structured post-call extraction, including attribution of notes to their actual call. `greeting.py` prepares the constant greeting before Cloud calls; the Windows launcher runs it automatically. The frontend uses one-origin HTTP rewrites and a direct localhost WebSocket.

```powershell
.\check.ps1
# With local LiveKit running, check actual media transport without AI charges:
.\.venv\Scripts\python.exe tools\check_transport.py
```

Tests exercise create → triage → lookup → note, concurrent retries, changed-request conflicts, stale revisions, transcript replay, persistence, WebSocket updates and analysis failure. AI/tool selection and audio interaction still require a live call to validate; passing API tests does not establish those behaviors. Any `mode=test` call in the local demo is labeled API test and was not an AI voice call.

Staff sign-in protects the dashboard, staff case/call APIs, and live event stream. Setup generates a local password in `data/staff-login.txt`, a signing secret, and a separate voice-worker credential. Staff sessions use an expiring HttpOnly SameSite cookie. The public `/report` page can launch a voice call without signing in. It receives a signed, one-hour token that permits only reading and ending that call through separate public routes. Its response excludes backend case snapshots, case notes, change history, and staff analysis; a small confirmation shows the linked case number, issue, location, and current status. The token stays in the page's memory, not a URL or persistent browser storage. Starting public calls is limited to five per minute per client address in this single-process demo. The worker can access its current call and linked case, create a confirmed request, or append a resident note; it cannot list the database or edit staff status. The model sees four fixed tools and never receives these credentials or SQL access. Phone/case-ID voice lookup remains a demo convenience rather than proof of resident identity. All demo records should be fictional. Real municipal use would need resident identity verification and stronger abuse controls. This is not a deployed service or telephony integration.

## Manual start on macOS/Linux with LiveKit Cloud

Run `uv sync --frozen`, copy `.env.example` to `.env`, enter the three Cloud credentials, and run `uv run python tools/configure_auth.py`. Sign in using `data/staff-login.txt`. Then keep three terminals open, starting from this directory:

```sh
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8060
uv run python -m backend.greeting
uv run python -m backend.agent dev
cd frontend && npm ci && npm run dev -- --hostname 127.0.0.1 --port 3060
```

Run the greeting preparation once in the worker terminal, then start the worker in that same terminal. The API and frontend each need their own terminal. Greeting preparation is optional and falls back to live speech synthesis if unavailable. Cloud mode needs no local LiveKit server. Python and frontend dependencies are pinned by the included lockfiles.

## Sources

Implementation references: [LiveKit Python starter](https://github.com/livekit-examples/agent-starter-python), [LiveKit local server](https://docs.livekit.io/transport/self-hosting/local/), [OpenAI realtime plugin](https://docs.livekit.io/agents/models/realtime/plugins/openai/), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs). No application template source was copied. The small JSON client was reused from this workspace's preparation kit.

The emergency direction follows the [National 911 Program's calling guidance](https://www.911.gov/calling-911/). This application provides no emergency connection or dispatch capability. `backend/policy.py` holds the demo capability rules and the narrow fast path for explicit urgent phrases; the broader emergency behavior is also part of the voice instructions.
