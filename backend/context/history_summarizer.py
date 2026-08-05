"""
历史摘要器 — 继承官方 SummarizationMiddleware
=============================================
基线采集定参（2026-08-04，四场景实测）：
  - trigger = 40_000 token（窗口 63%）：s1 第 10 轮 / s3 第 7 轮触发，余量 19K
  - keep = 20 条消息：s2/s4 全 100% 命中，上下文 16-21K token
  - 清单式摘要 prompt：s1 实测发现宽松 prompt 会漏扣除项金额 → 逐字段核对

扩展（lest 差异化）：
  - 摘要发生时置标志位（thread_id → 时间戳），供路由层 _agent_stream 消费
    → 发 SSE context 事件，实现"压缩时给用户提示"（用户新增需求）
  - 清单式 CUSTOM_SUMMARY_PROMPT（CONTEXT_KEYS 12 字段逐一自查）

集成：agent.engine.build_agent 的 middleware 链（与 ToolError/ModelCallLimit 并列）
"""

from __future__ import annotations

import threading
import time
from typing import Any

from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain_core.language_models import BaseChatModel


def est_tokens(text: str) -> int:
    """中文 token 估算：1 字 ≈ 1.75 token（与基线采集口径一致，trigger=40K 才有意义）"""
    return max(1, int(len(text) * 1.75))


def _count_tokens_zh(messages) -> int:
    """
    中文口径 token 计数（消息列表 → 总 token）。

    ⚠️ 关键修复（2026-08-04 实测踩坑）：官方默认 count_tokens_approximately 是
    英文口径（chars_per_token=4.0），中文被低估约 2.3 倍——s1 场景 20 轮真实
    token 70K（≈40K 字），官方只算 ~10K，导致 trigger=40K 永远不触发。
    必须传中文口径计数器，且与基线 est_tokens 完全一致，trigger 阈值才有意义。
    """
    return sum(est_tokens(m.content) for m in messages if getattr(m, "content", None))

# ── 摘要标志位：thread_id → 发生时间戳 ──
# 路由层在 SSE 流开始时 pop 消费；有标志 → 先发 context 事件再继续流。
# 多用户并发安全：per-thread_id 隔离 + 锁保护。
_summarized_flags: dict[str, float] = {}
_flags_lock = threading.Lock()


# ── 清单式摘要 prompt（基线采集 s1 缺陷对策 + 评测 v1 强化）──
# 占位符 {messages} + <messages> 标签是官方 public contract（summarization.py L77-86），
# 不得改动，否则 .format(messages=...) 会失败。
# 评测 v1（2026-08-04）发现 300 字上限 + 宽松指令仍会丢字段（s3 第一次摘要丢了
# 城市/工资/收入类型）→ 上限提至 500 字 + "宁删背景不删数值"最高优先级规则。
CUSTOM_SUMMARY_PROMPT = """你是对话历史摘要器。将以下多轮对话压缩为 500 字以内的摘要。

【最高优先级 - 必须完整出现（一个都不能漏）】以下字段若在对话中出现过，
必须原样保留其数值或名称：城市（如"郑州"）、收入类型（如"工资"/"经营"）、
月薪/年薪（如"12000"）、住房租金、子女教育、赡养老人、大病医疗、
住房贷款利息、婴幼儿照护、上年亏损、个体户名称/信用代码、
社保公积金缴费基数与比例、已办理或询问过的业务。
规则：宁删背景描述与寒暄，绝不删数值/名称；输出前逐项自查清单。

其余内容按信息价值取舍，闲聊与寒暄一律删除。
只输出摘要正文，不要任何解释。
<messages>
{messages}
</messages>"""


def pop_summarized_flag(thread_id: str) -> bool:
    """
    路由层调用：检查并消费摘要标志。
    Returns:
        True — 本线程本轮发生过摘要，应发 SSE context 事件提示用户
        False — 无摘要发生
    """
    with _flags_lock:
        return _summarized_flags.pop(thread_id, None) is not None


class HistorySummarizer(SummarizationMiddleware):
    """官方摘要中间件 + lest 扩展：清单式 prompt + 摘要标志位（→ context 事件）

    继承而非自研：官方处理了 AI/Tool 消息配对、cutoff 边界、RemoveMessage 替换等
    细节（summarization.py before_model/abefore_model），自研成本高且易错。
    """

    def __init__(
        self,
        model: BaseChatModel,
        trigger_tokens: int = 40_000,
        keep_messages: int = 20,
    ):
        super().__init__(
            model=model,
            trigger=[("tokens", trigger_tokens)],   # OR 语义，单条件即触发
            keep=("messages", keep_messages),        # 摘要后保留最近 N 条
            summary_prompt=CUSTOM_SUMMARY_PROMPT,
            token_counter=_count_tokens_zh,          # 中文口径（官方默认低估中文 2.3 倍）
            # ⚠️ 关键修复（踩坑 #7）：官方默认 trim_tokens_to_summarize=4000 且
            # strategy="last"——信息密度高的对话会砍掉最早的画像轮（城市/工资/扣除项），
            # 摘要 LLM 根本看不到 → 评测 probe/judge 不达标（s1/s2/s3 全部中招）。
            # 传 None 跳过 trim，全量喂摘要 LLM（保真优先；摘要输入 ~40K token ≈ ¥0.04/次）。
            trim_tokens_to_summarize=None,
        )

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """
        模型调用前钩子：官方逻辑（触发→切分→摘要→替换消息）+ lest 扩展（置标志）。
        super 返回非 None 表示发生了摘要 → 置标志位供路由层消费。
        """
        result = await super().abefore_model(state, runtime)
        if result is not None:
            # 发生了摘要 → 置标志（thread_id 从 contextvar 读，路由层已 set）
            try:
                from tools.user_context import _current_thread_id

                tid = _current_thread_id.get()
                with _flags_lock:
                    _summarized_flags[tid] = time.time()
            except LookupError:
                # contextvar 未初始化（评测脚本/单元测试场景）→ 跳过标志，不影响摘要本身
                pass
        return result


def build_history_summarizer(llm: BaseChatModel) -> HistorySummarizer:
    """工厂：供 agent.engine.build_agent 调用，复用 Agent 的 DeepSeek 实例"""
    return HistorySummarizer(model=llm)
