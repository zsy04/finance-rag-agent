import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from routers.tax import router as tax_router
from routers.social import router as social_router
from routers.chat import router as chat_router
from routers.form import router as form_router
from routers.library import router as library_router

app = FastAPI(title="财税助手api", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tax_router)
app.include_router(social_router)
app.include_router(chat_router)
app.include_router(form_router)
app.include_router(library_router)

@app.get("/health")
async def health():
    deps = {}
    # Qdrant 探测（轻量，只检查连通性）
    try:
        from qdrant_client import QdrantClient
        from config import QDRANT_URL
        qdrant = QdrantClient(url=QDRANT_URL, timeout=2)
        qdrant.get_collections()
        deps["qdrant"] = "ok"
    except Exception:
        deps["qdrant"] = "unreachable"
    # DeepSeek API 探测
    try:
        from config import DEEPSEEK_API_KEY
        deps["deepseek"] = "ok" if DEEPSEEK_API_KEY else "not_configured"
    except Exception:
        deps["deepseek"] = "unknown"
    return {"status": "ok", "deps": deps}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)