
from fastapi import FastAPI

from app.routes.auth import router as auth_router
from app.routes.files import router as files_router


# Main FastAPI application
app = FastAPI(
    title="File Vault API",
    description="Secure file storage with Google integration",
    version="1.0.0",
)


# Register authentication endpoints
app.include_router(
    auth_router,
    prefix="/api/v1",
)


# Register file endpoints
app.include_router(
    files_router,
    prefix="/api/v1",
)


# Application health check
@app.get(
    "/health",
    tags=["Health"],
)
async def health_check():
    return {
        "status": "healthy",
        "service": "file-vault-api",
    }
