"""
上下文工程 - 工具返回瘦身（guard_compress）
===========================================
基线采集结论（2026-08-04，实测数据）：
  - 单条 chunk 中位数仅 181 字，但 search_knowledge 把 top-5 拼接成
    ≈4K 字 ≈7K token 进入对话历史 —— 工具返回的拼接总长才是历史膨胀主因
    （s3 场景仅说一句"房贷利息1000"单轮历史就 +12.6K token）
  - 因此本模块从"极端保障"升级为"每次检索都生效的主力瘦身"：
      ① 单条超长才压缩（未超长原样返回，零损失）
      ② 提取式：必保句（数字/金额/文号/百分比/限值表述）强制保留，只删句不改写
      ③ 同时保留 doc_title 溯源（在 search_knowledge 组装处处理）

用法:
    from context.guard import guard_compress
    text = guard_compress(r.get("content", ""))
"""

from __future__ import annotations

import re

# 单条压缩后字符上限（原 content[:800] 硬截断的一半；chunk 中位数 181 字远低于此，正常不触发）
MAX_CHUNK_CHARS = 400

# ── 强必保正则：含这些内容的句子绝不淘汰（错一个数字就是错误答案）──
_PROTECT_STRONG = [
    r"\d+(?:\.\d+)?\s*(?:元|万元|万|亿|%|％|‰|年|月|日|天|倍|次|人|户)",  # 数字+单位
    r"[〔（(]\s*\d{4}\s*[〕）)]\s*\d{1,3}\s*号",                          # 文号：〔2018〕41号
    r"\d+(?:\.\d+)?\s*[％%]",                                            # 百分比
    r"自\s*\d{4}\s*年",                                                  # 生效时间
    r"(?:起征点|免征额|上限|下限|最高|最低|不超过|以上|以下)\s*[\d一二三四五六七八九十百千]",  # 限值表述
]
_PROTECT_COMPILED = [re.compile(p) for p in _PROTECT_STRONG]

# 句子切分：句号/问号/叹号/分号（含中英文），零宽断言保留标点
_SENT_END = re.compile(r"(?<=[。！？；;])")


def _sentencize(text: str) -> list[str]:
    """中文句子切分，返回非空句列表（保留原始顺序）"""
    parts = _SENT_END.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def _is_protected(sentence: str) -> bool:
    """含数字/文号/百分比/限值表述 → 必保"""
    return any(p.search(sentence) for p in _PROTECT_COMPILED)


def guard_compress(content: str, max_chars: int = MAX_CHUNK_CHARS) -> str:
    """
    提取式瘦身单条检索结果：
      - 未超长 → 原样返回（零损失，正常场景 99.9% 走此路径）
      - 超长   → 必保句全保留 + 其余按原序补到预算；极端情况兜底截断

    设计取舍（P2 保真度优先）：max_chars 是软上限——当必保句本身
    总长就超过预算时，宁可输出略超 max_chars 也不丢必保句（财税数字
    错一个就是错误答案）。实测 chunk 中位数 181 字，此边界几乎不触发。

    Args:
        content: 单条检索 chunk 文本
        max_chars: 压缩后字符上限（软上限，必保句优先）

    Returns:
        压缩后文本（必保句内容完整保留）
    """
    if not content:
        return ""
    if len(content) <= max_chars:
        return content

    sents = _sentencize(content)
    if not sents:
        # 无标点超长段：直接截断（关键信息通常在前部）
        return content[:max_chars]

    protected = [s for s in sents if _is_protected(s)]
    rest = [s for s in sents if not _is_protected(s)]

    # 必保句全选
    picked = list(protected)
    budget = max_chars - sum(len(s) for s in picked)

    # 其余按原序补入，直到预算耗尽
    for s in rest:
        if budget <= 0:
            break
        if len(s) <= budget:
            picked.append(s)
            budget -= len(s)
        else:
            picked.append(s[:budget])  # 单句超预算：保留句首（关键信息多在句首）
            budget = 0

    result = "".join(picked).strip()
    # 兜底：极端情况（全必保句也超预算/结果为空）直接截断原文
    if not result:
        result = content[:max_chars]
    return result


if __name__ == "__main__":
    # 自检：单测级验证
    import json

    cases = [
        # (输入, 期望关键点)
        ("国家税务总局公告〔2018〕41号规定，住房租金扣除标准为每月1500元。", "不超长原样"),
        ("根据规定，纳税人应当依法申报纳税，不得漏报瞒报。" * 10 + "扣除标准每月1500元。" * 10,
         "必保句保留"),
        ("", "空串"),
    ]
    for text, label in cases:
        out = guard_compress(text)
        print(f"[{label}] 输入{len(text)}字 → 输出{len(out)}字")
        if "1500" in text:
            assert "1500" in out, f"必保数字丢失! {out}"
    print("✅ 自检通过")

    # 超长含必保句案例（正常分布：必保句占小部分，应收敛到预算内）
    long_text = ("（一）纳税人在主要工作城市没有自有住房而发生的住房租金支出，可以扣除。\n"
                 "（二）直辖市、省会（首府）城市、计划单列市以及国务院确定的其他城市，扣除标准为每月1500元。\n"
                 "（三）市辖区户籍人口超过100万的城市，扣除标准为每月1100元。\n"
                 "（四）其他城市，扣除标准为每月800元。\n"
                 "该条款自2019年1月1日起施行。"
                 + "各地税务机关应当认真贯彻执行本规定，及时开展宣传辅导工作，确保纳税人充分享受政策红利。" * 12)
    out = guard_compress(long_text, max_chars=300)
    print(f"超长案例: {len(long_text)}字 → {len(out)}字（预算300，软上限）")
    for kw in ["1500", "1100", "800", "2019"]:
        assert kw in out, f"关键信息丢失: {kw}"
    print("✅ 超长案例必保句保留通过")

    # 极端边界：必保句本身超预算 → 软上限生效（宁超不丢数字）
    extreme = "扣除标准每月1500元。" * 200
    out = guard_compress(extreme, max_chars=100)
    assert "1500" in out, "极端案例必保句丢失!"
    print(f"✅ 极端边界通过（必保句超预算时宁超 {len(out)}>100 也不丢数字）")
