"""模型供应商注册表 — 模型切换器（2026-08-06）

设计（见《docs/财务RAG-模型切换器需求记录.md》）：
  - PROVIDER_TEMPLATES：前端设置页的预设模板（选中自动填充 base_url/默认模型/窗口）
  - API Key 由用户在前端设置页填写 → localStorage → 随请求带给后端（后端转发，
    保留 RAG + 8 工具 + 双子 Agent + 上下文工程全链路）
  - context_window：上下文工程 history_summarizer 的 trigger 动态适配依据
    （trigger = 窗口 60%，小窗口模型自动降阈值防爆窗）
  - 安全：API Key 只在请求链路内存中流转（localStorage → 请求体 → ChatOpenAI），
    不落盘、不进日志、不提交 git

调用方：
  - agent/engine.get_llm(provider) / get_agent(provider) 按 provider 缓存实例
  - routers/chat.py GET /api/models 暴露模板列表（不含 key）、POST /api/models/test 测试连接
"""

from __future__ import annotations

from typing import Any

# 默认上下文窗口（DeepSeek V4 Flash，config 默认模型）
DEFAULT_CONTEXT_WINDOW = 64_000

# 摘要触发比例：trigger = context_window × TRIGGER_RATIO（默认 40K = 64K × 62.5%）
TRIGGER_RATIO = 0.6
TRIGGER_MIN = 8_000  # 小窗口模型最低触发阈值（防止窗口极小导致频繁摘要）

# ── 预设模板（前端设置页下拉数据源；不含任何 API Key）──
PROVIDER_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-v4-flash",
        "context_window": 64_000,
    },
    {
        "id": "qwen",
        "label": "通义千问（DashScope）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "context_window": 128_000,
    },
    {
        "id": "kimi",
        "label": "Kimi（Moonshot）",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "context_window": 32_000,
    },
    {
        "id": "zhipu",
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
        "context_window": 128_000,
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "context_window": 128_000,
    },
    {
        "id": "custom",
        "label": "自定义（BYOK）",
        "base_url": "",
        "default_model": "",
        "context_window": DEFAULT_CONTEXT_WINDOW,
    },
]

# 模板索引（id → template），供接口与前端快速查找
PROVIDER_TEMPLATE_MAP: dict[str, dict[str, Any]] = {
    t["id"]: t for t in PROVIDER_TEMPLATES
}


def get_template(template_id: str) -> dict[str, Any] | None:
    """按模板 id 取预设（无则 None）"""
    return PROVIDER_TEMPLATE_MAP.get(template_id)


def provider_key(provider: dict[str, Any] | None) -> str:
    """provider 缓存签名（LLM/Agent 缓存 dict 的 key）。

    provider=None → "__default__"（config 默认 DeepSeek）；
    否则 base_url|api_key 末 8 位|model —— 同配置复用缓存实例。
    """
    if not provider:
        return "__default__"
    api_key = provider.get("api_key") or ""
    return "|".join([
        str(provider.get("base_url") or ""),
        api_key[-8:],
        str(provider.get("model") or ""),
    ])


def resolve_context_window(provider: dict[str, Any] | None) -> int | None:
    """解析请求 provider 的上下文窗口（供 history_summarizer 动态 trigger）。

    Returns:
        int — 窗口大小；None — 用默认（trigger=40K）
    """
    if not provider:
        return None
    window = provider.get("context_window")
    return int(window) if window else None


def compute_trigger_tokens(context_window: int | None) -> int:
    """摘要触发阈值：窗口 60%，下限 8K（默认 40K 保持既有基线行为）"""
    if context_window:
        return max(TRIGGER_MIN, int(context_window * TRIGGER_RATIO))
    return 40_000
