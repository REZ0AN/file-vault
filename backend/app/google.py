"""Google sign-in, encrypted Drive credentials, and Drive file APIs."""

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, optional_user, set_auth_cookie
from app.database import get_db
from app.models import GoogleConnection, User
from app.session import (
    STATE_AGE, STATE_COOKIE, STATE_PATH, cipher, read_cookie,
    require_frontend_origin, secure_cookies, write_cookie,
)

router = APIRouter()
logger = logging.getLogger(__name__)
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
GOOGLE_KEYS = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")


def settings() -> tuple[str, str, str]:
    values = tuple(os.getenv(name, "").strip() for name in (
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI",
    ))
    if not all(values):
        raise HTTPException(503, "Google OAuth is not configured")
    return values[0], values[1], values[2]


def frontend_url(error: str = "", *, dashboard: bool = False) -> str:
    base = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
    path = "/dashboard" if dashboard or not error else "/"
    return f"{base}{path}?{urlencode({'error': error})}" if error else f"{base}{path}"


def callback_redirect(message: str, response_user: User | None = None,
                      *, linking: bool = False) -> RedirectResponse:
    response = RedirectResponse(frontend_url(message, dashboard=linking))
    response.delete_cookie(STATE_COOKIE, path=STATE_PATH, secure=secure_cookies(),
                           httponly=True, samesite="lax")
    if response_user:
        set_auth_cookie(response, response_user)
    return response


def verify_google_identity(id_token: str, client_id: str, nonce: str) -> tuple[str, str]:
    """Verify Google's signature, issuer, audience, expiry, and nonce."""
    key = GOOGLE_KEYS.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token, key.key, algorithms=["RS256"], audience=client_id,
        issuer=["https://accounts.google.com", "accounts.google.com"],
        options={"require": ["sub", "email", "email_verified", "exp", "iss", "aud", "nonce"]},
    )
    if not secrets.compare_digest(str(claims["nonce"]), nonce):
        raise jwt.InvalidTokenError("Google nonce mismatch")
    if claims["email_verified"] not in (True, "true"):
        raise jwt.InvalidTokenError("Google email is not verified")
    subject = claims["sub"]
    email = claims["email"]
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise jwt.InvalidTokenError("Invalid Google subject")
    if not isinstance(email, str) or not email or len(email) > 255:
        raise jwt.InvalidTokenError("Invalid Google email")
    return subject, email.lower()


@router.get("/connect")
def connect(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    client_id, _, redirect_uri = settings()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": f"openid email {DRIVE_SCOPE} {GMAIL_SCOPE}", "access_type": "offline", "prompt": "consent",
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    user = optional_user(request, db)
    response = RedirectResponse(f"{AUTH_URL}?{urlencode(params)}")
    write_cookie(response, STATE_COOKIE, {
        "state": state, "verifier": verifier, "nonce": nonce,
        "link_user_id": str(user.id) if user else None,
    }, STATE_AGE, STATE_PATH)
    return response


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    pending = read_cookie(request, STATE_COOKIE, STATE_AGE)
    linking = bool(pending and pending.get("link_user_id"))
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not pending or not state or not secrets.compare_digest(str(pending.get("state", "")), state):
        return callback_redirect("OAuth state check failed. Start again.", linking=linking)
    if request.query_params.get("error") or not code:
        return callback_redirect("Google authorization was cancelled.", linking=linking)

    client_id, client_secret, redirect_uri = settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(TOKEN_URL, data={
                "code": code, "client_id": client_id, "client_secret": client_secret,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code",
                "code_verifier": pending["verifier"],
            })
        tokens = result.json()
        if result.status_code != 200 or not tokens.get("access_token") or not tokens.get("id_token"):
            return callback_redirect("Google token exchange failed.", linking=linking)
        if DRIVE_SCOPE not in tokens.get("scope", "").split():
            return callback_redirect("Google Drive permission was not granted.", linking=linking)
        if GMAIL_SCOPE not in tokens.get("scope", "").split():
            return callback_redirect("Gmail draft permission was not granted.", linking=linking)
        subject, email = await run_in_threadpool(
            verify_google_identity, tokens["id_token"], client_id, pending["nonce"]
        )
        if email == os.getenv("STORAGE_GOOGLE_ACCOUNT_EMAIL", "").strip().lower():
            return callback_redirect("The central storage account cannot sign in.", linking=linking)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError):
        return callback_redirect("Google identity verification failed.", linking=linking)

    try:
        existing_subject = db.scalar(select(GoogleConnection).where(GoogleConnection.google_subject == subject))
        link_id = pending.get("link_user_id")
        if link_id:
            user = db.get(User, uuid.UUID(link_id))
            if user is None or (existing_subject and existing_subject.user_id != user.id):
                return callback_redirect("This Google account belongs to another user.", linking=linking)
        elif existing_subject:
            user = db.get(User, existing_subject.user_id)
        else:
            # Never merge accounts merely because their email addresses match.
            if db.scalar(select(User.id).where(func.lower(User.email) == email)):
                return callback_redirect("Sign in with your password, then connect Google from the dashboard.")
            user = User(email=email, password_hash=None)
            db.add(user)
            db.flush()

        connection = db.scalar(select(GoogleConnection).where(GoogleConnection.user_id == user.id))
        if connection and connection.google_subject not in (None, subject):
            return callback_redirect("A different Google account is already linked.", linking=linking)
        if connection is None:
            connection = GoogleConnection(user_id=user.id, granted_scopes="")
            db.add(connection)

        refresh = tokens.get("refresh_token")
        if not refresh and connection.refresh_token_ciphertext:
            refresh = cipher().decrypt(connection.refresh_token_ciphertext).decode()
        if not refresh:
            db.rollback()
            return callback_redirect("Google did not provide a refresh token. Reconnect and consent.", linking=linking)
        connection.google_subject = subject
        connection.google_email = email
        connection.access_token_ciphertext = cipher().encrypt(tokens["access_token"].encode())
        connection.refresh_token_ciphertext = cipher().encrypt(refresh.encode())
        connection.granted_scopes = tokens["scope"]
        connection.access_token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(tokens.get("expires_in", 3600))
        )
        db.commit()
    except (IntegrityError, ValueError):
        db.rollback()
        return callback_redirect("Account linking conflicted. Please retry.", linking=linking)
    return callback_redirect("", user)


def connection_for(user: User, db: Session) -> GoogleConnection:
    connection = db.scalar(select(GoogleConnection).where(GoogleConnection.user_id == user.id))
    if not connection or not connection.refresh_token_ciphertext:
        raise HTTPException(409, "Connect Google Drive first")
    return connection


@router.get("/status")
def status(user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    connection = db.scalar(select(GoogleConnection).where(GoogleConnection.user_id == user.id))
    connected = bool(connection and connection.refresh_token_ciphertext)
    return {"connected": connected, "email": connection.google_email if connected else None,
            "gmail_ready": bool(connected and GMAIL_SCOPE in connection.granted_scopes.split())}


@router.post("/disconnect")
def disconnect(request: Request, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, bool]:
    require_frontend_origin(request)
    connection = db.scalar(select(GoogleConnection).where(GoogleConnection.user_id == user.id))
    if connection:
        connection.access_token_ciphertext = None
        connection.refresh_token_ciphertext = None
        connection.access_token_expires_at = None
        db.commit()
    return {"connected": False}


async def access_token(user: User, db: Session, required_scope: str = DRIVE_SCOPE) -> str:
    connection = connection_for(user, db)
    if required_scope not in connection.granted_scopes.split():
        raise HTTPException(409, "Reconnect Google and grant Gmail draft access")
    now = datetime.now(timezone.utc)
    expiry = connection.access_token_expires_at
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if (connection.access_token_ciphertext and expiry
            and expiry > now + timedelta(seconds=60)):
        return cipher().decrypt(connection.access_token_ciphertext).decode()
    client_id, client_secret, _ = settings()
    try:
        refresh = cipher().decrypt(connection.refresh_token_ciphertext).decode()
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(TOKEN_URL, data={
                "client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh, "grant_type": "refresh_token",
            })
        tokens = result.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Could not refresh Google access") from None
    if result.status_code != 200 or not tokens.get("access_token"):
        raise HTTPException(401, "Google access expired. Connect again.")
    connection.access_token_ciphertext = cipher().encrypt(tokens["access_token"].encode())
    if tokens.get("refresh_token"):
        connection.refresh_token_ciphertext = cipher().encrypt(tokens["refresh_token"].encode())
    connection.access_token_expires_at = now + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    db.commit()
    return tokens["access_token"]


def drive_error(result: httpx.Response, action: str) -> HTTPException:
    reason = "unknown"
    try:
        error = result.json()["error"]
        if error.get("errors"):
            reason = error["errors"][0]["reason"]
        elif error.get("details"):
            reason = error["details"][0]["reason"]
    except (ValueError, AttributeError, KeyError, IndexError, TypeError):
        pass
    if not isinstance(reason, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", reason):
        reason = "unknown"
    logger.warning("Google Drive %s failed: HTTP %s reason=%s", action, result.status_code, reason)
    if result.status_code == 401:
        return HTTPException(401, "Google access expired. Connect again.")
    if result.status_code == 403:
        advice = {
            "accessNotConfigured": "Enable the Google Drive API in your Google Cloud project.",
            "SERVICE_DISABLED": "Enable the Google Drive API in your Google Cloud project.",
            "insufficientPermissions": "Reconnect Google and grant Drive access.",
            "ACCESS_TOKEN_SCOPE_INSUFFICIENT": "Reconnect Google and grant Drive access.",
            "domainPolicy": "Your Workspace administrator blocks this app.",
            "rateLimitExceeded": "Google Drive rate limit reached. Try again later.",
            "userRateLimitExceeded": "Google Drive rate limit reached. Try again later.",
            "dailyLimitExceeded": "Google Drive daily quota reached.",
        }.get(reason, f"Google denied {action} (reason: {reason}).")
        return HTTPException(403, advice)
    return HTTPException(502, f"Google Drive {action} failed.")


@router.get("/files")
async def list_drive_files(user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    token = await access_token(user, db)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            result = await client.get(FILES_URL, headers={"Authorization": f"Bearer {token}"}, params={
                "q": "trashed = false", "pageSize": 100,
                "fields": "files(id,name,webViewLink),nextPageToken",
            })
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Google Drive") from None
    if result.status_code != 200:
        raise drive_error(result, "file listing")
    return result.json()


async def upload_bytes(token: str, filename: str, mime: str, content: bytes,
                       parent_id: str | None = None) -> str:
    boundary = secrets.token_hex(16)
    metadata = {"name": filename}
    if parent_id:
        metadata["parents"] = [parent_id]
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + json.dumps(metadata).encode()
        + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()
        + content + f"\r\n--{boundary}--\r\n".encode()
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            result = await client.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "multipart", "fields": "id"},
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": f"multipart/related; boundary={boundary}"},
                content=body,
            )
    except httpx.HTTPError:
        raise HTTPException(502, "Upload timed out. Check Drive before retrying.") from None
    if result.status_code != 200:
        raise drive_error(result, "upload")
    file_id = result.json().get("id")
    if not isinstance(file_id, str) or not file_id:
        raise HTTPException(502, "Google did not return a file ID")
    return file_id


async def create_gmail_draft(token: str, recipient: str, filename: str,
                             mime: str, content: bytes) -> str:
    """Create an unsent Gmail draft with the stored file as an attachment."""
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = f"File: {filename.replace(chr(13), ' ').replace(chr(10), ' ')}"
    message.set_content("I've attached the file for you.\n")
    media_type = mime.split(";", 1)[0].strip().split("/", 1)
    if len(media_type) != 2 or not all(re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+", part)
                                            for part in media_type):
        media_type = ["application", "octet-stream"]
    message.add_attachment(content, maintype=media_type[0], subtype=media_type[1],
                           filename=filename.replace("\r", "_").replace("\n", "_"))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            result = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": {"raw": raw}},
            )
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Gmail. Check Drafts before retrying.") from None
    if result.status_code not in (200, 201):
        if result.status_code in (401, 403):
            raise HTTPException(403, "Gmail denied draft creation. Reconnect Google and grant Gmail access.")
        raise HTTPException(502, "Gmail could not create the draft")
    draft = result.json()
    draft_id = draft.get("id")
    if not isinstance(draft_id, str) or not draft_id:
        raise HTTPException(502, "Gmail did not confirm the draft. Check Drafts before retrying.")
    return draft_id
