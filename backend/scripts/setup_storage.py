"""One-time local OAuth setup for the unregistered central Drive account."""

import argparse
import base64
import hashlib
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
REDIRECT_URI = "http://127.0.0.1:8765/callback"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize a separate Drive storage account")
    parser.add_argument("--folder-name", default="file-vault", help="Top-level Drive folder to create")
    args = parser.parse_args()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    key = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    if not all((client_id, client_secret, key)):
        parser.error("Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_TOKEN_ENCRYPTION_KEY in backend/.env")
    cipher = Fernet(key.encode())
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    result: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            if parsed.path != "/callback" or params.get("state", [""])[0] != state:
                self.send_error(400, "Invalid OAuth callback")
                return
            result["code"] = params.get("code", [""])[0]
            result["error"] = params.get("error", [""])[0]
            body = b"<h1>Storage account setup received</h1><p>Return to the terminal.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT_URI, "response_type": "code",
        "scope": DRIVE_SCOPE, "access_type": "offline", "prompt": "consent",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    with HTTPServer(("127.0.0.1", 8765), Callback) as server:
        server.timeout = 5
        print("Choose the separate Google account that will own all stored files.")
        print("Opening Google authorization in your browser. If needed, open:", auth_url)
        webbrowser.open(auth_url)
        deadline = time.monotonic() + 180
        while "code" not in result and "error" not in result and time.monotonic() < deadline:
            server.handle_request()
    if result.get("error") or not result.get("code"):
        raise SystemExit("Google authorization failed or timed out")

    with httpx.Client(timeout=15) as client:
        exchanged = client.post("https://oauth2.googleapis.com/token", data={
            "code": result["code"], "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
            "code_verifier": verifier,
        })
        tokens = exchanged.json()
        if exchanged.status_code != 200 or not tokens.get("refresh_token") or DRIVE_SCOPE not in tokens.get("scope", "").split():
            raise SystemExit("Google did not grant offline Drive access. Re-run setup and approve Drive.")
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        about = client.get("https://www.googleapis.com/drive/v3/about",
                           headers=headers, params={"fields": "user(emailAddress)"})
        if about.status_code != 200:
            raise SystemExit("Could not confirm the storage account email")
        email = about.json().get("user", {}).get("emailAddress", "").lower()
        expected_email = os.getenv("STORAGE_GOOGLE_ACCOUNT_EMAIL", "").strip().lower()
        if not email or (expected_email and email != expected_email):
            raise SystemExit("A different storage account was selected")
        folder_id = os.getenv("STORAGE_GOOGLE_ROOT_FOLDER_ID", "").strip()
        if folder_id:
            folder = client.get(f"https://www.googleapis.com/drive/v3/files/{quote(folder_id, safe='')}",
                                headers=headers, params={"fields": "id,mimeType,trashed"})
            if (folder.status_code != 200 or folder.json().get("mimeType") != "application/vnd.google-apps.folder"
                    or folder.json().get("trashed")):
                raise SystemExit("Existing root folder is unavailable; check the selected account and folder ID")
        else:
            folder = client.post("https://www.googleapis.com/drive/v3/files", headers=headers,
                                 params={"fields": "id"},
                                 json={"name": args.folder_name,
                                       "mimeType": "application/vnd.google-apps.folder"})
            if folder.status_code not in (200, 201) or not folder.json().get("id"):
                raise SystemExit("Could not create the app folder in central Drive")
            folder_id = folder.json()["id"]

    encrypted = cipher.encrypt(tokens["refresh_token"].encode()).decode()
    print("\nAdd these to backend/.env; keep the token private:")
    print(f"STORAGE_GOOGLE_ACCOUNT_EMAIL={email}")
    print(f"STORAGE_GOOGLE_ROOT_FOLDER_ID={folder_id}")
    print(f"STORAGE_GOOGLE_REFRESH_TOKEN_CIPHERTEXT={encrypted}")


if __name__ == "__main__":
    main()
