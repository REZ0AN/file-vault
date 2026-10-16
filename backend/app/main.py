from fastapi import FastAPI

app = FastAPI(
    title="File Vault API",
    description="Secure file storage with Google integration",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "file-vault-api",
    }
