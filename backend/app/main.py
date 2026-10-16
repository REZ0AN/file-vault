from fastapi import FastAPI
from app.routes.auth import router as auth_router
app = FastAPI(
    title="File Vault API",
    description="Secure file storage with Google integration",
    version="1.0.0",
)

app.include_router(auth_router,prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "file-vault-api",
    }
