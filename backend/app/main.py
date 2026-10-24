"""File Vault API: local identity, central storage, and personal Google actions."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.files import router as files_router
from app.google import router as google_router

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")

app = FastAPI(title="File Vault API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(files_router, prefix="/api/v1/files")
app.include_router(google_router, prefix="/api/v1/google")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
