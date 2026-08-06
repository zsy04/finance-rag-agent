import os
from pathlib import Path
from dotenv import load_dotenv

# 明确指定 .env 路径（避免 CWD 不同导致找不到）
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()  # 回退到 CWD 搜索（Docker 中环境变量直接注入）

#----------API-------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# 模型：DeepSeek V4 Flash（2026-07-24 后 deepseek-chat 已弃用，统一用 deepseek-v4-flash）
# 可通过环境变量 DEEPSEEK_MODEL 覆盖（如切换其他模型）
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
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
# 嵌入设备：auto(自动检测GPU优先) / cpu(强制CPU) / cuda(强制GPU)
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "auto")

#----------路径-----------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "rag-data"/"processed"
BACKEND_DIR = Path(__file__).parent

#----------存储（用户上下文持久化 §5.1）-----------
# SQLite 数据库路径：标准库零依赖，演示零风险；多进程部署时换 MongoDB（仅换实现类）
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(BACKEND_DIR / "data" / "chat.db"))

# ── Agent 模式开关（v1.2）──
# "multi"：子 Agent 形态（计税/社保由 tax_subagent / social_subagent 处理，演示默认）
# "tools"：纯工具形态（原 8 工具，回退保底 / 演示单 vs 多 Agent 对比）
AGENT_MODE = os.getenv("AGENT_MODE", "multi")