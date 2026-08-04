"""
RAG 问答生成器（Legacy 直连通路）
==============
构建 System Prompt（含检索到的法规上下文），调用 DeepSeek（config.DEEPSEEK_MODEL）流式输出。
Agent 通路见 agent/engine.py；本模块仅由 Legacy /chat 和 /chat/with-search 使用。
"""

import json
import logging
from typing import AsyncGenerator
from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)

SYSTEM_PROMPT = """你是一个专业的中国财税助手，面向普通大众用户（非财务专业人士）。

## 你的能力
你可以根据提供的法规条文、问答库和税率表，回答用户关于税务、社保、公积金的问题。

## 回答规则
1. **基于上下文回答**：只根据【参考法规】中的内容回答，不要编造信息。
   如果没有找到相关信息，诚实告知用户并建议拨打 12366 税务咨询热线。
2. **语言通俗**：用普通人能听懂的话解释，避免堆砌专业术语。如果必须使用术语，加上简短解释。
3. **分步说明**：涉及计算的问题，分步骤列出推导过程。
4. **法规溯源**：在回答末尾列出引用的法规名称和条文号。
5. **安全提醒**：金额计算类问题在回答末尾加上免责声明：
   "⚠️ 以上计算仅供参考，具体以税务机关核定为准。如有疑问请拨打 12366。"

## 回答格式
- 简洁开篇，直接回答问题
- 列举型内容用短句分行
- 引用法规时用 `《法规名称》第X条` 格式
"""


# 上下文最大字符数（5 个 chunk × 800 字 = 4000，预留 500 给标题和分隔符）
# 超过此值按 final_score 降序截断，确保高相关性的内容优先保留
MAX_CONTEXT_CHARS = 3500


def build_context(search_results: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """将检索结果拼接为 LLM 可读的上下文，超出 max_chars 自动截断"""
    if not search_results:
        return "（未找到相关法规）"

    parts = []
    total_chars = 0
    included = 0
    truncated = False

    for i, r in enumerate(search_results, 1):
        tier_label = {
            "tax_law": "税法",
            "tax_regulation": "条例/细则",
            "qa_corpus": "官方问答",
            "general_law": "关联法律",
        }.get(r.get("relevance_tier", ""), "")

        header = f"【参考 {i}】{tier_label} | {r.get('doc_title', '')}"
        content = r.get('content', '')
        block = f"{header}\n{content}"

        # 加上分隔符的长度
        sep_len = len("\n\n---\n\n") if parts else 0
        block_len = len(block)

        if total_chars + sep_len + block_len <= max_chars:
            # 完整保留
            parts.append(block)
            total_chars += sep_len + block_len
            included += 1
        elif total_chars + sep_len + len(header) + 50 <= max_chars:
            # chunk 太长，保留头部 + 截断正文
            available = max_chars - total_chars - sep_len - len(header) - 20
            if available > 100:  # 至少保留 100 字才有意义
                parts.append(f"{header}\n{content[:available]}…")
                total_chars = max_chars
                included += 1
            truncated = True
            break
        else:
            # 连头部都放不下，停止
            truncated = True
            break

    result = "\n\n---\n\n".join(parts)

    if truncated and included < len(search_results):
        result += (
            f"\n\n---\n"
            f"（已截断：共检索到 {len(search_results)} 条法规，"
            f"因长度限制仅展示前 {included} 条高相关性结果）"
        )

    return result


async def stream_answer(query: str, search_results: list[dict]) -> AsyncGenerator[str, None]:
    """
    构建完整 prompt → 调用 DeepSeek → 流式 yield SSE 数据块

    Yields:
        SSE 格式字符串，如:
        data: {"type":"token","content":"你好"}\n\n
        data: {"type":"done"}\n\n
    """
    context = build_context(search_results)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"【用户问题】\n{query}\n\n【参考法规】\n{context}"},
    ]

    try:
        stream = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            temperature=0,
            stream=True,
            max_tokens=2048,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {json.dumps({'type': 'token', 'content': delta.content}, ensure_ascii=False)}\n\n"

        # 流结束
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        # 内部记完整 traceback 便于排查，对外不泄露原始异常信息
        logger.exception("stream_answer 异常 (query=%s)", query[:100])
        yield f"data: {json.dumps({'type': 'error', 'content': '生成服务暂时不可用，请稍后重试'}, ensure_ascii=False)}\n\n"
