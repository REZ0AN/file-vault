# What this PoC proves, and what to decide next

This guide separates behavior demonstrated by the code and tests from assumptions that need a real environment. Use it before extending or deploying File Vault. Start with the [concept guide](concepts.md) if the account and token roles are unfamiliar.

## Confirmed in this repository

| Question | Evidence here | Limit of that evidence |
| --- | --- | --- |
| Can password and Google users share one local authorization model? | [`auth.py`](../backend/app/auth.py), [`google.py`](../backend/app/google.py), and owner-filter tests | Password email ownership is not verified; real Google consent still depends on Cloud setup. |
| Can the storage account stay out of user registration? | [`storage.py`](../backend/app/storage.py), registration and Google sign-in rejection tests | A stolen central token could still access the central Drive. |
| Can file bytes live in Drive while PostgreSQL controls ownership? | Upload/download paths and mocked central storage tests | No measured availability, cost, quotas, backup, or real Google recovery test. |
| Can a user copy a file to their own Drive? | Owner check, personal token selection, saved `drive_file_id`, tests | Google and PostgreSQL cannot commit atomically; retries may duplicate. |
| Can the app create an addressed Gmail draft with an attachment? | MIME draft construction and tests confirm attachment, no send call | Google consent, mailbox UI behavior, and restricted-scope verification need live validation. |
| Can the app preview the listed file types safely? | Format checks, owner checks, PDF.js and converter integration code, tests | Office conversion requires the container; parser isolation and browser behavior need integration testing. |

The automated backend suite uses SQLite and mocked Google responses. The frontend suite checks API client behavior; lint and build check the UI code. They do not prove Google's live APIs, token renewal over days, browser account switching, backup recovery, or converter performance.

## Product decisions

| Decision | Current PoC choice | Keep it when… | Reconsider when… |
| --- | --- | --- | --- |
| What does “share” mean? | Copy to the user's Drive or create an unsent Gmail attachment draft. | The user remains the sender and manually reviews email. | Recipients need a live Drive link, shared permissions, expiry, or collaboration. Those require a different permission model and UX. |
| Who owns stored originals? | One unregistered central Google account. | The audience is small and controlled, files are small, and operational ownership is clear. | You need independent storage tenancy, formal backups, lifecycle policies, stronger availability targets, or higher volume. |
| Where do bytes live? | Central Drive; PostgreSQL keeps references. | You are evaluating the workflow and understand that Drive availability gates reads. | You need large uploads, streaming, durable object lifecycle, regional policy, or predictable storage operations. Evaluate an object store and measure the full cost, including transfer and requests. |
| When is Google consent requested? | Drive and Gmail together during Google sign-in/connect. | Nearly everyone uses both actions and can accept that consent. | Users want basic sign-in or Drive copy without Gmail's restricted permission. Split identity, Drive, and Gmail grants. |
| How is the app session managed? | One-hour JWT cookie, no server-side revocation. | Short-lived sessions and simple PoC logout behavior suffice. | You need immediate revocation, device management, audit trails, or compromised-session response. Consider server-side sessions or a token denylist/rotation design. |
| How are Office files previewed? | Local Gotenberg converts to PDF on demand. | Small documents and occasional previews fit the timeout and resource cap. | You need high throughput, expensive repeated conversions, fidelity requirements, or strict isolation. Add caching, jobs, quotas, and a hardened converter environment. |
| How are files listed? | Offset pagination of owner-filtered rows. | Libraries are small and writes are infrequent. | Deep pages or concurrent additions cause slow queries or shifting pages. Use a cursor tied to the ordering keys. |

The current Gmail flow requests [`gmail.compose`, a restricted Google scope](https://developers.google.com/workspace/gmail/api/auth/scopes). The scope is capable of managing drafts **and sending email**, although this app only calls `drafts.create`. A public OAuth app using restricted scopes may need verification and, if restricted-scope data is stored or transmitted on servers, a security assessment under Google's rules. Treat this as a launch decision, not a minor checkbox. By contrast, [`drive.file` is a narrower per-file Drive scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).

## Release gates before public use

These are gaps in the current implementation, ordered by what they protect. Decide explicitly whether each applies to the intended audience. The PoC is not a public-service security claim.

1. **Account recovery and abuse controls:** Verify password-account email ownership, add password reset, durable login and registration rate limits, and monitor abuse. Decide whether all users may self-register.
2. **Session policy:** Define revocation, expiry, key rotation, logout across devices, and incident response. The current JWT remains valid until expiry if copied before logout.
3. **Google consent and compliance:** Confirm the exact scopes, testing versus production publishing status, OAuth verification, and Gmail restricted-scope requirements. [Google documents seven-day refresh-token expiry for External apps in Testing](https://developers.google.com/identity/protocols/oauth2), with its stated exception for basic profile-only scopes; this app requests more than basic profile.
4. **Storage durability and lifecycle:** Back up both PostgreSQL metadata and central Drive bytes, test restore together, define delete/retention behavior, reconcile orphaned and missing Drive files, and monitor quota and token expiry. No delete endpoint or automatic reconciliation exists now.
5. **Untrusted files:** Define allowed upload types, malware scanning, file quarantine, download policy, and stronger Office converter isolation. Preview validation covers supported renderers but upload itself accepts arbitrary file types up to 5 MiB. [OWASP's file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) is a useful review checklist.
6. **Scale and reliability:** Measure Google latency, API quotas, converter CPU/memory, whole-file buffering, database growth, retries, and concurrency. The 5 MiB limit keeps this PoC simple; larger files need a different transfer design.
7. **Operations and tests:** Add structured audit events, monitoring, backup drills, a sandbox Google integration suite, and browser tests for auth cookies, dialogs, previews, and multi-account Gmail behavior. Keep secrets out of logs and user-facing errors.

## Failure windows worth testing

| Inject this failure | Current likely outcome | Design question |
| --- | --- | --- |
| Google accepts upload, DB commit fails | Central Drive may hold an orphan with no app row. | How will you discover and clean orphaned files? |
| Google accepts personal copy, response is lost | Retry may create another copy because `drive_file_id` was not saved. | Is duplicate avoidance needed, and where should idempotency live? |
| Gmail accepts draft, response is lost | Retry may create another draft. | Should the UI ask users to inspect Drafts before retrying? |
| Central refresh token expires or is revoked | Stored files remain indexed but reads fail until storage reconnects. | What is the recovery time target and alert path? |
| File is removed directly from central Drive | PostgreSQL still lists it; download and preview fail. | Will you prohibit manual changes or reconcile them? |
| User changes browser Google account after connecting | App token still targets the originally linked account; Gmail web tab may show another account. | Should the UI show or enforce the connected account more explicitly? |
| Converter is down | Office previews fail; download and non-Office previews still work. | Is Office preview essential or optional? |
| User uploads a hostile file | App stores it; supported preview formats face parsers. | Which scanning and isolation controls match your audience? |

## A practical evaluation session

Use two File Vault users, two personal Google accounts, and the separate storage account. Keep test files harmless and small.

1. Register user A with a password. Upload a TXT, PDF, DOCX, and CSV. Confirm the rows show only A's files; inspect central Drive for A's UUID folder.
2. Sign in as user B. Confirm B cannot list, download, preview, copy, or draft from A's app file ID. A 404 is expected for file-specific access.
3. Connect A's personal Google account. Confirm the consent scopes, copy one file, and verify that the personal copy is separate from the central original. Repeat the action and inspect for duplicates.
4. Create a Gmail draft addressed to a non-Gmail address. Check its attachment and connected sender account; leave it unsent unless you deliberately want a mail-delivery test.
5. Preview every supported type. Stop the converter and confirm the Office preview error is isolated. Try an SVG and a malformed Office file; they should be rejected.
6. Let a test grant expire or revoke it in Google. Observe which actions fail and how reconnection behaves. Do not rotate the encryption key casually: old ciphertext needs that key.
7. Record upload/read latency, central Drive usage, conversion time, and whether the user understands the three account roles. These observations are more useful for the storage and consent decisions than a unit-test pass alone.

## Questions to answer before choosing a target architecture

- Is the product for one operator, a small trusted group, or public self-service users?
- Are files personal backups, temporary transfer objects, or records with retention requirements?
- Must recipients get attachments, Drive permission links, or both? Who can revoke access?
- What file sizes, formats, daily volume, and preview latency must work?
- What are acceptable recovery time and data-loss windows if the storage account or database is unavailable?
- Is Gmail's restricted scope justified by the product value and review cost?
- Do you need immediate session revocation and a documented incident response?

Answer these with measured PoC results and actual product requirements. The current code establishes the core flows, but it does not settle those operational and policy choices.
