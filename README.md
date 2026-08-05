# 财税助手 — Finance RAG Agent

> 面向零财务基础大众的 AI 财税助手 Web 应用。自然语言对话替代复杂税务软件，让每个人都能看懂自己的税、算对自己的钱、填对申报表。

![Tech](https://img.shields.io/badge/Python-3.11+-blue) ![Frontend](https://img.shields.io/badge/React-18-61dafb) ![LLM](https://img.shields.io/badge/LLM-DeepSeek-green) ![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## 功能

| 功能 | 说明 |
|------|------|
| 智能问答 | 自然语言提问财税问题，RAG 检索精准答案，法规溯源 |
| 税率计算 | 个税（工资/劳务/稿酬/经营所得）、年终奖对比、分步明细 |
| 社保查询 | 郑州社保+公积金精准扣除（全国架构预留城市扩展） |
| 申报指引 | 个税APP汇算清缴操作流程、个体户季度申报指引 |
| 申报材料 | A表（雇员）/ B表（个体户）在线填写，一键导出 xlsx |
| 长对话记忆 | 历史自动摘要（trigger 40K token），超长对话不爆窗，压缩时用户可见提示 |

## 上下文工程（P0 ✅ 2026-08-04 完成）

| 模块 | 说明 |
|------|------|
| `context/guard.py` | 工具返回瘦身：检索拼接文本提取式压缩（必保句=数字/文号/百分比），单条 >400 字才触发 |
| `context/history_summarizer.py` | 历史摘要：继承官方 SummarizationMiddleware，trigger=40K/keep=20，清单式 prompt（12 字段逐一核对），中文 token 口径 |
| SSE `context` 事件 | 摘要发生时下一轮流开始时提示用户（"较早的对话已归档…"），前端 📦 提示条 |
| 评测闭环 | 长对话场景集四指标：judge 忠实度 **100%** / 事件触发率 **100%** / probe 字段完整率 92% / 历史峰值 <41K 不爆窗 |

## 技术栈

| 层级 | 选型 |
|------|------|
| LLM | DeepSeek (`deepseek-chat`)，LangChain `create_agent`，流式 SSE |
| Embedding | BGE-M3（FlagEmbedding），稠密 1024d + 稀疏双向量，支持 GPU/CPU 切换 |
| 向量库 | Qdrant，原生混合检索（RRF 融合） |
| 重排器 | BGE-Reranker-v2-m3，双阶段检索 |
| 后端 | FastAPI + StreamingResponse，8 个 Agent @tool + 上下文工程（历史摘要/工具瘦身）+ **Multi-Agent 化（P1 ✅ 2026-08-05 完成，双子 Agent）** |
| 前端 | React 18 + TypeScript + shadcn/ui + Tailwind CSS |
| 知识图谱 | 轻量 JSON 关系索引（20 条关联规则，两跳推理） |
| 评测 | 检索层 40 条（Recall@5/MRR/NDCG）+ 工具层 26 条（主 Agent 路由 100%）+ 生成层长对话场景集（judge 忠实度/字段校验）+ **多 Agent 双层评测（主层对拍 8/8 + 子层 10/10）** |

## 检索链路

```
用户提问 → Query 改写（口语→术语映射）
         → 元数据预过滤（relevance_tier 分层）
         → BGE-M3 双向量编码（稠密 1024d + 稀疏词汇）
         → Qdrant 混合检索（RRF 融合 → Top-30）
         → BGE-Reranker-v2-m3 精排 → Top-5
         → 轻量关系索引二次检索（两跳推理）
         → 拼接上下文 + System Prompt
         → DeepSeek 流式输出（SSE）
```

## Agent 工具集（8 个）

| 工具 | 功能 |
|------|------|
| `search_knowledge` | RAG 知识库检索（三层分层召回 + 关系图谱扩展） |
| `calculate_income_tax` | 综合所得个税计算（工资/劳务/稿酬/特许权使用费 + 年终奖对比） |
| `calculate_business_income_tax` | 经营所得个税计算（个体户，5%-35% 五级超额累进，支持季度/年度） |
| `query_social_insurance` | 社保+公积金计算（郑州，灵活就业/职工双模式） |
| `fill_tax_form` | 申报表自动填写（A表/B表），字段映射 + openpyxl，直接导出 xlsx |
| `filing_guide` | 申报流程指引（个税APP汇算清缴/个体户季度申报） |
| `get_user_context` | 对话上下文记忆（城市/收入/扣除项/亏损，跨轮复用） |
| `update_user_context` | 保存用户上下文信息 |

## 快速启动

### 本地开发

```bash
# 1. 配置 API Key
echo 'DEEPSEEK_API_KEY=sk-xxxx' > backend/.env

# 2. 启动 Qdrant（需要 Docker Desktop）
docker compose -f docker-compose.qdrant.yml up -d

# 3. 向量化入库（首次 ~15min GPU / ~1h CPU）
cd scripts && python embed_and_upsert.py

# 4. 启动后端
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 5. 启动前端
cd frontend
npm install && npm run dev

# 访问 http://localhost:5173
```

> **无 GPU 用户**：设置环境变量 `EMBEDDING_DEVICE=cpu`，BGE-M3 会自动回退 CPU（稍慢但可用）。
> **国内用户**：设置 `HF_ENDPOINT=https://hf-mirror.com` 加速模型下载。

### 评测

```bash
cd backend
python eval/eval.py          # 40 条 query，recall@5 / MRR / NDCG
python eval/eval.py -v       # 逐条打印详情
python eval/eval.py --category 个税  # 按分类评测
```

## 项目结构

```
├── backend/
│   ├── agent/           # Agent 大脑（LangGraph + 8 @tool + 历史摘要 middleware + Multi-Agent 双子 Agent 规划）
│   ├── context/         # 上下文工程（guard 工具瘦身 + history_summarizer 历史摘要）
│   ├── rag/             # RAG 检索引擎（retriever + query_rewriter）
│   ├── routers/         # FastAPI 路由（chat/tax/social/form，SSE 9 种事件）
│   ├── services/        # 计税引擎（纯 Python，零幻觉）
│   ├── tools/           # LangChain @tool 工具函数（规划：subagents.py 双子 Agent）
│   └── eval/            # 评测（检索 40 条 + 长对话场景集 + 规划：双层多 Agent 评测）
├── frontend/
│   └── src/
│       ├── components/chat/     # 对话视图
│       ├── components/calculator/ # 税率计算器
│       ├── components/form/     # 申报材料生成
│       └── components/layout/   # 布局（Sidebar + TopBar）
├── rag-data/processed/
│   ├── national/rates/         # JSON 税率表 + 行业基准
│   ├── national/templates/     # 申报表模板（A表/B表 xlsx）
│   └── cities/zhengzhou/       # 郑州社保+公积金数据
├── scripts/                    # 数据处理工具链
├── docs/                       # 技术文档
└── qdrant_data/                # Qdrant 向量数据
```

## 核心设计决策

- **准确性优先于速度**：财税场景错不起
- **金额计算不走 LLM**：税率/社保全部 JSON + Python 公式，零幻觉
- **语义边界切分**：税法按 `### 第X条`、问答按 `## 问句` 切分，不硬按字符数
- **先跑通再评测收敛**：建 40 条 bad case 评测集，逐轮优化避免过拟合
- **AI 嵌入 vs AI 原生**：核心逻辑代码化，AI 负责调度和理解层
- **上下文工程**：历史摘要 + 工具返回瘦身，评测驱动迭代（三轮回合修 3 个根因，见 docs/开发踩坑记录）
- **Multi-Agent 化（P1 ✅ 2026-08-05 完成）**：计税/社保拆为双子 Agent（Tool-as-Subagent，无状态+全局单例），`AGENT_MODE` 模式开关回退，prompt 双版本防"调不到子 Agent"，失败降级复用 tool_calls 参数，绕过检测强制重算。三层评测全绿：主 Agent 路由 26/26、主层对拍 8/8、子层 10/10——设计见 `docs/财务RAG-Multi-Agent 集成设计文档.md`（v1.5）

## License

MIT
