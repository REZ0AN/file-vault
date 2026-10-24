# Central Google Drive storage setup

This PoC uses one Google account as its private file store. **Do not register or sign in to File Vault with this account.** Its Drive holds `file-vault/<app-user-id>/<filename>`. App users still have their own File Vault accounts; they may optionally connect their own Google account to copy a file to their Drive or create Gmail drafts.

## 1. Prepare Google Cloud

1. Enable the **Google Drive API** and **Gmail API** in the same Google Cloud project as File Vault.
2. In your existing **Web application** OAuth client, keep `http://localhost:8000/api/v1/google/callback` and add the exact redirect URI `http://127.0.0.1:8765/callback` for the one-time storage setup script.
3. Keep the OAuth consent scopes `openid`, `email`, `https://www.googleapis.com/auth/drive.file`, and `https://www.googleapis.com/auth/gmail.compose` for app users. The storage setup script requests only `drive.file`.
4. If the OAuth app is in **Testing**, add the separate storage account and each test user as test users. [Google says refresh tokens for External / Testing apps with Drive scopes expire after seven days](https://developers.google.com/identity/protocols/oauth2); rerun setup when the storage token expires.

## 2. Prepare backend secrets

Copy values from [`backend/.env.example`](../backend/.env.example) into `backend/.env`. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_TOKEN_ENCRYPTION_KEY`, database settings, `JWT_SECRET_KEY`, and `FRONTEND_ORIGIN`. Keep `backend/.env` private and reuse the same Fernet key after setup; changing it makes encrypted storage and user tokens unreadable.

From `backend/`, install dependencies and generate a Fernet key if you do not have one:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 3. Authorize the unregistered storage account once

Run this **on your own computer**, where a browser can open and the loopback callback can listen on port 8765:

```bash
cd backend
.venv/bin/python scripts/setup_storage.py --folder-name file-vault
```

Choose the dedicated storage Google account at Google's account picker and approve Drive access. The script verifies the callback state and PKCE code, checks which account was selected, creates its top-level `file-vault` folder, and prints three values. Add all three to `backend/.env`:

```dotenv
STORAGE_GOOGLE_ACCOUNT_EMAIL=the-dedicated-account@gmail.com
STORAGE_GOOGLE_ROOT_FOLDER_ID=the-folder-id-from-setup
STORAGE_GOOGLE_REFRESH_TOKEN_CIPHERTEXT=the-encrypted-token-from-setup
```

The ciphertext is encrypted with `GOOGLE_TOKEN_ENCRYPTION_KEY`, but both are secrets when stored together in `.env`. The storage account is not added to PostgreSQL `users` or `google_connections`; File Vault rejects registration and Google sign-in for `STORAGE_GOOGLE_ACCOUNT_EMAIL`.

When rerun with the existing `STORAGE_GOOGLE_ROOT_FOLDER_ID` in `.env`, setup verifies and reuses that folder, then prints a fresh encrypted token. Keep the folder ID and replace only the ciphertext when reconnecting the **same** storage account. The script rejects a different selected account when `STORAGE_GOOGLE_ACCOUNT_EMAIL` is already configured.

## 4. Prepare PostgreSQL and start the app

You said you will clean the PoC database. Do that separately when ready; this guide does not delete data. Apply the non-destructive schema migration:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

In another terminal, start the frontend with `cd frontend && npm install && npm run dev`.

## 5. Check each path

1. Register or sign in with an **app user account**, not the storage account.
2. Upload one small file. In central Drive, look for `file-vault/<app-user-uuid>/<filename>`. PostgreSQL stores its owner, metadata, and `storage_drive_file_id`; the new file's `content` is `NULL`.
3. Download it from the dashboard. FastAPI checks ownership and fetches the bytes from central Drive with the storage token.
4. Connect the app user's own Google account. **Save to Drive** uploads a separate copy owned by that user's account. `drive_file_id` records this personal copy.
5. Create a Gmail draft. FastAPI reads the central copy, attaches it using the user's Gmail connection, and opens Gmail Drafts. The app does not send the email.

The backend never shares central folders with app users. Every file read first selects the PostgreSQL row using the authenticated local user ID. A Drive link or file ID from the browser is never accepted as proof of ownership.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `Central Drive storage is not configured` | All three `STORAGE_GOOGLE_*` values are in `backend/.env`; restart the backend. |
| `Central Drive authorization expired` | Rerun setup with the same storage account; Testing refresh tokens can expire after seven days. Keep track of the old root folder ID. |
| Central Drive rejects folder creation or upload | Confirm Drive API is enabled, the root folder belongs to the selected storage account, and it has quota. |
| User Drive or Gmail action fails | Check the **user's** Google connection and scopes; the central storage token is separate. |
| Download returns a central Drive error | The file may have been deleted or moved from the central account, or the central grant may have expired. |

The PoC retains a 5 MiB upload limit. If Drive accepts an upload but the PostgreSQL commit fails, an orphaned Drive file may remain. If you later need larger files, use resumable uploads rather than the current multipart upload. [Google's upload guide](https://developers.google.com/workspace/drive/api/guides/manage-uploads) covers both.
