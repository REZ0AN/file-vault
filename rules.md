# Project rules

## Architecture to preserve

- FastAPI authenticates the local user and checks file ownership on every protected file action. Frontend state, file IDs, and Google account email are never proof of access.
- PostgreSQL owns users, file metadata, and encrypted user Google connections. A separate, unregistered Google account stores original file bytes in central Drive. Keep its token and file IDs behind the backend.
- A user's Google token is used only for that user's personal Drive copy or Gmail draft. “Save to Drive” creates a copy; “Share with Gmail” creates an unsent draft. Do not broaden either action silently.
- Treat uploaded bytes and MIME types as untrusted. Keep previews owner-checked, bounded, and rendered as data; Office conversion stays isolated from the browser.
- Keep the UI's dark red/black brutalist style and short toast feedback. Do not expose storage internals in routine user messages.

## How to change the code

- Follow existing FastAPI/Next.js patterns and the local [frontend rules](frontend/AGENTS.md). Keep the PoC small; add dependencies or services only when they solve the requested problem.
- Preserve existing data with an Alembic migration when the schema changes. Never silently drop stored files or Google connections.
- Add or adjust focused tests for changed auth, ownership, storage, Google, or preview behavior. Run backend tests with `cd backend && .venv/bin/python -m unittest discover -s tests -v`; run frontend checks with `cd frontend && npm test && npm run lint && npm run build` when affected.
- Update [docs/study.md](docs/study.md), [docs/api-and-data.md](docs/api-and-data.md), or [docs/decision-guide.md](docs/decision-guide.md) when their described behavior or decision changes. Keep secrets out of code, docs, logs, and test output.
