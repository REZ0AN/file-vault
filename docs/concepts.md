# Concepts: how File Vault fits together

This is a learning guide to the implementation as it exists now. Read the [flow diagrams](study.md) alongside it, then use the [decision guide](decision-guide.md) to decide what to keep, change, or validate next.

## Vocabulary to keep nearby

| Term | Meaning in this project |
| --- | --- |
| Cookie | Browser-held value sent with eligible requests. The app JWT cookie is HttpOnly, so frontend JavaScript cannot read it. |
| JWT | A signed statement of local user identity and expiry. The server verifies it; the browser does not become an authority by possessing UI state. |
| OAuth scope | A permission requested from Google for a specific API capability. The consent screen shows these requests. |
| ID token | Google's signed identity statement used during sign-in; it is not the token used to call Drive or Gmail. |
| Access token | Short-lived credential sent by the backend to a Google API. |
| Refresh token | Longer-lived credential exchanged by the backend for a new access token. |
| File ID | An opaque identifier. The app UUID, central Drive ID, and personal Drive ID name different objects. |
| Database transaction | A set of PostgreSQL changes committed together. It cannot atomically commit a Google API call. |
| Idempotency | A retry has the same intended effect as one request. The app partially achieves this for recorded personal Drive copies. |
| Blob URL | Browser-local URL for fetched image or PDF bytes; it is revoked when the preview closes. |

## 1. One app, three identities

| Identity | Where it lives | What it permits | What it does not permit |
| --- | --- | --- | --- |
| File Vault user | `users` in PostgreSQL, selected by an app JWT | Access to that user's dashboard and file records | Direct Google API access |
| Central storage Google account | One encrypted refresh token in backend configuration | Backend access to the private storage Drive | Signing in to File Vault; personal Gmail or Drive actions |
| User's connected Google account | One `google_connections` row per app user | Copying a file to that user's Drive and creating a draft in that user's Gmail | Reading another File Vault user's files or the central storage token |

The Google account used for storage is deliberately separate from accounts that use the app. For file actions, the browser supplies an **app file ID**, never the central Drive file ID. The backend maps that app ID to its owner and storage reference. See [`auth.py`](../backend/app/auth.py), [`files.py`](../backend/app/files.py), and [`storage.py`](../backend/app/storage.py).

## 2. Authentication, authorization, and consent answer different questions

- **Authentication:** Who is making this request? Password login or verified Google sign-in creates a File Vault session.
- **Authorization:** May this user access *this* file? The backend selects a row where both `files.id` and `files.user_id` match. A guessed UUID alone grants nothing.
- **Google consent:** What may File Vault do with a selected Google account? Google grants scopes to a token. This is separate from File Vault's file ownership decision.

The dashboard hides actions when appropriate, but hiding an icon does not enforce access. Every protected API request resolves the current user again. [`dashboard/page.tsx`](../frontend/app/dashboard/page.tsx) checks the session before rendering; [`auth.py`](../backend/app/auth.py) and [`files.py`](../backend/app/files.py) enforce it on the API.

**Try it:** Sign in as user A, upload a file, and request its preview with user B's session. The API returns 404. The backend tests exercise this boundary in [`test_flow.py`](../backend/tests/test_flow.py).

## 3. Passwords and the app session

Registration stores an Argon2 **hash**, not a password. Login verifies the submitted password against the stored hash. A dummy hash is checked when no user exists, reducing the difference between a missing account and a wrong password. Password accounts are not email verified in this PoC.

Successful sign-in sets a signed HS256 JWT in an HttpOnly, SameSite=Lax cookie for one hour. The JWT contains the local user UUID (`sub`), issuer, issued-at time, and expiry. It is signed, **not encrypted**. The server verifies the signature, issuer, and expiry and reloads the user from PostgreSQL. JavaScript cannot read the HttpOnly cookie, but the browser attaches it to eligible requests.

Logout deletes the browser cookie. It does not revoke an already copied JWT before its expiry. The current app has no server-side session table, token rotation, password reset, login rate limit, or email verification. These are decisions for a real deployment, not features implied by having a JWT.

## 4. OAuth, OpenID Connect, and Google scopes

The Google flow uses both **OAuth** and **OpenID Connect**:

- OAuth's authorization code produces tokens for Google APIs. `drive.file` allows this app to work with files it creates or that the user opens with the app. `gmail.compose` permits managing drafts and sending mail; this code only calls draft creation.
- OpenID Connect's signed ID token tells File Vault which Google user completed the flow. The backend verifies signature, issuer, audience, expiry, nonce, and verified email. It uses Google's stable `sub` as the account key.
- `state` ties the callback to the browser flow; PKCE ties the authorization code to the original request; `nonce` ties the ID token to this authentication attempt. The encrypted OAuth state cookie lasts ten minutes.

The same **Connect Google** route has two outcomes. From an existing app session it explicitly links the selected Google account to that local user. Without an app session it signs in an already linked Google subject or creates a Google-only File Vault user. Matching email alone never merges a Google identity into a password account. A Google-only user has a null password hash.

The callback requires both Drive and Gmail scopes before completing. This means a user granting only Drive cannot finish this combined flow. Existing users who connected before Gmail was added must reconnect. The backend encrypts Google tokens before saving them in PostgreSQL. It refreshes expired access tokens with the stored refresh token when needed. See [`google.py`](../backend/app/google.py) and [`session.py`](../backend/app/session.py).

**Think about it:** Which is the minimum consent experience your product needs? If many users only want personal Drive copying, splitting Drive and Gmail consent would reduce the initial permission request but add another connection state and flow.

## 5. Files, metadata, and the central Drive

The user's browser uploads a file to FastAPI. FastAPI caps it at 5 MiB, normalizes the filename, obtains a central storage token, and writes the bytes under `file-vault/<local-user-UUID>/<filename>`. PostgreSQL records the local owner, name, size, MIME type, and `storage_drive_file_id`. New rows leave the legacy `content` byte column empty. The folder path is an organization convention; the **PostgreSQL owner check** is the access rule. Drive permits duplicate names in one folder, so the file ID, not the path, is the durable reference.

On download, preview, Drive copy, or Gmail draft, FastAPI first selects the user's file row, then fetches its bytes with the central token. It sends them to the browser or to the relevant Google API. The central folder is never shared with app users. Google links are not used as public download links.

The database and Google Drive are separate systems with no shared transaction. If Drive accepts an upload and the database commit later fails, an orphan may remain. If the Drive response is lost, a retry may upload a duplicate. The current code does not reconcile these cases. `storage_drive_file_id` refers to the central original; `drive_file_id` refers to an optional copy in the user's personal Drive. See the [schema and request examples](api-and-data.md).

## 6. “Save to Drive” and “Share with Gmail”

**Save to Drive** makes a separate copy in the connected user's Drive. It does not change central Drive permissions. The backend stores the returned personal Drive ID, and a later click reports that the file is already copied. A network failure between Google accepting the copy and saving its ID can still leave a duplicate after retry.

**Share with Gmail** creates an *unsent draft* in the connected user's Gmail. The backend attaches the stored bytes and addresses the draft to the submitted email. The browser opens Gmail Drafts, where the user checks and sends it. File Vault does not call Gmail's send API and does not grant Drive access to the recipient. A draft can be created even when the file has not been copied to personal Drive.

The recipient is validated as an email address; it does not have to be a Gmail address. The current UI opens the Drafts folder because the app does not have a documented stable Gmail web link to the specific draft. See [`create_gmail_draft()`](../backend/app/google.py) and the [Gmail flow](study.md#creating-an-attached-gmail-draft).

## 7. Previewing untrusted content

Preview is an owner-checked API read. The backend chooses a supported format from the extension, then validates important bytes. It does not trust the uploaded MIME string as proof of type. The response is private, `no-store`, and returned as data to the frontend.

| Files | Backend output | Browser rendering |
| --- | --- | --- |
| TXT, code, HTML, CSS, JSON, XML, YAML | Bounded UTF-8 JSON text | Escaped React text in a code block; HTML and scripts do not run |
| Markdown | Bounded UTF-8 JSON text | React Markdown without raw HTML or external images |
| CSV | Bounded rows, columns, and response data in JSON | Text cells in a table; spreadsheet formulas remain text |
| PNG, JPEG, GIF, WebP | Image bytes after signature check | Private blob URL in an image element |
| PDF | PDF bytes after header check | PDF.js canvas, without embedding a page from the document |
| DOCX, XLSX, PPTX | ZIP structure checked, then converted by Gotenberg | PDF.js canvas of the resulting PDF |

The preview endpoint rejects unsupported types, including SVG and macro-enabled Office formats. The converter has a timeout, size limits, a separate Compose network, and no public port binding. It is still a parser for untrusted Office files, so a public deployment should review container isolation, image updates, and operational limits. See [`preview.py`](../backend/app/preview.py), [`FilePreview.tsx`](../frontend/app/dashboard/FilePreview.tsx), and [`compose.yaml`](../compose.yaml).

## 8. Browser, API, and database responsibilities

The Next.js client renders the interface, holds transient form state, shows toasts, and calls FastAPI through [`lib/api.ts`](../frontend/lib/api.ts) with credentials. It never stores Google tokens or decides file ownership. Its Google-connected flag is a display hint from the backend. FastAPI validates input, authenticates the app user, checks ownership, calls Google, and maps failures to HTTP responses. PostgreSQL is the durable index of local users, Google connections, and file ownership; Drive is the byte store.

The file list is paged by `created_at DESC, id DESC` with an offset. This is simple for a PoC; inserts between page requests can shift results across pages. A large or highly active library may call for cursor pagination. The frontend currently requests ten items per page; the backend permits one to fifty.

## 9. Browser security controls

- **SameSite=Lax cookie:** reduces cross-site cookie sending, but does not replace server validation.
- **Origin check on writes:** registration, login, logout, upload, Drive copy, Gmail draft, and Google disconnect require the configured frontend or backend origin.
- **CORS:** permits credentialed browser reads from one configured frontend origin. CORS is a browser access rule, not a user authorization check.
- **Download headers:** downloads use attachment disposition and `nosniff`. Preview responses also disable caching and use a sandbox content security policy.
- **Secrets:** JWT signing key, OAuth client secret, token-encryption key, and central storage refresh token live in backend configuration. Losing the encryption key makes stored Google tokens unreadable.

See the [security walkthrough](study.md#trust-boundaries) and [deployment decisions](decision-guide.md#release-gates-before-public-use).
