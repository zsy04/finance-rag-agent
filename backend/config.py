import os
from pathlib import Path
from dotenv import load_dotenv

# 明确指定 .env 路径（避免 CWD 不同导致找不到）
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

#----------API-------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = "deepseek-chat"

#----------Qdrant-----------
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "finance_knowledge"

#----------模型-----------
BGE_MODEL_PATH = "BAAI/bge-m3"
RERANKER_MODEL_PATH = "BAAI/bge-reranker-v2-m3"

#----------路径-----------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "rag-data"/"processed"
BACKEND_DIR = Path(__file__).parent