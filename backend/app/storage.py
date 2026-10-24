"""Central Drive account used only as File Vault's backing store."""

import os
from urllib.parse import quote

import httpx
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

from app.google import FILES_URL, TOKEN_URL
from app.session import cipher


def root_folder_id() -> str:
    folder_id = os.getenv("STORAGE_GOOGLE_ROOT_FOLDER_ID", "").strip()
    if not folder_id:
        raise HTTPException(503, "Central Drive storage is not configured")
    return folder_id


async def storage_access_token() -> str:
    encrypted = os.getenv("STORAGE_GOOGLE_REFRESH_TOKEN_CIPHERTEXT", "").strip()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not encrypted or not client_id or not client_secret:
        raise HTTPException(503, "Central Drive storage is not configured")
    try:
        refresh = cipher().decrypt(encrypted.encode()).decode()
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(TOKEN_URL, data={
                "client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh, "grant_type": "refresh_token",
            })
        tokens = result.json()
    except (httpx.HTTPError, ValueError, InvalidToken):
        raise HTTPException(502, "Central Drive storage is unavailable") from None
    if result.status_code != 200 or not tokens.get("access_token"):
        raise HTTPException(503, "Central Drive authorization expired; reconnect the storage account")
    return tokens["access_token"]


async def create_user_folder(token: str, parent_id: str, user_id: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            result = await client.post(FILES_URL,
                                       headers={"Authorization": f"Bearer {token}"},
                                       params={"fields": "id"},
                                       json={"name": user_id,
                                             "mimeType": "application/vnd.google-apps.folder",
                                             "parents": [parent_id]})
    except httpx.HTTPError:
        raise HTTPException(502, "Could not create a central Drive folder") from None
    if result.status_code not in (200, 201):
        raise HTTPException(502, "Central Drive rejected folder creation")
    folder_id = result.json().get("id")
    if not isinstance(folder_id, str) or not folder_id:
        raise HTTPException(502, "Central Drive did not return a folder ID")
    return folder_id


async def read_storage_file(token: str, file_id: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            result = await client.get(f"{FILES_URL}/{quote(file_id, safe='')}",
                                      params={"alt": "media"},
                                      headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        raise HTTPException(502, "Could not read the file from central Drive") from None
    if result.status_code != 200:
        raise HTTPException(502, "Central Drive could not return the file")
    return result.content
