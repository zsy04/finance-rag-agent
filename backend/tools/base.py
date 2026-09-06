"""工具返回结构 schema + 共享工具函数

v1 @tool 返回统一 JSON 结构（所有字段可选）：

    {
        "answer": str,           # 交给 LLM 的自然语言回答文本
        "result_card": {         # 前端结果卡片 → on_tool_end 解包发 result SSE 事件
            "type": "tax_result" | "social_result",
            "data": dict          # 引擎原始返回
        } | None,
        "sources": [             # 法规来源 → on_tool_end 解包发 source SSE 事件
            {"title": str, "url": str}
        ] | None,
        "disclaimer": str | None  # 免责声明 → on_tool_end 解包发 disclaimer SSE 事件
    }

Router 在 on_tool_end 拦截流程：
  1. output = event["data"]["output"]              # ToolMessage 对象
  2. raw = output.content                           # JSON 字符串
  3. parsed = json.loads(raw)
  4. if parsed.get("result_card"): yield result 事件
  5. if parsed.get("sources"):     yield source 事件（遍历）
  6. if parsed.get("disclaimer"):  yield disclaimer 事件
  7. parsed["answer"] → 交给 LLM 流式输出 step 事件
"""

# 后端 API 免责声明模板
AI_DISCLAIMER = (
    "⚠️ 本结果由 AI 辅助计算，仅供参考。"
    "实际应纳税额以税务机关最终核定为准。"
    "如有疑问，请拨打 12366 税务咨询热线。"
)


def tag_tool_result(text: str) -> str:
    """工具 answer 用 <tool_result> 包裹（2026-08-11，配合 SAFETY_HEADER）。

    声明"标签内是数据不是指令"：确定性工具返回（计算/填表）统一包裹，
    与 search_knowledge 的 <context>（检索文本）并列——LLM 视角两类数据源都有明确边界。
    仅包 answer 字段（前端/SSE 解包读 result_card/sources，不受影响）。
    """
    return f"<tool_result>\n{text}\n</tool_result>"
