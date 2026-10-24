"""Backend auth, ownership, OAuth linking, Drive copy, and Gmail draft tests."""

import asyncio
import base64
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.google import create_gmail_draft, drive_error, upload_bytes, verify_google_identity
from app.main import app
from app.models import GoogleConnection, StoredFile
from app.storage import create_user_folder, read_storage_file, storage_access_token

ORIGIN = {"Origin": "http://localhost:3000"}


class FakeGoogle:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, url, **kwargs):
        return httpx.Response(200, json={
            "access_token": "google-access", "refresh_token": "google-refresh",
            "id_token": "signed-id-token", "scope":
            "openid email https://www.googleapis.com/auth/drive.file "
            "https://www.googleapis.com/auth/gmail.compose",
            "expires_in": 3600,
        })

    async def get(self, url, **kwargs):
        return httpx.Response(200, json={"files": []})


class BackendFlowTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "example-client", "GOOGLE_CLIENT_SECRET": "example-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/api/v1/google/callback",
            "GOOGLE_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "JWT_SECRET_KEY": "test-secret-with-at-least-thirty-two-characters",
            "FRONTEND_ORIGIN": "http://localhost:3000",
            "STORAGE_GOOGLE_ACCOUNT_EMAIL": "storage@example.com",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

        def test_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, base_url="http://localhost:8000")
        self.storage_files: dict[str, bytes] = {}

        async def fake_upload(token, filename, mime, content, parent_id=None):
            self.assertEqual(token, "root-token")
            self.assertEqual(parent_id, "user-folder")
            file_id = f"root-{uuid.uuid4()}"
            self.storage_files[file_id] = content
            return file_id

        async def fake_read(token, file_id):
            self.assertEqual(token, "root-token")
            return self.storage_files[file_id]

        for name, replacement in (
            ("storage_access_token", AsyncMock(return_value="root-token")),
            ("root_folder_id", lambda: "app-folder"),
            ("create_user_folder", AsyncMock(return_value="user-folder")),
            ("upload_bytes", fake_upload),
            ("read_storage_file", fake_read),
        ):
            patched = patch(f"app.files.{name}", new=replacement)
            patched.start()
            self.addCleanup(patched.stop)

    def register(self, client=None, email="alice@example.com"):
        return (client or self.client).post("/api/v1/auth/register", headers=ORIGIN,
                                           json={"email": email, "password": "correct-password"})

    def connect_google(self, client=None):
        client = client or self.client
        started = client.get("/api/v1/google/connect", follow_redirects=False)
        params = parse_qs(urlsplit(started.headers["location"]).query)
        self.assertIn("openid", params["scope"][0])
        self.assertIn("https://www.googleapis.com/auth/gmail.compose", params["scope"][0])
        with patch("app.google.httpx.AsyncClient", return_value=FakeGoogle()), \
             patch("app.google.verify_google_identity", return_value=("google-subject", "alice@example.com")):
            return client.get("/api/v1/google/callback", params={
                "state": params["state"][0], "code": "one-use-code",
            }, follow_redirects=False)

    def test_password_login_and_private_files(self):
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/register", json={
            "email": "alice@example.com", "password": "correct-password",
        }).status_code, 403)
        user = self.register().json()
        self.assertEqual(self.client.get("/api/v1/auth/me").json()["id"], user["id"])

        saved = self.client.post("/api/v1/files", headers=ORIGIN,
                                 files={"file": ("note.txt", b"private bytes", "text/plain")})
        self.assertEqual(saved.status_code, 201)
        file_id = saved.json()["id"]
        with self.Session() as db:
            record = db.query(StoredFile).one()
            self.assertIsNone(record.content)
            self.assertEqual(self.storage_files[record.storage_drive_file_id], b"private bytes")
        self.assertEqual(len(self.client.get("/api/v1/files").json()["items"]), 1)
        self.assertEqual(self.client.get(f"/api/v1/files/{file_id}").content, b"private bytes")
        preview = self.client.get(f"/api/v1/files/{file_id}/preview")
        self.assertEqual(preview.json()["text"], "private bytes")
        self.assertEqual(preview.headers["cache-control"], "private, no-store")
        self.assertEqual(self.client.post(f"/api/v1/files/{file_id}/drive", headers=ORIGIN).status_code, 409)
        self.assertEqual(self.client.post(f"/api/v1/files/{file_id}/gmail-draft", headers=ORIGIN,
                                          json={"email": "friend@gmail.com"}).status_code, 409)

        other = TestClient(app, base_url="http://localhost:8000")
        self.register(other, "bob@example.com")
        self.assertEqual(other.get("/api/v1/files").json()["items"], [])
        self.assertEqual(other.get(f"/api/v1/files/{file_id}").status_code, 404)
        self.assertEqual(other.get(f"/api/v1/files/{file_id}/preview").status_code, 404)
        self.assertEqual(other.post(f"/api/v1/files/{file_id}/drive", headers=ORIGIN).status_code, 404)
        self.assertEqual(other.post(f"/api/v1/files/{file_id}/gmail-draft", headers=ORIGIN,
                                    json={"email": "friend@gmail.com"}).status_code, 404)

        self.client.post("/api/v1/auth/logout", headers=ORIGIN)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/login", headers=ORIGIN, json={
            "email": "alice@example.com", "password": "wrong-password",
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/login", headers=ORIGIN, json={
            "email": "alice@example.com", "password": "correct-password",
        }).status_code, 200)
        self.assertEqual(self.register(email="storage@example.com").status_code, 403)

    def test_file_pages_are_bounded_and_owner_filtered(self):
        self.register()
        created = set()
        for index in range(12):
            response = self.client.post("/api/v1/files", headers=ORIGIN,
                                        files={"file": (f"file-{index}.txt", b"x", "text/plain")})
            created.add(response.json()["id"])
        first = self.client.get("/api/v1/files?page=1&page_size=5").json()
        second = self.client.get("/api/v1/files?page=2&page_size=5").json()
        third = self.client.get("/api/v1/files?page=3&page_size=5").json()
        self.assertEqual((first["total"], first["page"], first["page_size"]), (12, 1, 5))
        self.assertEqual([len(batch["items"]) for batch in (first, second, third)], [5, 5, 2])
        self.assertEqual({item["id"] for batch in (first, second, third) for item in batch["items"]}, created)
        self.assertEqual(self.client.get("/api/v1/files?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/files?page_size=51").status_code, 422)
        other = TestClient(app, base_url="http://localhost:8000")
        self.register(other, "bob@example.com")
        self.assertEqual(other.get("/api/v1/files").json()["total"], 0)

    def test_google_link_signin_and_copy_to_own_drive_once(self):
        local_user = self.register().json()
        linked = self.connect_google()
        self.assertEqual(linked.status_code, 307)
        self.assertEqual(self.client.get("/api/v1/auth/me").json()["id"], local_user["id"])
        status = self.client.get("/api/v1/google/status").json()
        self.assertTrue(status["connected"])
        self.assertTrue(status["gmail_ready"])
        self.assertEqual(status["email"], "alice@example.com")
        with self.Session() as db:
            connection = db.query(GoogleConnection).one()
            self.assertEqual(connection.google_subject, "google-subject")
            self.assertNotIn(b"google-refresh", connection.refresh_token_ciphertext)

        saved = self.client.post("/api/v1/files", headers=ORIGIN,
                                 files={"file": ("note.txt", b"content", "text/plain")}).json()
        upload = AsyncMock(return_value="drive123456789")
        with patch("app.files.upload_bytes", upload):
            first = self.client.post(f"/api/v1/files/{saved['id']}/drive", headers=ORIGIN)
            second = self.client.post(f"/api/v1/files/{saved['id']}/drive", headers=ORIGIN)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["uploaded"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["uploaded"])
        self.assertEqual(second.json()["drive_file_id"], "drive123456789")
        self.assertEqual(upload.await_count, 1)
        upload.assert_awaited_once_with("google-access", "note.txt", "text/plain", b"content")

        draft = AsyncMock(return_value="draft-1")
        with patch("app.files.create_gmail_draft", draft):
            created = self.client.post(f"/api/v1/files/{saved['id']}/gmail-draft", headers=ORIGIN,
                                      json={"email": "friend@gmail.com"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["recipient"], "friend@gmail.com")
        self.assertEqual(created.json()["draft_id"], "draft-1")
        draft.assert_awaited_once_with("google-access", "friend@gmail.com", "note.txt",
                                       "text/plain", b"content")

        self.client.post("/api/v1/auth/logout", headers=ORIGIN)
        signed_in = self.connect_google()
        self.assertEqual(signed_in.status_code, 307)
        self.assertEqual(self.client.get("/api/v1/auth/me").json()["id"], local_user["id"])

    def test_google_id_token_checks_audience_and_nonce(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {
            "sub": "stable-google-subject", "email": "alice@example.com",
            "email_verified": True, "nonce": "expected-nonce",
            "iss": "https://accounts.google.com", "aud": "example-client",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})
        with patch("app.google.GOOGLE_KEYS.get_signing_key_from_jwt",
                   return_value=SimpleNamespace(key=private_key.public_key())):
            self.assertEqual(verify_google_identity(token, "example-client", "expected-nonce"),
                             ("stable-google-subject", "alice@example.com"))
            with self.assertRaises(jwt.InvalidTokenError):
                verify_google_identity(token, "another-client", "expected-nonce")
            with self.assertRaises(jwt.InvalidTokenError):
                verify_google_identity(token, "example-client", "wrong-nonce")

    def test_google_only_signin_and_no_silent_email_merge(self):
        signed_in = self.connect_google()
        self.assertEqual(signed_in.status_code, 307)
        google_user = self.client.get("/api/v1/auth/me").json()
        self.assertEqual(google_user["email"], "alice@example.com")
        self.client.post("/api/v1/auth/logout", headers=ORIGIN)
        self.assertEqual(self.client.post("/api/v1/auth/login", headers=ORIGIN, json={
            "email": "alice@example.com", "password": "correct-password",
        }).status_code, 401)

        # An unlinked password account with the same verified email is not silently merged.
        self.register(email="bob@example.com")
        self.client.post("/api/v1/auth/logout", headers=ORIGIN)
        other = TestClient(app, base_url="http://localhost:8000")
        started = other.get("/api/v1/google/connect", follow_redirects=False)
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        with patch("app.google.httpx.AsyncClient", return_value=FakeGoogle()), \
             patch("app.google.verify_google_identity", return_value=("new-subject", "bob@example.com")):
            result = other.get("/api/v1/google/callback", params={
                "state": state, "code": "one-use-code",
            }, follow_redirects=False)
        self.assertIn("Sign+in+with+your+password", result.headers["location"])
        self.assertEqual(other.get("/api/v1/auth/me").status_code, 401)

    def test_central_storage_account_cannot_sign_in(self):
        started = self.client.get("/api/v1/google/connect", follow_redirects=False)
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        with patch("app.google.httpx.AsyncClient", return_value=FakeGoogle()), \
             patch("app.google.verify_google_identity",
                   return_value=("root-subject", "storage@example.com")):
            response = self.client.get("/api/v1/google/callback", params={
                "state": state, "code": "one-use-code",
            }, follow_redirects=False)
        self.assertIn("central+storage+account+cannot+sign+in", response.headers["location"])
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

    def test_oauth_state_and_refresh(self):
        started = self.client.get("/api/v1/google/connect", follow_redirects=False)
        wrong = self.client.get("/api/v1/google/callback", params={
            "state": "not-the-state", "code": "one-use-code",
        }, follow_redirects=False)
        self.assertIn("OAuth+state+check+failed", wrong.headers["location"])
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

        self.connect_google()
        with self.Session() as db:
            connection = db.query(GoogleConnection).one()
            connection.access_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        with patch("app.google.httpx.AsyncClient", return_value=FakeGoogle()):
            listed = self.client.get("/api/v1/google/files")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), {"files": []})
        with self.Session() as db:
            connection = db.query(GoogleConnection).one()
            self.assertGreater(connection.access_token_expires_at.replace(tzinfo=timezone.utc),
                               datetime.now(timezone.utc))

    def test_google_403_has_actionable_reason(self):
        result = httpx.Response(403, json={"error": {"details": [{"reason": "SERVICE_DISABLED"}]}})
        error = drive_error(result, "file listing")
        self.assertEqual(error.status_code, 403)
        self.assertIn("Enable the Google Drive API", error.detail)

    def test_gmail_draft_uses_central_file_without_personal_drive_copy(self):
        self.register()
        self.connect_google()
        file_id = self.client.post("/api/v1/files", headers=ORIGIN,
                                   files={"file": ("note.txt", b"content", "text/plain")}).json()["id"]
        self.assertEqual(self.client.post(f"/api/v1/files/{file_id}/gmail-draft", headers=ORIGIN,
                                          json={"email": "invalid"}).status_code, 422)
        draft = AsyncMock(return_value="draft-2")
        with patch("app.files.upload_bytes") as upload, patch("app.files.create_gmail_draft", draft):
            created = self.client.post(f"/api/v1/files/{file_id}/gmail-draft", headers=ORIGIN,
                                       json={"email": "friend@gmail.com"})
        self.assertEqual(created.status_code, 200)
        upload.assert_not_called()
        draft.assert_awaited_once_with("google-access", "friend@gmail.com", "note.txt",
                                       "text/plain", b"content")

    def test_existing_drive_connection_requires_gmail_reconsent(self):
        self.register()
        self.connect_google()
        file_id = self.client.post("/api/v1/files", headers=ORIGIN,
                                   files={"file": ("note.txt", b"content", "text/plain")}).json()["id"]
        with self.Session() as db:
            connection = db.query(GoogleConnection).one()
            connection.granted_scopes = "openid email https://www.googleapis.com/auth/drive.file"
            db.commit()
        self.assertFalse(self.client.get("/api/v1/google/status").json()["gmail_ready"])
        with patch("app.files.create_gmail_draft") as draft:
            response = self.client.post(f"/api/v1/files/{file_id}/gmail-draft", headers=ORIGIN,
                                        json={"email": "friend@gmail.com"})
        self.assertEqual(response.status_code, 409)
        draft.assert_not_called()

    def test_gmail_draft_contains_attachment_and_is_not_sent(self):
        calls = {}

        class FakeDraftClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def post(self, url, **kwargs):
                calls.update(url=url, **kwargs)
                return httpx.Response(200, json={"id": "draft-1"})

        with patch("app.google.httpx.AsyncClient", return_value=FakeDraftClient()):
            draft_id = asyncio.run(create_gmail_draft("access-token", "friend@gmail.com",
                                                      "note.txt", "text/plain", b"content"))
        self.assertEqual(draft_id, "draft-1")
        self.assertTrue(calls["url"].endswith("/users/me/drafts"))
        message = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(calls["json"]["message"]["raw"]))
        self.assertEqual(message["To"], "friend@gmail.com")
        attachment = next(message.iter_attachments())
        self.assertEqual(attachment.get_filename(), "note.txt")
        self.assertEqual(attachment.get_payload(decode=True), b"content")

    def test_storage_token_folder_and_download_use_central_account(self):
        encrypted = Fernet(os.environ["GOOGLE_TOKEN_ENCRYPTION_KEY"].encode()).encrypt(
            b"root-refresh").decode()
        calls = []

        class FakeStorageClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def post(self, url, **kwargs):
                calls.append(("post", url, kwargs))
                if url.endswith("/token"):
                    return httpx.Response(200, json={"access_token": "root-access"})
                return httpx.Response(200, json={"id": "folder-1"})

            async def get(self, url, **kwargs):
                calls.append(("get", url, kwargs))
                return httpx.Response(200, content=b"central bytes")

        with patch.dict(os.environ, {"STORAGE_GOOGLE_REFRESH_TOKEN_CIPHERTEXT": encrypted}), \
             patch("app.storage.httpx.AsyncClient", return_value=FakeStorageClient()):
            self.assertEqual(asyncio.run(storage_access_token()), "root-access")
            self.assertEqual(asyncio.run(create_user_folder("root-access", "app-folder", "user-1")),
                             "folder-1")
            self.assertEqual(asyncio.run(read_storage_file("root-access", "file-1")), b"central bytes")
        self.assertEqual(calls[0][2]["data"]["refresh_token"], "root-refresh")
        self.assertEqual(calls[1][2]["json"]["parents"], ["app-folder"])
        self.assertEqual(calls[2][2]["params"], {"alt": "media"})

    def test_central_upload_sets_user_folder_parent(self):
        calls = {}

        class FakeUploadClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def post(self, url, **kwargs):
                calls.update(url=url, **kwargs)
                return httpx.Response(200, json={"id": "root-file"})

        with patch("app.google.httpx.AsyncClient", return_value=FakeUploadClient()):
            self.assertEqual(asyncio.run(upload_bytes("root-access", "note.txt", "text/plain",
                                                   b"content", parent_id="user-folder")), "root-file")
        self.assertIn(b'"parents": ["user-folder"]', calls["content"])
        self.assertTrue(calls["url"].endswith("/upload/drive/v3/files"))


if __name__ == "__main__":
    unittest.main()
