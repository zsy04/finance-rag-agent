# 财务 RAG Agent · 后端开发路线图

> **面向**：自己动手编码 | **技术栈**：FastAPI + LangChain `create_agent` + LangGraph + DeepSeek V4 Flash | **文档链**：→ `财务RAG-技术架构与Agent方案.md` + `财务RAG-开发注意事项.md`
> **前置**：资料收集完成（`rag-data/processed/` 就绪）、Docker Qdrant 已装

---

## 开发总览（7 步，按依赖顺序）

```
Step 1: 项目骨架     →  FastAPI 跑起来 + 依赖装好
Step 2: 数据引擎     →  JSON 税率表 + 社保/个税计算函数（纯 Python，无 LLM）
Step 3: 向量化入库   →  MD 切分 → BGE-M3 编码 → Qdrant 写入
Step 4: RAG 检索链   →  BGE-M3 检索 + BGE-Reranker 重排
Step 5: 工具集       →  6 个 @tool 函数（对接 Step2 数据 + Step4 检索）
Step 6: Agent 大脑    →  create_agent 调度 + MemorySaver + System Prompt
Step 7: SSE 流式上线  →  StreamingResponse + astream_events → 前端可联调
```

---

## Step 1：项目骨架

### 目标
FastAPI 启动成功 + 所有依赖导入无报错。

### 操作
```bash
mkdir backend && cd backend
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
```

```bash
pip install fastapi uvicorn[standard] sse-starlette
pip install langchain-deepseek langgraph langchain-core langchain
pip install FlagEmbedding qdrant-client pydantic python-dotenv
```

### 文件
```
backend/
├── main.py           # FastAPI 入口
├── config.py         # 环境变量 + 常量
├── requirements.txt
└── .env              # DEEPSEEK_API_KEY=sk-xxx
```

### `config.py`
```python
import os
from dotenv import load_dotenv
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "finance_knowledge"
BGE_MODEL_PATH = "BAAI/bge-m3"
RERANKER_MODEL_PATH = "BAAI/bge-reranker-v2-m3"
```

### `main.py` 最小骨架
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="财税助手 API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health(): return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### ✅ 通过标准
```bash
curl http://localhost:8000/health → {"status": "ok"}
```

---

## Step 2：数据引擎（纯 Python，无 LLM）

### 目标
个税计算和社保计算函数就绪，输入数据 → 输出结构化结果。

### 文件
```
backend/
├── data/
│   ├── tax_rates.json        # 税率表（7 级综合 + 5 级经营 + 预扣率）
│   ├── deductions.json       # 7 项专项附加扣除标准
│   └── cities/
│       └── zhengzhou.json    # 郑州社保比例 + 基数 + 公积金
└── services/
    └── tax_engine.py         # 计算引擎（纯函数）
```

### 数据文件格式示例
`data/tax_rates.json`：
```json
{
  "comprehensive": [
    {"level": 1, "from": 0, "to": 36000, "rate": 0.03, "quick_deduction": 0},
    {"level": 2, "from": 36000, "to": 144000, "rate": 0.10, "quick_deduction": 2520},
    ...
  ]
}
```

`data/cities/zhengzhou.json`：
```json
{
  "city": "郑州", "effective_from": "2025-07-01",
  "social_avg_wage": 6385, "base_min": 3831, "base_max": 19155,
  "pension": {"employer": 0.16, "employee": 0.08},
  "medical": {"employer": 0.07, "employee": 0.02},
  "unemployment": {"employer": 0.007, "employee": 0.003},
  ...
}
```

### `services/tax_engine.py`
```python
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

def load_json(filename: str) -> dict:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

def calculate_comprehensive_tax(
    annual_income: float,
    social_insurance: float = 0,
    special_deductions: float = 0,
) -> dict:
    """综合所得个税计算"""
    rates = load_json("tax_rates.json")["comprehensive"]
    taxable = annual_income - 60000 - social_insurance - special_deductions
    if taxable <= 0:
        return {"taxable_income": 0, "tax_amount": 0, "rate": "0%", "level": 0}

    for bracket in rates:
        if taxable <= bracket["to"] or bracket["to"] is None:
            tax = taxable * bracket["rate"] - bracket["quick_deduction"]
            return {
                "taxable_income": round(taxable, 2),
                "tax_amount": round(max(tax, 0), 2),
                "rate": f"{bracket['rate']*100:.0f}%",
                "level": bracket["level"],
            }
```

### ✅ 通过标准
```python
from services.tax_engine import calculate_comprehensive_tax
result = calculate_comprehensive_tax(annual_income=120000, social_insurance=9888, special_deductions=18000)
assert result["taxable_income"] == 32112
assert result["tax_amount"] == 963.36
```

---

## Step 3：向量化入库

### 目标
`rag-data/processed/` → BGE-M3 编码 → Qdrant collection 创建完毕。

### 前置
- 资料收集完成（`rag-data/processed/` 目录就绪）
- **Docker Desktop 已安装** + Qdrant 镜像已拉取 → `docker compose up -d`（`docker-compose.yml` 在项目根目录）

### 文件
```
backend/
├── ingestion/
│   ├── index.py            # 主摄取脚本
│   └── chunker.py          # MD 文本切分
└── rag/
    └── embedder.py         # BGE-M3 单例（稠密 + 稀疏双编码）
```

### `rag/embedder.py`
```python
from FlagEmbedding import BGEM3FlagModel

class Embedder:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        return cls._instance

    def encode(self, texts: list[str]) -> tuple:
        output = self.model.encode(texts, return_dense=True, return_sparse=True)
        return output["dense_vecs"], output["lexical_weights"]
```

### `ingestion/index.py`（伪代码示意）
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, SparseVectorParams
from rag.embedder import Embedder
from ingestion.chunker import chunk_markdown

client = QdrantClient(url="http://localhost:6333")
embedder = Embedder()

# 创建 collection（同时支持 dense 1024d + sparse）
client.create_collection(
    collection_name="finance_knowledge",
    vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
    sparse_vectors_config={"sparse": SparseVectorParams()},
)

# 遍历 processed/ 下的 MD 文件
for md_file in Path("rag-data/processed").rglob("*.md"):
    chunks = chunk_markdown(md_file)  # 800 tokens/chunk
    dense_vecs, sparse_vecs = embedder.encode(chunks)
    # 写入 Qdrant...
```

### ✅ 通过标准
```
curl http://localhost:6333/collections/finance_knowledge → 返回 collection 信息，点数 > 0
```

---

## Step 4：RAG 检索链

### 目标
`query → BGE-M3 → Qdrant 混合检索 Top-20 → BGE-Reranker 精排 Top-5` 可复用调用。

### 文件
```
backend/rag/
├── embedder.py    # Step 3 已建
├── retriever.py   # 混合检索
└── reranker.py    # 精排
```

### `rag/retriever.py`
```python
from qdrant_client import QdrantClient
from qdrant_client.models import SearchRequest
from rag.embedder import Embedder
from config import QDRANT_URL, QDRANT_COLLECTION

client = QdrantClient(url=QDRANT_URL)
embedder = Embedder()

def hybrid_search(query: str, top_k: int = 20) -> list[dict]:
    dense, sparse = embedder.encode([query])
    results = client.search_batch(
        collection_name=QDRANT_COLLECTION,
        requests=[
            SearchRequest(vector={"name": "dense", "vector": dense[0].tolist()}, limit=top_k),
            SearchRequest(vector={"name": "sparse", "vector": sparse[0]}, limit=top_k),
        ],
    )
    # RRF 融合两个排序结果
    return rrf_fusion(results, top_k)
```

### `rag/reranker.py`
```python
from FlagEmbedding import FlagReranker

class Reranker:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
        return cls._instance

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        pairs = [[query, c["content"]] for c in candidates]
        scores = self.model.compute_score(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [c for c, _ in ranked[:top_k]]
```

### ✅ 通过标准
```python
results = hybrid_search("租房扣除标准")
assert len(results) == 20
reranked = reranker.rerank("租房扣除标准", results)
assert len(reranked) == 5
assert reranked[0]["score"] > 0.5
```

---

## Step 5：工具集（6 个 `@tool`）

### 目标
6 个 LangChain Tool 就绪，可被 Agent 调用，返回结构化结果。

### 文件
```
backend/tools/
├── base.py             # 共享工具函数（SSE yield helper 等）
├── search_knowledge.py # 工具 1：RAG 检索
├── calculate_tax.py    # 工具 2：个税计算
├── query_social.py     # 工具 3：社保查询
├── fill_form.py        # 工具 4：申报材料生成
├── filing_guide.py     # 工具 5：申报流程指引
└── search_website.py   # 工具 6：白名单搜索
```

### 工具模板
```python
from langchain_core.tools import tool

@tool
def search_knowledge(query: str) -> str:
    """搜索财税知识库。query: 用户的财税问题原文"""
    from rag.retriever import hybrid_search
    from rag.reranker import Reranker
    results = hybrid_search(query)
    reranker = Reranker()
    top = reranker.rerank(query, results)
    return json.dumps([{"content": r["content"], "source": r["source_url"]} for r in top], ensure_ascii=False)

@tool
def calculate_income_tax(annual_income: float, city: str,
                          housing_rent: float = 0, children_edu: float = 0,
                          elderly_support: float = 0) -> str:
    """计算综合所得个人所得税。
    annual_income: 年收入总额（元）
    city: 所在城市，如'郑州'
    housing_rent: 租房月扣除额（默认0）"""
    from services.tax_engine import calculate_comprehensive_tax
    special_deductions = (housing_rent + children_edu + elderly_support) * 12
    result = calculate_comprehensive_tax(annual_income, 9888, special_deductions)
    result["legal_basis"] = "《个人所得税法》附表一；国发〔2023〕13号"
    return json.dumps(result, ensure_ascii=False)

# ... 其余 4 个工具类似
```

### ✅ 通过标准
```python
tool_result = search_knowledge.invoke({"query": "租房扣除标准"})
assert "1500" in tool_result or "1100" in tool_result
```

---

## Step 6：Agent 大脑

### 目标
LLM + 6 个工具 + 对话记忆 = 能自主选择工具、能引导式追问、能流式输出。

### 文件
```
backend/agent/
├── engine.py      # create_agent 调度
└── prompts.py     # System Prompt
```

### `agent/prompts.py`
```python
SYSTEM_PROMPT = """你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。

规则：
1. 信息不足时，先反问 1-2 个问题，每次只问 1-2 个，不要猜测
2. 税率计算和社保计算使用提供的工具，不要自己推算
3. 每个计算结果附带逐步推导过程
4. 涉及金额的回复末尾附上 AI 免责：「⚠️ 本结果由 AI 辅助计算，仅供参考。以税务机关最终核定为准。12366」
5. 使用简洁易懂的语言，专业术语附带解释
6. 回答附带法规引用（法规名 + 文号）"""
```

### `agent/engine.py`
```python
from langchain_deepseek import ChatDeepSeek
from langchain import create_agent
from langgraph.checkpoint.memory import MemorySaver

from agent.prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS

llm = ChatDeepSeek(model="deepseek-v4-flash", temperature=0)
checkpointer = MemorySaver()

agent = create_agent(
    model=llm,
    tools=ALL_TOOLS,          # [search_knowledge, calculate_income_tax, ...]
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)
```

### ✅ 通过标准
```python
config = {"configurable": {"thread_id": "test-1"}}
result = agent.invoke(
    {"messages": [{"role": "user", "content": "郑州工资8000租房，一个月交多少税？"}]},
    config=config
)
# Agent 应该自动调用 calculate_income_tax 工具
assert "税" in result["messages"][-1].content
```

---

## Step 7：SSE 流式上线

### 目标
前端可以通过 `/api/chat` 拿到 SSE 流式响应，8 种事件类型完整。

### `routers/chat.py`
```python
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from agent.engine import agent
import json

router = APIRouter(prefix="/api", tags=["chat"])

@router.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = body["message"]
    context = body.get("context", {})
    thread_id = body.get("thread_id", "default")

    async def generate():
        config = {"configurable": {"thread_id": thread_id}}
        yield f"event: thinking\ndata: {json.dumps({'message': '正在为您处理……'})}\n\n"

        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield f"event: step\ndata: {json.dumps({'content': chunk.content})}\n\n"

        yield f"event: done\ndata: {json.dumps({})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### ✅ 通过标准
```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"房租能抵多少税？"}' 
# 应该看到 event: thinking → event: step → event: done 等流式输出
```

---

## 面试武器库

| Step | 面试能说的点 |
|------|------------|
| 1 | "FastAPI + Async 架构，非阻塞 I/O，SSE 长连接" |
| 2 | "税率计算不走 LLM，用 Pydantic 模型 + JSON 驱动，零幻觉" |
| 3 | "BGE-M3 双向量（稠密 1024d + 稀疏 BM25），Qdrant 原生混合检索" |
| 4 | "双阶段检索：Qdrant RRF 融合初排 20 + BGE-Reranker Cross-encoder 精排 5" |
| 5 | "LangChain @tool 装饰器 + Pydantic 自动生成 JSON Schema，LLM 理解入参" |
| 6 | "create_agent + MemorySaver 实现有状态多轮对话，支持工具自动路由" |
| 7 | "astream_events 实时事件流 → SSE → 前端逐字渲染，端到端延迟 < 500ms" |

---

## 开发注意事项

### 🔴 Critical — API 弃用警告

| 不要用 | 原因 | 用这个 |
|--------|------|--------|
| `create_react_agent` | 已弃用，v1.0 后移除 | `langchain.create_agent()` |
| `model="deepseek-chat"` | **2026-07-24 起弃用** | `model="deepseek-v4-flash"` |
| `model="deepseek-reasoner"` | **同日弃用**，且不支持 Tool Calling | `model="deepseek-v4-flash"` |
| `langgraph.savers.memory.MemorySaver` | v0.2 起路径已变 | `langgraph.checkpoint.memory.MemorySaver` |
| `state["messages"] += [...]` | v0.2+ 强制 reducer | `Annotated[list, operator.add]` |

### 🟡 环境与资源

| 事项 | 说明 |
|------|------|
| **Qdrant Docker 启动顺序** | 必须在 Step 3 之前 `docker-compose up -d`。答辩时提前 5 分钟启动，关掉微信/Chrome 等重应用释放内存 |
| **BGE-M3 首次加载** | 首次 `BGEM3FlagModel("BAAI/bge-m3")` 会从 HuggingFace 下载约 2.2GB 模型文件到 `~/.cache/huggingface/`，需联网。之后秒加载 |
| **BGE-Reranker 同样** | 首次下载约 1.5GB。两个模型总计约 3.7GB |
| **GPU 显存** | BGE-M3 fp16 占用约 2GB，Reranker 约 1.5GB，DeepSeek 走 API 不占显存。RTX 4060 8GB 绰绰有余 |
| **Python 版本** | ≥ 3.10（LangChain 要求）。你已有的 3.13.12 没问题 |
| **.env 文件** | 放在 `backend/.env`，包含 `DEEPSEEK_API_KEY=sk-xxx`。**不要提交到 Git** |

### 🟡 编码陷阱

| 陷阱 | 现象 | 正确做法 |
|------|------|---------|
| `@tool` 函数无类型提示 | Agent 调用时参数乱传 | 每个参数必须有类型注解 + 描述（见 Step 5 模板） |
| `@tool` 函数返回非 str | LangChain 要求工具返回字符串 | 复杂结果用 `json.dumps(result, ensure_ascii=False)` 包一层 |
| `temperature` 设为 > 0 | Agent 偶尔选错工具 | Tool Calling 场景 `temperature=0`，保证确定性 |
| Qdrant collection 未创建 | `search_batch` 报 404 | Step 3 必须先执行 |
| SSE 事件格式不对 | 前端收不到事件 | 格式必须是 `event: xxx\ndata: {...}\n\n`，注意两个换行 |
| `astream_events` 无 `version="v2"` | 事件格式不兼容 | 加 `version="v2"` 参数 |
| 中文 JSON 被转义 | 前端显示 `\uXXXX` | `json.dumps(..., ensure_ascii=False)` |
| Reranker 重复加载 | 每次查询重新初始化模型（巨慢） | 用单例模式（Step 4 的 `__new__` 写法） |
| Embedder 重复加载 | 同上 | 同上 |

### 🟢 开发联调

| 事项 | 说明 |
|------|------|
| **前端联调端口** | 后端 `localhost:8000`，前端 `localhost:5173`（Vite 默认）。前端 `vite.config.ts` 中配置 proxy 到 8000 避免 CORS |
| **测试对话** | 每个 Step 的"通过标准"即为单元测试，建议写完一个 Step 跑一次 |
| **Qdrant Dashboard** | `http://localhost:6333/dashboard` — 可视化查看向量分布，答辩时打开这个页面展示 |
| **DeepSeek 余额** | 提前充值 10 元足够整个毕设。每 100 次对话约花 ¥0.02-0.05 |
| **流式调试** | 前端未就绪时用 `curl -N` 直接看原始 SSE 事件（Step 7 的通过标准）
