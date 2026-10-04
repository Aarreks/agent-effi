# Test and demonstrate EffiGov Voice Desk

## Your first microphone test

Open http://127.0.0.1:3060 in Chrome. Sign in using the password in `data/staff-login.txt`. Use headphones to prevent the agent's speech feeding back into your microphone. Click **Start voice call** and allow microphone access. Wait for the greeting. If playback is blocked, click **Enable sound**.

Say: “I want to report missed trash collection.” Answer its questions with fictional details: **Morgan Reed**, **202-555-0176**, **42 Oak Street**, and “The bin was out this morning, but collection was missed.” Confirm the read-back. The agent should announce a case number only after the case is actually saved.

End the call. Check that the case appears in **Cases** with the correct details and **New** status. Open the related call and confirm that its transcript and completed analysis describe what happened. The analysis can take several seconds after ending.

Open the case again. Change its status to **In progress**, add “Forwarded to sanitation for route review,” and save. Start a second call: “Please check my request. My phone number is 202-555-0176.” The agent should report **In progress**. Ask: “Please add a note that the bin is still at the curb.” End the call and verify a new **Voice** note and a new event in **Change history**.

If several cases share that phone, the agent will ask you to choose a case. Supply its case number, spelling letters if necessary. For a new rehearsal, use another fictional name and phone number. Existing cases persist when the app restarts.

## A five-minute debrief

1. Explain the flow in one sentence: “A resident speaks with the LiveKit agent; its tools write to FastAPI and SQLite; staff see the case, transcript, and updates in this dashboard.”
2. Create a fresh request by voice. Show the call arriving immediately, live captions, collected details and issue category. Keep the read-back and confirmation visible in the transcript, then show the saved case.
3. Triage it in the dashboard, then make a follow-up voice call to read the actual status and append a note.
4. Show the supervisor checks, separate call analysis, search/status filters, and case change history. Explain that creating a request does not mean a crew was dispatched or the issue was resolved.
5. Be ready to open `backend/agent.py` for tool definitions, `backend/store.py` for persistence/retries, and `backend/main.py` for HTTP/WebSocket routes.

For screen sharing, use the Chrome/system-audio option requested by the assignment, and check with the interviewer that they can hear the agent. Close tabs or editors displaying credentials before sharing.

## Checks already performed versus your remaining check

Real LiveKit Cloud calls using synthesized resident audio verified speech recognition, generated agent audio, case creation, status lookup, resident-note updates, and structured post-call analysis. These calls used real models and backend tools. API tests verify retries, stale-update conflicts, transcript persistence, and live event notifications.

Your physical microphone, browser permission, selected audio devices, and screen-share audio still need a short manual rehearsal. The automated voice check does not verify those devices.

## Start or troubleshoot

If the dashboard is already open and **Start voice call** is enabled, use the running app. To start it after shutdown, open PowerShell in `submission` and run `./run.ps1`. Keep that terminal running. First-time installation uses `./setup.ps1`.

If another run already occupies the ports, return to its terminal or stop it with Ctrl+C before starting another. Do not run two voice workers against the same project for this demo.

- **Microphone denied:** allow microphone access for localhost in Chrome and try again.
- **Need the staff password:** open `data/staff-login.txt`; setup and the launcher generate it locally without printing it. Keep it closed during screen sharing.
- **Cannot hear Effi:** use **Enable sound**, check your output device, and avoid muting the browser tab.
- **Worker did not join / provider error:** inspect `data/agent-error.log`; confirm the three LiveKit Cloud values in `.env` and restart the launcher.
- **Analysis failed:** use **Retry analysis** after the call ends. A failed analysis does not erase the saved case.
- **Saved case absent from a filtered list:** clear search and select **All statuses**.

LiveKit Cloud supplies all model credentials for the configured Cloud mode. Separate OpenAI keys are needed only if you intentionally select the direct OpenAI alternative. LiveKit Ship can provide rehearsal headroom beyond the free inference allowance; it does not itself improve model quality.

## Optional stretch demonstration

During a status lookup call, change the case status in another dashboard tab. Ask for its status again after each save. The dashboard updates immediately and the agent reads the current saved value.

Supervisor checks appear in the call view. To demonstrate a correction reliably, use the explicitly labeled fault-injection check against an unresolved fictional case: `.\.venv\Scripts\python.exe tools/check_supervisor_voice.py EG-YOURID`. This intentionally speaks a false resolved claim, runs the real AI reviewer, and receives real correction audio. Its call is labeled **API test**, and the case status remains unchanged. Explain the injected error as a test rather than presenting it as a natural resident call.

Worker code changes need a launcher restart; the installed LiveKit SDK's `dev` command does not reload them automatically. End active calls before restarting.

For a fictional emergency rehearsal, say “My car flipped over,” then “Can you help me dial 911?” The app should direct you to call emergency services, clearly say it cannot dial or transfer, and avoid reopening service intake. It does not make a phone call. Say “I am safe; that was a test” to resume ordinary questions. A repeatable real voice check is `.\.venv\Scripts\python.exe tools/live_voice_check.py --policy-check`; it also checks role, note visibility, and name-only lookup responses.
