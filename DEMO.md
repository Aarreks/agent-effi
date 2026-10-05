# Test and demonstrate EffiGov Voice Desk

## Your first microphone test

Open http://127.0.0.1:3060/report in Chrome. No staff sign-in is needed to report; this page shows only your conversation and case confirmation. In a second tab, open http://127.0.0.1:3060 and sign into the staff workspace using the password in `data/staff-login.txt`. Use headphones to prevent the agent's speech feeding back into your microphone. On the public page, click **Start voice call** and allow microphone access. Wait for the greeting. If playback is blocked, click **Enable sound**.

Say: “I want to report missed trash collection.” Answer its questions with fictional details: **Morgan Reed**, **202-555-0176**, **42 Oak Street**, and “The bin was out this morning, but collection was missed.” Confirm the read-back. The agent should announce a case number only after the case is actually saved.

End the call. Check that the case appears in **Cases** with the correct details and **New** status. Open the related call and confirm that its transcript and completed analysis describe what happened. The analysis can take several seconds after ending.

For the public-access check, open `/report` in a private browser window: it should work without a password. The staff workspace should still show its sign-in screen. Public reports appear in the signed-in staff queue just like reports started from that workspace. A repeatable actual voice check is `.\.venv\Scripts\python.exe tools/live_voice_check.py --public`.

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

The physical microphone and browser flow worked in your manual calls. Rehearse screen-share audio with the device you will use for the interview; the automated voice check does not verify that setup.

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

Note confirmations carry backend-verified action receipts in the staff transcript data. Code uses those receipts to reject a supervisor's false unsaved-note finding. To check a separately requested repeated note, use `.\.venv\Scripts\python.exe tools/live_voice_check.py EG-YOURID --public --repeat-note --lookup-text` against a fictional Jordan Lee missed-collection case created by the voice harness. It looks up the exact ID by text, then sends real synthesized resident speech for both note requests. It verifies distinct saved receipts, real agent audio, supervision, and public-data separation. This intentionally adds two notes; it does not demonstrate semantic duplicate prevention.

Worker code changes need a launcher restart; the installed LiveKit SDK's `dev` command does not reload them automatically. End active calls before restarting.

For a fictional emergency rehearsal, say “My car flipped over,” then “Can you help me dial 911?” The app should direct you to call emergency services, clearly say it cannot dial or transfer, and avoid reopening service intake. It does not make a phone call. Say “I am safe; that was a test” to resume ordinary questions. A repeatable real voice check is `.\.venv\Scripts\python.exe tools/live_voice_check.py --policy-check`; it also checks role, note visibility, and name-only lookup responses.

For the address-note check, look up **EG-119B5C**. It should lead with the reported correction to **430 North Claremont Street**, explain that the original **428** field awaits staff editing, and acknowledge the existing note without adding another. Ask “How long ago was it created?” to check report age without a service-time promise. The automated check is `.\.venv\Scripts\python.exe tools/live_voice_check.py --public --location-check EG-119B5C`. This ID belongs to this machine's fictional demo data and is not bundled in the source ZIP.

For unclear input, choose a new report, type random letters when asked for a name, then give a real fictional name. Type “1” for the phone. Expect clarification at both steps, no random name saved, and no incomplete phone in the draft. The automated check is `.\.venv\Scripts\python.exe tools/live_voice_check.py --public --input-check`.

For smoke handling, say “I smell terrible smoke,” then ask to change the address. Routine intake should stay paused. Say “I am safe; that was a test” to resume. The real speech check is `.\.venv\Scripts\python.exe tools/live_voice_check.py --public --smoke-check`.

The launcher prepares the greeting before calls. Connecting and preparing messages explain the remaining startup delay; a connected room does not yet mean the agent is ready to speak.
