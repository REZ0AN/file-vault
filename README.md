# File Vault

File Vault stores private file bytes in a **separate central Google Drive account** and keeps ownership and file IDs in PostgreSQL. Users can sign in with a password or Google, copy a file to **their own connected Google Drive**, or create an unsent Gmail draft with that file attached.

Start with the [documentation index](docs/README.md) for the study path and decision guide. For local setup, use the [central Drive setup guide](docs/storage-setup.md).

## Local setup

1. Start PostgreSQL and the Office preview converter with `docker compose up -d`.
2. Follow the [storage setup guide](docs/storage-setup.md) to configure Google Cloud and authorize the separate storage account. Add `http://127.0.0.1:8765/callback` to the OAuth client's redirect URIs alongside the app callback.
3. Set up the backend. Existing `backend/.env` files can be kept; add any missing variables from [the example](backend/.env.example). Generate `JWT_SECRET_KEY` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Generate `GOOGLE_TOKEN_ENCRYPTION_KEY` with the Fernet command below.

   ```bash
   cd backend
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   .venv/bin/python scripts/setup_storage.py --folder-name file-vault
   # Add the three printed STORAGE_GOOGLE_* values to backend/.env.
   .venv/bin/alembic upgrade head
   .venv/bin/uvicorn app.main:app --reload
   ```

4. In another terminal, start the frontend:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Open `http://localhost:3000`. Use `localhost` for both apps; the HttpOnly auth cookie is host-only and shared across local ports.

## Tests

```bash
(cd backend && .venv/bin/python -m unittest discover -s tests -v)
(cd frontend && npm test && npm run lint && npm run build)
```

Backend tests use an isolated SQLite database and mocked Google responses. Live storage-account consent and Drive uploads require your Google Cloud configuration and are not covered by those mocked tests.

## Main routes

| Route | Purpose |
| --- | --- |
| `POST /api/v1/auth/register`, `POST /api/v1/auth/login` | Password account and app JWT cookie. |
| `GET /api/v1/auth/me`, `POST /api/v1/auth/logout` | Check or end the local session. |
| `GET /api/v1/google/connect`, `GET /api/v1/google/callback` | Google sign-in or explicit account linking. |
| `GET /api/v1/google/status`, `POST /api/v1/google/disconnect` | Check or remove stored Drive credentials. |
| `GET /api/v1/google/files` | List up to 100 Drive files accessible to this app. |
| `POST /api/v1/files`, `GET /api/v1/files?page=1&page_size=10`, `GET /api/v1/files/{id}` | Upload to central Drive, page through metadata, and download the current user's files. The list returns `items`, `total`, `page`, and `page_size`. |
| `GET /api/v1/files/{id}/preview` | Owner-checked preview. Returns JSON for text, Markdown, and CSV; safe image bytes or PDF for images, PDFs, and converted Office files. |
| `POST /api/v1/files/{id}/drive` | Copy the stored file to the signed-in user's connected Google Drive. |
| `POST /api/v1/files/{id}/gmail-draft` | Create an unsent draft in the connected Gmail account with `{ "email": "recipient@gmail.com" }` and the stored file attached. |

The server enforces a 5 MiB upload limit. New PostgreSQL file rows store no bytes. Password users choose their personal Google account with **Connect Google**; Google sign-in links the account used during consent. Gmail drafts do not change Drive permissions or send email. The dashboard opens Gmail Drafts in a new tab; select the new draft and check the connected account if your browser has multiple Google accounts.

## Previews

Use the eye icon beside a stored file. TXT, Markdown, CSV, code, and HTML are parsed as data; HTML and scripts never execute. PNG, JPEG, GIF, and WebP are shown only after signature checks. PDFs render with a local PDF.js worker. DOCX, XLSX, and PPTX are converted to PDF by the local LibreOffice-only [Gotenberg](https://gotenberg.dev/docs/convert-with-libreoffice/convert-to-pdf) service, then rendered in the same viewer. Office preview requires Docker Compose running; set `PREVIEW_CONVERTER_URL` if the API and converter are on different hosts.

Preview access uses the app session and the file ownership check. The converter listens on loopback, accepts only server-submitted Office files, and has a 30-second timeout, small queue, and container resource limits. The API bounds input and output size, validates Office ZIP structure, and returns `no-store` responses. Previews do not create public Drive links or save converted PDFs. SVG and macro-enabled Office formats are unsupported. For a public deployment, keep the converter on a private network, restrict its egress, and pin a reviewed image digest.
