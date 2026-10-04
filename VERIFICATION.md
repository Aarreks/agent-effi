# Verification — 4 October 2026

Verified on Windows with Python 3.12, Node 24.19, and the dependencies in `uv.lock` and `frontend/package-lock.json`.

- Setup and launcher: dependency installation succeeded; existing Cloud credentials were preserved. The launcher starts the API on 8060, configured LiveKit Cloud worker, and Next dashboard on 3060. Local records survive restart.
- Backend: 89 tests pass. Coverage includes transactional retries, changed-request conflicts, stale staff revisions, voice-note idempotency, ambiguous phone lookup, transcript/caption replay, live events, analysis failure, supervision timing, current status context, supervisor false positives, urgent speech routing without model/HTTP calls, blocked routine actions during an emergency, safe resumption, and precise role/note-visibility answers.
- Access: anonymous HTTP reads/writes and WebSocket access are rejected. A worker credential cannot list records, operate under another call ID, access an unrelated linked case, or modify staff status. Valid worker intake, creation, transcript, and note requests succeed. Logout, cookie flags, origin checks, missing configuration, and login attempt limits are tested.
- Frontend: production compilation, TypeScript, and static page generation passed after the sign-in UI was added. The browser shows the staff sign-in page. Prior browser checks verified live updates, staff triage, case notes, and change history.
- Media transport: two actual local LiveKit participants exchanged data and synthetic audio without a model API.
- Real voice creation: synthesized fictional resident speech passed through Cloud STT, the real conversation model, backend tools, and real agent audio. A read-back correction was required for a misheard street name; the saved case EG-2B7EEF correctly records 24 Cedar Avenue. Live intake stages and post-call analysis were verified.
- Latest real voice check, call 240c4512-b71b-4b26-ab4a-2207790b6601: authenticated staff launched the call; the restricted worker retrieved EG-2B7EEF and added a note. Staff changed status from in progress to resolved and back to in progress during the call. The agent spoke each new saved status. Five real AI supervisor reviews were persisted, 12 live-caption WebSocket events were received, and structured analysis completed. Exit code 0.
- Latest supervisor fault injection, API-test call 609c88e5-e2f9-4af6-a6fa-0e89f00e312f: a controlled false resolved claim went through the real background reviewer with the restricted worker credential. A correction grounded in EG-D3F0BA's saved status was spoken and actual correction audio received. The review was persisted and the case remained unchanged. Exit code 0.
- Whole-call policy review: real Cloud voice call 940a6019-1630-4d08-a344-b554341b5d1e passed role explanation, note visibility, refusal of name-only lookup, explicit vehicle-emergency guidance, inability to dial/transfer, and resumption after an explicit safe/test confirmation. The Cloud speech pipeline emitted the fixed urgent responses without a conversation-model or case-lookup request. User and assistant turns were preserved, actual agent audio was received, no case was created or linked, seven real supervisor reviews completed, and 26 live-caption events were received. Post-call analysis included the emergency disclosure and the later clarification that it was a test. Exit code 0.
- Separate real model evaluations: the revised supervisor flags the original unsupported privacy promise; revised analysis includes the emergency disclosure after the original goodbye. Conversation-policy fixtures distinguish a saved address from a correction in a note and avoid claiming an exhaustive count from a five-result lookup.
- Core-flow regression after the policy changes, real Cloud voice call bf02dd67-e9d0-44f6-a15c-410bd0afa4fa: retrieved EG-2B7EEF, read its current in-progress status, and saved a resident note including “we still see the trash outside the mailbox.” This confirms the note-visibility question routing does not consume ordinary note requests. Real agent audio, three supervisor reviews, ten live-caption events, and completed analysis were verified. Exit code 0.

## Assignment coverage

| Requirement | Implementation and evidence |
| --- | --- |
| Voice creates, looks up, and updates requests | Real Cloud voice calls created cases, retrieved current status, and appended resident notes. |
| FastAPI, uv, SQLite, Next staff dashboard | Included source and lockfiles; working local launcher and persistence. |
| Immediate case/status updates | WebSocket notices with polling recovery; staff revision checks; live status-cycle voice check. |
| Live call and transcript | Call row appears on session creation; temporary captions and saved utterances update during the conversation. |
| Additional fields and issue category update | Live intake preview persists learned/corrected details and collecting/confirmation/recorded stages. |
| Clean repeated updates | Atomic creation and action IDs prevent duplicate work on retries; changed retries are rejected. |
| Search and filters | Case search plus status filter in the dashboard. |
| Background supervisory AI with correction | Independent model checks factual claims; grounded spoken correction verified through real LiveKit audio. |
| Post-call summary and extraction | Structured AI analysis stored separately, visible failure state, and retry control. |
| Audit log display | Case change history shows revisions, changed fields, notes, timestamps, and staff/voice source. |

The live voice harness synthesizes only the fictional resident's input. It does not simulate the agent, tools, STT, TTS, supervision, or analysis. Calls marked **API test** are deliberate backend/fault-injection fixtures.

An exploratory live status test found stale reuse of an earlier tool result. The agent now fetches current case facts before every user turn and repeats lookup for new status questions. The latest status-cycle check above passed after this fix. Background reviews use the case snapshot recorded with the reply, so later staff changes do not make earlier correct replies appear false.

The user's physical microphone and browser voice flow worked in real manual rehearsals. In call 1bdffc9c-d0a2-41ab-b8d0-de927c0e31f0, a staff status save changed EG-12C912 from new to resolved at 15:23:04 PDT. The agent reported the new resolved status on the next lookup, distinguished recorded status from proof of work, and appended the resident's disagreement at 15:24:19 without changing status. All 22 supervisor checks completed with no corrections or failures. The agent also gave unsupported general note-visibility advice and confusing staff-versus-resident wording; those statements are not established app behavior. Screen-share audio remains for manual rehearsal. Public resident identity verification, production account management, deployment, and telephony integration are outside this local staff demo.

The source ZIP uses an explicit inclusion list and excludes credentials, databases, logs, dependencies, downloaded binaries, screenshots, and synthesized speech files. The installed Starlette emits a TestClient/httpx deprecation warning; it does not fail the checks.
