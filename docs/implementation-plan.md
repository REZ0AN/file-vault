# Historical implementation plan

This file records how the PoC reached its current design. For present behavior, start with the [documentation index](README.md). For remaining choices, use the [decision guide](decision-guide.md).

## Decisions

- Keep the existing PostgreSQL `users`, `files`, and `google_connections` data. Add a migration for Google-only accounts, whose password hash is nullable, and a unique Google subject.
- Use one short-lived **app JWT** in an HttpOnly cookie for both password and Google sign-in. Every dashboard and file route resolves that JWT to a user in PostgreSQL. The frontend never treats its own state as authorization.
- Verify Google's signed OpenID Connect ID token and identify Google accounts by `sub`. A logged-in user can explicitly link Google; an existing password account is never silently merged by matching email.
- Store Google access and refresh tokens encrypted in `google_connections`, owned by the app user. The app JWT never grants Google permissions by itself.
- Upload new file bytes to a separate, unregistered central Google account. PostgreSQL keeps owner IDs, metadata, and central Drive file IDs. The personal Drive and Gmail actions read central bytes, then use the app user's own Google token. Keep the old byte column nullable for legacy rows.
- Keep the 5 MiB limit and request `drive.file`, `gmail.compose`, `openid`, and `email`. SameSite cookies and exact Origin checks protect state-changing requests.

## Steps

1. ✅ Restore database models and migrations, preserving existing rows. Add configuration and dependency declarations.
2. ✅ Add password registration/login, JWT cookie verification, Google sign-in/linking, and dashboard authorization.
3. ✅ Add per-user file metadata, owner-checked downloads, and copying files to the owner's connected Drive.
4. ✅ Replace the frontend with sign-in, registration, protected dashboard, upload, and own-Drive copy flows.
5. ✅ Add separate backend and frontend test commands and suites, run checks, and document the complete trust flow and migration.
6. ✅ Add per-file Gmail draft creation with a recipient and attachment, with separate backend and frontend tests.
7. ✅ Add server-backed file pagination and icon actions with upload and Gmail input modals.
8. ✅ Add a separate central Drive OAuth setup script, storage adapter, schema migration, and setup guide. Keep the storage account out of app registration.

## Acceptance checks

- An anonymous request cannot read the dashboard data or another user's files.
- Password and Google sign-in both reach the same app user after explicit linking.
- Google identity is verified by signature, audience, issuer, expiry, and stable subject.
- A stored file can be copied to its owner's connected Drive; a repeat request reuses the Drive file ID.
- A file owner can create an attached Gmail draft addressed to a valid email; another local user cannot create it from that file.
- New uploads leave `files.content` empty and store a central Drive file ID; downloading and both Google actions read central storage after the owner check.
- Existing database rows survive `alembic upgrade head`.
- Backend tests, frontend tests, lint, and production build pass.

Apply migration `9d38c7a10f21` with `alembic upgrade head`; PoC data cleanup is a separate choice. The tests mock Google; live storage-account consent, Drive upload, and Gmail draft creation still require the configured Google Cloud project. Follow the [storage setup guide](storage-setup.md).
