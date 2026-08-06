# 财务RAG-模型切换器需求记录

> 定位：网站内**模型切换器**功能的需求记录与设计草案（先思考，未实施）。
> 创建：2026-08-06。状态：✅ **2026-08-06 已实施**（后端 provider 注册表 + get_llm/get_agent 按 provider 缓存 + chat 接收 provider + /api/models + /api/models/test + 前端设置页/模型下拉 + 上下文工程窗口动态适配；待 tsc/冒烟验证）

---

## 1. 需求背景（用户原话要点）

> "让用户自己来（在网站内部更换模型），比如 V4 Flash 或者 DeepSeek 其他型号，或者千问什么的……"
> "我希望是市面上绝大部分的模型都可以兼容进去"
> "（持久化）localStorage"
> "（UI 位置）之后我会再给你说的部分，你只用先思考一下这些问题然后处理保存一下我提问的这些问题就行了"

## 2. 已确认决策

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 模型范围 | **市面绝大部分模型可兼容**（不限于 DeepSeek 系列） |
| 2 | 选择持久化 | **localStorage**（前端保存，请求携带，无后端状态） |
| 3 | UI 位置 | ✅ **顶栏右侧用户栏**（2026-08-06 定案）——启用原预留的用户区位置，放"设置"入口 + 模型下拉；设置页内容含供应商配置/API Key 管理 |
| 4 | 设置入口 | ✅ **新增"设置"入口**（设置页/弹窗），用户可自行输入 API Key |
| 5 | 调用架构 | ✅ **后端转发**：前端把 provider 配置（base_url + api_key + model）随请求带给后端，后端动态实例化 LLM，**保留 RAG + 8 工具 + 双子 Agent + 上下文工程全链路**。⚠️ 不能前端直连——Agent 能力全在后端，直连会退化为裸聊天 |
| 6 | API Key 来源 | **用户自填为主，`.env` 预配置为兜底**：未配置自定义 provider 时回退到默认 DeepSeek（`DEEPSEEK_API_KEY`） |

## 3. 设计草案（先思考，未定稿）

### 3.1 核心思路：OpenAI 兼容协议统一接入

市面主流模型 API 绝大多数提供 **OpenAI 兼容端点**（`/v1/chat/completions`），LangChain `ChatOpenAI` 可统一接入。因此无需为每家写适配器，只需一张**供应商模板表**驱动（用户一键填充 + 可自定义）：

| 供应商模板 | 兼容端点（base_url） | key 字段 |
|--------|---------------------|----------|
| DeepSeek | `https://api.deepseek.com/v1` | api_key（用户填） |
| 通义千问 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | api_key（用户填） |
| Kimi Moonshot | `https://api.moonshot.cn/v1` | api_key（用户填） |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | api_key（用户填） |
| OpenAI | `https://api.openai.com/v1` | api_key（用户填） |
| 本地 Ollama | `http://localhost:11434/v1` | 无需 key |
| **自定义（BYOK）** | 用户任意填 base_url | api_key + model 全自定义 |

> 每家模型名示例：`deepseek-v4-flash` / `deepseek-reasoner` / `qwen-plus` / `qwen-turbo` / `moonshot-v1-8k` / `glm-4-flash` / `gpt-4o-mini` / `llama3.1` 等。

### 3.2 模型注册表结构（草案）

```python
# backend/models.py（或 services/model_registry.py）
MODEL_REGISTRY = {
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash（默认）",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-flash",
        "context_window": 64000,   # 用于上下文工程 WINDOW 动态适配
    },
    ...
}
```

### 3.3 接口设计（草案）

| 接口 | 说明 |
|------|------|
| `GET /api/models` | 返回供应商模板列表（前端设置页下拉数据源） |
| `POST /api/chat` | 请求体加可选 provider 配置：`{ base_url, api_key, model }`；缺省回退 `.env` 默认 DeepSeek（v4-flash） |

`get_llm(base_url, api_key, model)` 动态实例化 `ChatOpenAI`（langchain-openai），base_url/api_key/model 全由请求携带；缺省时用 config 默认值。**engine.py:61 TODO（key 配置源接口位）正好落在这里**——`get_llm` 从"读 config"升级为"按请求 provider 配置"。

### 3.4 设置页（新增，用户定案）

- 入口：顶栏/侧边栏"设置"图标（与模型下拉位置一起定）
- 内容：
  1. **供应商模板选择**：下拉选 DeepSeek / 千问 / Kimi / GLM / OpenAI / Ollama / 自定义，选中自动填充 base_url
  2. **自定义配置**：base_url + api_key + 模型名（BYOK，可接任意 OpenAI 兼容端点/中转站）
  3. **多套配置管理**：可保存多套 provider，设为当前使用（切换即时生效）
  4. **测试连接**：可选「测试」按钮，调一次最小请求验证 key/base_url 有效
- 存储：localStorage（key 如 `lest_providers` = 配置数组 + `lest_active_provider` = 当前 id）

### 3.5 前端调用链（草案）

- 模型下拉控件（shadcn Select，位置待定）展示"当前 provider 的模型"
- 发送消息时：`{ base_url, api_key, model }` 随 `POST /api/chat` 请求体携带
- 未配置任何自定义 provider → 请求不带 provider，后端走默认 DeepSeek
- 会话中切换即时生效（下一轮对话用新配置）

### 3.6 上下文工程适配（重要风险）

- 各模型 **context_window 不同**（DeepSeek 64K / qwen-turbo 128K / gpt-4o-mini 128K / moonshot 8K-32K）
- `history_summarizer` 的 trigger 40K / keep 20 参数需按模型窗口**动态计算**，否则小窗口模型会爆窗
- 方案：请求携带可选 `context_window`（或后端按 model 名查模板表），`get_llm` 返回时同步给上下文工程配置

### 3.7 安全说明（自用场景可接受，需标注）

- API Key 经 localStorage 存取、随请求传给**本地后端**（`localhost:8000`），自用/演示可接受
- 若将来公网部署：需加 HTTPS + 会话鉴权，或改为"key 只存后端 .env"模式，本需求文档的 localStorage 模式仅限本地

## 4. 待用户确认的问题（后续）

- [x] ~~**UI 位置**~~ → ✅ 已定案（2026-08-06）：**顶栏右侧用户栏**，设置入口 + 模型下拉，启用原预留用户区
- [x] ~~**默认 provider 是否必须保留**~~ → ✅ 保留：默认 DeepSeek（.env 的 `DEEPSEEK_API_KEY` + v4-flash）兜底，未配置自定义也能用
- [x] ~~**模型能力差异处理**~~ → ✅ 加"工具兼容"标签，切换时不兼容模型给出提示（Agent 依赖 function calling）
- [x] ~~**`temperature` 是否按模型调整**~~ → ✅ **保持 0 不变**（财税场景确定性优先，全部模型一致）
- [x] ~~**Ollama 本地模型**~~ → ❌ **不做**（用户 2026-08-06 定案：不需要）

> ✅ **2026-08-06 全部决策已定案，进入实施阶段。**

## 5. 实施规划（全部决策已定案，2026-08-06 启动）

1. `backend/models.py`（或 services/provider_registry.py）：供应商模板表 + `get_llm(base_url, api_key, model)` 改造（engine.py/subagents.py 同步）
2. chat.py 请求体接收 provider 配置（Pydantic 模型扩展）
3. 前端设置页（供应商模板 + BYOK + 多套管理 + 测试连接）+ localStorage
4. 前端模型下拉 + 请求携带 provider
5. 上下文工程 WINDOW 动态适配
6. 文档同步（UI设计方案/前后端对照表/后端设计文档/README 特性）
7. 评测回归（工具层 26 条确认切换后不回归）
