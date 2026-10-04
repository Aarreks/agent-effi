# Design decisions — presentation study notes

This is the running explanation of the current app. Updated as decisions change. Last updated: 4 October 2026.

## Explain the app in twenty seconds

“A resident talks to Effi. Effi collects the details, reads them back, and asks for confirmation. Its tools save a case through our backend. Staff see the case and the live conversation in the dashboard. A separate AI checks the agent's claims, and another step summarizes the call after it ends.”

## Why I made these choices

**I kept the work narrow.** The app records a municipal service issue, looks up an existing case, and adds a note. A small flow lets us demonstrate every step working.

**I used LiveKit for the conversation.** It connects the browser's microphone and speaker to the voice agent. We use LiveKit Cloud's model service for speech recognition, replies, speech, and AI review. One project supplies the credentials for all of those parts.

**I kept a separate backend.** The AI asks the backend to save or retrieve information. It does not directly edit the database. This gives the dashboard and the voice agent the same rules and the same source of truth.

**The model has four specific tools.** It can update the intake preview, create a case, look up a case, and add a note. It has no SQL tool and no general tool for sending any request it wants. The supervisor and summary step save their own findings; they do not edit case fields. The API also requires staff sign-in or the restricted worker credential.

**I used SQLite.** The demo needs data to survive a restart, but it does not need a separate database server. SQLite stores the records in a local file and lets related changes succeed or fail together.

**I used Next.js for the dashboard.** It gives us a normal browser app for viewing cases, calls, notes, and review results. The browser sends normal data requests through the same site it loaded.

**I show a draft before saving a case.** As the resident gives details, the agent updates a live intake preview. Staff can see the issue category change when the resident clarifies it. The preview is clearly a draft. A confirmed case is created only after the read-back.

**I separate call progress from service status.** A call can be connecting, active, ended, or failed. A service case can be new, in progress, or resolved. Ending a conversation does not resolve someone's service problem.

**Residents add information; staff decide service status.** A caller can report that the bin is still at the curb. The agent saves that as a note. It cannot mark work resolved or claim that a crew was dispatched. Staff change the case's service status in the dashboard.

**The backend decides whether an action succeeded.** The agent may announce a saved case only after the backend returns the saved record. If the request fails, it must say the save was not confirmed.

**Repeated delivery should not create repeated work.** A call identifies its case creation, and each note tool action has its own ID. Repeating the same action returns the first result. Reusing the same action ID for different content is rejected. A new call can add a new note, even when its wording matches an earlier report.

**I protect staff edits from stale screens.** Each case has a revision number. If someone saves an older revision after the case changed, the backend asks them to refresh. It does not quietly overwrite the newer data.

**The dashboard updates while the call is happening.** The backend sends change notices over a WebSocket, which is a connection it keeps open to the browser. The browser then fetches the latest record. It also checks periodically so it can recover if that connection drops.

**Live captions are temporary; transcript turns are permanent.** Incoming recognized speech can appear immediately in a clearly marked live caption. That text may change. When the full turn is ready, it replaces the caption and is saved in the transcript. We do not store unstable, half-recognized words as permanent transcript entries.

**A separate AI supervises the agent's replies.** It checks claims about saved requests, case numbers, status, crew dispatch, resolution, and promised dates against backend facts. It runs in the background so the resident can keep talking.

**The supervisor's correction is built from saved facts.** The AI identifies the suspect claim. Code constructs the correction using the confirmed case number and status. The reviewer cannot invent a new appointment or dispatch result in its correction.

**I keep the facts from when a reply was recorded.** Staff may change a case while a background check is running. The transcript stores the case state alongside the agent's reply, so a later change does not make a previously correct reply look false.

**A failed review is visible.** A model timeout is recorded as a failed check. It is not labeled “safe.” The dashboard shows the findings and whether a spoken correction was delivered.

**A supervisor finding must also make sense in code.** In a microphone rehearsal, the supervisor flagged an interrupted “Your request” fragment and a correct “awaiting staff review” confirmation. The backend now requires an actual saved-action claim before that kind of correction and treats familiar status wording as equivalent to the database values. A model verdict alone is not enough to interrupt a caller.

**The summary does not rewrite the case.** After the call, AI creates a summary and extracts structured information. That analysis is stored separately. It cannot silently change a person's name, staff notes, or case status.

**A linked case does not prove the caller's identity.** Someone may ask about a case without saying who they are. The analysis should leave caller identity blank unless it was supplied or confirmed in that conversation. Phone lookup is a convenience for this local demo, not proof of identity.

**An emergency takes priority over service intake.** The earlier rehearsal correctly said the app could not call 911, but then offered routine municipal help. That was a poor response. Explicit danger reports such as a flipped car now receive a fixed emergency direction through the speech pipeline, without waiting for the conversation model or a database lookup. Ordinary case actions pause until the caller confirms safety and that help is arranged or the scenario was a test. Other emergency descriptions are covered by the agent's instructions; the small phrase detector is not a complete emergency classifier. The app never places an emergency call, transfers a call, or claims responders were contacted.

**Residents can try reporting without a staff login.** The public page at `/report` starts the same real voice flow. It shows that visitor's conversation and a case confirmation. The staff dashboard remains separate and protected. Each public call gets a signed token that expires after one hour and permits reading or ending only that call. The page keeps this token in memory. It cannot use it to browse other calls, read staff records, or change a service status.

**The caller's role and the dashboard login are different.** The agent knows whether the call started on the public page or in the signed-in staff dashboard. Both use resident intake tools. Starting a call from the dashboard does not grant the voice model staff editing permissions.

**I do not promise note privacy that the app does not enforce.** Staff can see case notes, and voice lookup can return them. The public page's data response excludes notes and staff analysis, but voice lookup still has no resident identity check. A fixed answer states these app facts when the caller asks about note visibility; the supervisor can correct an unsupported privacy promise. Ordinary requests to add notes still use the case tool. Use fictional details in the demo.

**A reported correction is different from a changed field.** If the caller reports a new address, voice records a note for staff. Until staff edit the address field, the agent must distinguish the saved address from the correction in the note.

**Model quality is not the only source of mistakes.** In the latest microphone rehearsal, the agent shortened a saved case number and blurred a saved address with a correction note. The supervisor caught the case number, but its current checks do not cover address claims. Speech recognition also misheard words. Separately, a recognized interruption was missing from the saved transcript, and logs showed delays while creating supervisor network clients. Those are integration limitations, not evidence that simply buying a stronger model solves everything. The public confirmation now displays the exact case number and saved location directly from the database.

**A limited lookup is not a count of every case someone has.** Lookup supports case ID or phone, not name-only search. It returns at most five matches. The agent must describe those matches, distinguish open from resolved cases, and avoid claiming a complete total.

**I keep a change history.** Staff can see what changed, when it changed, and whether the change came from staff or the voice workflow. Saving a note leaves a visible record of the action.

**I kept the app local.** The assignment accepts a localhost demo. The browser app, backend, and voice worker run on this computer; LiveKit Cloud supplies media transport and model access. There is no phone-number integration or production deployment.

**Credentials stay out of the submission.** Local `.env` files hold the project secrets. The source ZIP includes an example config and excludes actual credentials, databases, logs, and installed dependencies.

## How to describe the checks honestly

“I tested the backend rules and built the frontend for production. I also sent synthesized resident speech through real LiveKit calls. Those calls used real speech recognition, real AI replies, real tool calls, and real agent audio. I separately injected a false resolved claim to check that the supervisor could detect it and speak a correction.”

The user's physical microphone, browser permissions, and screen-share audio still need a manual rehearsal. A speech recognizer can mishear a street name; that is why the read-back and correction step matter.

## Likely presentation questions

**Why not let the AI write directly to the database?** “I want one place to enforce the rules. The agent requests an action, and the backend decides whether it is valid and whether it was saved.”

**Why a separate supervisor?** “The conversation agent is busy helping the resident. A separate reviewer can check its claims against stored facts, and we can show those checks to staff.”

**What happens if the same tool runs twice?** “The same action ID returns the saved result. Different content under that ID is rejected, so a retry cannot quietly add a second note.”

**What happens if the live connection drops?** “The browser reconnects and fetches current records. Periodic checks keep the dashboard useful while that happens.”

**How is access controlled?** “Staff sign in to open the workspace. A public visitor can start a call and gets permission to view only that conversation. The voice worker uses a different credential and can only use the routes for its current call and linked case. The model gets four named tools. It cannot send arbitrary database queries or change staff status.”

**What would you add for real use?** “Individual staff accounts, resident identity checks, and operational monitoring. The local demo has staff sign-in and restricted worker access, but a phone number alone does not prove who a resident is.”

**Does buying a higher LiveKit tier improve the AI?** “The paid plan gives us more usage headroom. Model choice and the app's rules determine behavior. The plan itself does not make the answers better.”

## Running change log

- Initial build: chose a narrow voice-to-case flow with SQLite and a staff dashboard.
- Credential setup: switched the default on this machine to LiveKit Cloud model access, so separate model-provider keys are unnecessary.
- Retry review: rejected changed creation retries and prevented looking up another case from returning the wrong creation result.
- Browser review: added cancellation guards so ending an old connection cannot end a newly started call.
- Live speech checks: added case-ID spacing support and explicit letter spelling in the automated test. Tightened the test to correct and verify a misheard address.
- Full stretch scope: added the live intake preview and independent supervisor with recorded findings and spoken corrections.
- Concurrent-update review: added the case snapshot attached to each assistant turn so background checks use the right facts.
- Live caption review: separated temporary recognition text from saved transcript turns, and prevented an old transcript retry from clearing a newer caption.

**Staff and AI have different permissions.** Staff sign in with a local password. Their browser gets a signed cookie that expires after eight hours. The voice worker uses a separate secret kept in its process. The backend checks every request against the worker's call ID and permitted routes. The AI cannot list all cases or change staff status. Public visitors can launch voice intake; their browser can read or end only its own call, using a separate token.

**I refresh case facts before each resident turn.** Staff can change status during a conversation. The agent receives the current saved status before answering and is instructed to look it up again for each status question. Earlier conversation results must not stand in for the current record.

- Access review: added staff sign-in, protected HTTP and WebSocket access, and limited the voice-worker credential to call-related routes.
- Live status review: found an agent reusing an old status and added a fresh backend read before each user turn.
- Physical microphone rehearsal: found two supervisor false positives at the end of a successful creation. Added checks for interrupted fragments, confirmed saves, and matching status wording, with regression tests preserving real-error detection.
- Manual live status rehearsal: staff changed a case from New to Resolved during the call. The next voice lookup read the saved status. When the caller disputed resolution, the agent saved their feedback as a note and kept staff status unchanged. The same call exposed confusing role wording and an unsupported claim about who can see notes; these need clearer language.
- Whole-call policy review: added urgent-response handling, paused routine tools during emergencies, clarified staff login versus resident workflow and note visibility, stopped name-only search promises, separated canonical addresses from reported corrections, and limited case-count claims to returned matches. Post-call analysis now includes material emergency disclosures even after a goodbye.
- Public reporting: added `/report` without staff sign-in, reused the real voice flow, scoped visitor access to one call, excluded staff data from public responses, and added a confirmation built directly from the database. The public page shows the exact saved case number even if the agent misreads it.
