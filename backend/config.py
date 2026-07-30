import os
from pathlib import Path
from dotenv import load_dotenv

# 明确指定 .env 路径（避免 CWD 不同导致找不到）
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

#----------API-------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = "deepseek-chat"
if not DEEPSEEK_API_KEY:
    raise RuntimeError(
        "DEEPSEEK_API_KEY 未配置。请在 backend/.env 中设置 DEEPSEEK_API_KEY=sk-xxxx"
    )

#----------Qdrant-----------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "finance_knowledge")

#----------CORS-----------
# 逗号分隔的允许来源列表，默认仅本地开发
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

#----------模型-----------
BGE_MODEL_PATH = "BAAI/bge-m3"
RERANKER_MODEL_PATH = "BAAI/bge-reranker-v2-m3"

#----------路径-----------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "rag-data"/"processed"
BACKEND_DIR = Path(__file__).parent