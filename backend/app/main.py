
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.auth import router as auth_router
from app.routes.files import router as files_router


app = FastAPI(
    title="File Vault API",
    description="Secure file storage with Google integration",
    version="1.0.0",
)


# Allow requests from our Next.js development frontend.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
    ],
)


# Authentication routes:
# /api/v1/auth/register
# /api/v1/auth/login
# /api/v1/auth/me
app.include_router(
    auth_router,
    prefix="/api/v1",
)


# File routes:
# POST /api/v1/files
# GET  /api/v1/files
# GET  /api/v1/files/{file_id}/download
app.include_router(
    files_router,
    prefix="/api/v1",
)


@app.get(
    "/health",
    tags=["Health"],
)
async def health_check():
    return {
        "status": "healthy",
        "service": "file-vault-api",
    }
