
"""
Google OAuth 2.0 configuration for File Vault.

This module defines and validates configuration only.

It does NOT:
- Start an OAuth authorization flow
- Exchange authorization codes
- Make Google API requests
- Store or decrypt Google tokens
"""

import base64
import binascii
import os

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


# --------------------------------------------------
# Environment
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


# --------------------------------------------------
# Google OAuth endpoints
# --------------------------------------------------

GOOGLE_AUTHORIZATION_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

GOOGLE_TOKEN_URL = (
    "https://oauth2.googleapis.com/token"
)


# --------------------------------------------------
# Minimal initial permissions
# --------------------------------------------------

GOOGLE_DRIVE_SCOPES = (
    "https://www.googleapis.com/auth/drive.file",
)


# Expected local development callback.
DEFAULT_GOOGLE_REDIRECT_URI = (
    "http://localhost:8000/api/v1/google/callback"
)


# --------------------------------------------------
# Configuration helpers
# --------------------------------------------------

def required_environment_variable(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} is not configured"
        )

    return value


def validate_redirect_uri(uri: str) -> str:
    """
    Require an absolute HTTP(S) callback URL.

    HTTP is allowed only for localhost/loopback
    during development.
    """

    parsed = urlsplit(uri)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            "Google redirect URI must use HTTP or HTTPS"
        )

    if not parsed.hostname:
        raise ValueError(
            "Google redirect URI must have a hostname"
        )

    if parsed.username or parsed.password:
        raise ValueError(
            "Redirect URI must not contain credentials"
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Google redirect URI contains an invalid port"
        ) from exc

    if parsed.scheme == "http":
        if parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError(
                "HTTP redirect URI is only allowed "
                "for local development"
            )

    if parsed.query or parsed.fragment:
        raise ValueError(
            "Redirect URI must not contain a query "
            "or fragment"
        )

    if not parsed.path.startswith("/api/v1/google/"):
        raise ValueError(
            "Redirect URI must use the Google "
            "callback route"
        )

    if parsed.path != "/api/v1/google/callback":
        raise ValueError(
            "Unsupported Google callback path"
        )

    # Explicitly reject malformed ports where relevant.
    _ = port

    return uri


def validate_encryption_key(key: str) -> str:
    """
    Validate a Fernet-compatible key.

    Fernet uses 32 random bytes encoded with
    URL-safe Base64.

    This function does not perform encryption.
    """

    try:
        decoded = base64.b64decode(
            key.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (
        ValueError,
        UnicodeEncodeError,
        binascii.Error,
    ) as exc:
        raise ValueError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY must be "
            "a valid URL-safe Base64 string"
        ) from exc

    if len(decoded) != 32:
        raise ValueError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY must encode "
            "exactly 32 bytes"
        )

    return key


# --------------------------------------------------
# Validated settings
# --------------------------------------------------

@dataclass(frozen=True)
class GoogleOAuthSettings:
    client_id: str

    client_secret: str = field(repr=False)

    redirect_uri: str

    token_encryption_key: str = field(repr=False)

    authorization_url: str = GOOGLE_AUTHORIZATION_URL

    token_url: str = GOOGLE_TOKEN_URL

    scopes: tuple[str, ...] = GOOGLE_DRIVE_SCOPES

    access_type: str = "offline"

    code_challenge_method: str = "S256"

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise ValueError(
                "Google client ID cannot be empty"
            )

        if not self.client_secret.strip():
            raise ValueError(
                "Google client secret cannot be empty"
            )

        validate_redirect_uri(self.redirect_uri)

        validate_encryption_key(
            self.token_encryption_key
        )

        if not self.scopes:
            raise ValueError(
                "At least one OAuth scope is required"
            )


# --------------------------------------------------
# Load configuration when explicitly requested
# --------------------------------------------------

def get_google_oauth_settings() -> GoogleOAuthSettings:
    """
    Load and validate Google OAuth settings.

    Loading is lazy so File Vault's existing
    authentication and file endpoints can start
    even before Google OAuth is configured.
    """

    return GoogleOAuthSettings(
        client_id=required_environment_variable(
            "GOOGLE_CLIENT_ID"
        ),
        client_secret=required_environment_variable(
            "GOOGLE_CLIENT_SECRET"
        ),
        redirect_uri=os.getenv(
            "GOOGLE_REDIRECT_URI",
            DEFAULT_GOOGLE_REDIRECT_URI,
        ).strip(),
        token_encryption_key=required_environment_variable(
            "GOOGLE_TOKEN_ENCRYPTION_KEY"
        ),
    )
