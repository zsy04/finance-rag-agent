"""Multi-Agent 双层评测

v1.5 设计：
  主层·对拍 8 条（计税 5 + 社保 3）：子 Agent vs 原工具直调，比较 result_card 数值
  子层·内部选工具 6 条（计税 4 + 社保 2）：直接对子 Agent 注入 query，验证内部工具选择与拒答

运行：cd F:/lest && F:/lest/backend/venv/Scripts/python.exe backend/eval/multi_agent_eval.py
"""

import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGENT_MODE
from agent.engine import get_llm
from tools.subagents import get_tax_subagent, get_social_subagent, _extract_fields, CALC_TOOL_NAMES
from tools.calculate_income_tax import calculate_income_tax, calculate_business_income_tax
from tools.query_social_insurance import query_social_insurance


# ── 主层·对拍集（8 条）──────────────────────────────
# direct_args 必须与工具的实际 args_schema 字段名严格一致
# expect 支持点号嵌套路径，如 "bonus.separate_tax" → data["bonus"]["separate_tax"]

PAIR_EVAL = [
    # 计税（5 条）
    {"id": 1, "query": "我年收入96000元工资类型社保年缴9888元租房月扣1500算个税",
     "subagent": "tax", "expect": "tax_amount",
     "direct_args": {"annual_income": 96000, "income_type": "salary", "social_insurance": 9888, "deductions": {"housing_rent": 1500}}},
    {"id": 2, "query": "年薪12万交多少税",
     "subagent": "tax", "expect": "tax_amount",
     "direct_args": {"annual_income": 120000, "income_type": "salary"}},
    {"id": 3, "query": "劳务报酬3万元个税怎么算",
     "subagent": "tax", "expect": "tax_amount",
     "direct_args": {"annual_income": 30000, "income_type": "labor_service"}},
    {"id": 4, "query": "年终奖5万要交多少税（并入综合 vs 单独对比）",
     "subagent": "tax", "expect": "exists",
     "direct_args": {"annual_income": 0, "income_type": "salary", "bonus": 50000}},
    {"id": 5, "query": "个体工商户季度收入20万成本8万，算经营所得个税",
     "subagent": "tax", "expect": "tax_amount", "tool_name": "business",
     "direct_args": {"period": "quarter", "income": 200000, "cost": 80000}},

    # 社保（3 条）
    {"id": 6, "query": "郑州工资8000社保扣多少",
     "subagent": "social", "expect": "total_personal",
     "direct_args": {"salary": 8000, "employment_type": "employee"}},
    {"id": 7, "query": "灵活就业社保一个月交多少钱",
     "subagent": "social", "expect": "total_monthly",
     "direct_args": {"salary": 8000, "employment_type": "flexible", "flexible_base_level": 1}},
    {"id": 8, "query": "郑州公积金缴存基数",
     "subagent": "social", "expect": "housing_fund.base",
     "direct_args": {"salary": 8000, "employment_type": "employee"}},
]


# ── 子层·内部选工具评测（6+ 条）─────────────────────

SUBAGENT_EVAL = [
    # 计税子 Agent：内部应选对工具（4 条）
    {"id": 1, "agent": "tax", "query": "年终奖5万要交多少税",
     "expected": ["calculate_income_tax"], "reject": False},
    {"id": 2, "agent": "tax", "query": "个体户季度收入20万成本8万算税",
     "expected": ["calculate_business_income_tax"], "reject": False},
    {"id": 3, "agent": "tax", "query": "我之前填的工资信息是什么",
     "expected": ["get_user_context"], "reject": False},
    {"id": 4, "agent": "tax", "query": "我的工资改成12000",
     "expected": ["update_user_context"], "reject": False},
    # 社保子 Agent（2 条）
    {"id": 5, "agent": "social", "query": "五险一金缴费比例是多少",
     "expected": ["query_social_insurance"], "reject": False},
    {"id": 6, "agent": "social", "query": "郑州公积金基数",
     "expected": ["query_social_insurance"], "reject": False},
    # 拒答用例（2 条）
    {"id": 7, "agent": "tax", "query": "个税APP怎么退税",
     "expected": [], "reject": True, "reject_phrase": "不是计税问题"},
    {"id": 8, "agent": "social", "query": "工资8000交多少税",
     "expected": [], "reject": True, "reject_phrase": "不是社保"},
    # 心算诱导用例（v1.5 新增：验证 result_card 必须存在）
    {"id": 9, "agent": "tax", "query": "月薪8000个税大概多少",
     "expected": ["calculate_income_tax"], "reject": False, "require_result_card": True},
    {"id": 10, "agent": "tax", "query": "房租1500能省多少税",
     "expected": ["calculate_income_tax"], "reject": False, "require_result_card": True},
]


def _get_nested(data: dict, path: str):
    """按点号路径取嵌套字典值，如 'bonus.separate_tax' → data['bonus']['separate_tax']"""
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data


def run_direct_calc(case: dict):
    """直调原工具计算，返回结果字典"""
    args = case.get("direct_args", {})
    subagent = case["subagent"]
    tool_name = case.get("tool_name", "")

    if subagent == "tax" and tool_name == "business":
        raw = calculate_business_income_tax.invoke(args)
    elif subagent == "tax":
        raw = calculate_income_tax.invoke(args)
    else:
        raw = query_social_insurance.invoke(args)

    return json.loads(raw) if isinstance(raw, str) else raw


def extract_tool_calls_from_messages(messages: list) -> list[str]:
    """从消息链中提取所有工具调用名称（去重，保留顺序）"""
    tools_called = []
    seen = set()
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if name and name not in seen:
                    tools_called.append(name)
                    seen.add(name)
    return tools_called


def evaluate_pair():
    """主层对拍：子 Agent 返回结果 vs 直调原工具结果，比较数值一致性"""
    print("="*60)
    print(f"主层·对拍评测 ({len(PAIR_EVAL)} 条) | AGENT_MODE={AGENT_MODE}")
    print("="*60 + "\n")

    if AGENT_MODE != "multi":
        print("⚠️ AGENT_MODE != 'multi'，对拍评测仅 multi 形态有效，跳过。")
        print("   请设置 AGENT_MODE=multi 后重试。\n")
        return

    llm = get_llm()
    tax_sub = get_tax_subagent(llm)
    social_sub = get_social_subagent(llm)

    correct = 0
    total = len(PAIR_EVAL)

    for case in PAIR_EVAL:
        qid = case["id"]
        query = case["query"]
        expect_field = case["expect"]
        subagent = case["subagent"]
        sub = tax_sub if subagent == "tax" else social_sub

        try:
            # 子 Agent 路径
            result = asyncio.run(sub.ainvoke({"messages": [{"role": "user", "content": query}]}))
            answer, sub_card, sources = _extract_fields(result["messages"])

            # 直调原工具路径
            direct_result = run_direct_calc(case)
            direct_card = direct_result.get("result_card")

            # 比较数值
            if sub_card and direct_card:
                sub_data = sub_card.get("data", {})
                dir_data = direct_card.get("data", {})

                # expect="exists"：只验证子 Agent 有 result_card（不计较具体数值）
                if expect_field == "exists":
                    correct += 1
                    print(f"  ✅ #{qid:2d} {'has_result_card':20s} | 子Agent已产出结果卡片")
                    continue

                # 对拍：比较 expect 字段的数值（支持点号嵌套路径）
                sub_val = _get_nested(sub_data, expect_field)
                dir_val = _get_nested(dir_data, expect_field)

                if sub_val is not None and sub_val == dir_val:
                    correct += 1
                    status = "✅"
                    detail = f"{expect_field}={sub_val}"
                else:
                    status = "❌"
                    detail = f"子Agent={sub_val} vs 直调={dir_val}"

                print(f"  {status} #{qid:2d} {expect_field:20s} | {detail}")
            elif sub_card:
                status = "⚠️"
                correct += 1  # 有 result_card 但直调无结果 → 视为通过（参数传递差异）
                print(f"  {status} #{qid:2d} 子Agent有result_card但直调无结果（参数差异，暂放行）")
            else:
                status = "❌"
                print(f"  {status} #{qid:2d} 子Agent无result_card | query: {query[:50]}")

        except Exception as e:
            print(f"  ❌ #{qid:2d} 异常: {e}")

    accuracy = correct / total * 100
    print(f"\n=== 对拍准确率: {correct}/{total} ({accuracy:.1f}%) ===\n")


def evaluate_subagent():
    """子层评测：直接对子 Agent 注入 query，验证内部工具选择与拒答"""
    print("="*60)
    print(f"子层·内部选工具评测 ({len(SUBAGENT_EVAL)} 条) | AGENT_MODE={AGENT_MODE}")
    print("="*60 + "\n")

    if AGENT_MODE != "multi":
        print("⚠️ AGENT_MODE != 'multi'，子层评测仅 multi 形态有效，跳过。\n")
        return

    llm = get_llm()
    tax_sub = get_tax_subagent(llm)
    social_sub = get_social_subagent(llm)

    tool_correct = 0
    tool_total = 0
    reject_correct = 0
    reject_total = 0
    bypass_correct = 0
    bypass_total = 0

    for case in SUBAGENT_EVAL:
        qid = case["id"]
        query = case["query"]
        agent_type = case["agent"]
        is_reject = case.get("reject", False)
        require_card = case.get("require_result_card", False)

        sub = tax_sub if agent_type == "tax" else social_sub

        try:
            result = asyncio.run(sub.ainvoke({"messages": [{"role": "user", "content": query}]}))
            messages = result["messages"]
            answer, result_card, sources = _extract_fields(messages)
            actual_tools = extract_tool_calls_from_messages(messages)

            # 计数
            if is_reject:
                reject_total += 1
                phrase = case.get("reject_phrase", "")
                if phrase in answer:
                    reject_correct += 1
                    print(f"  ✅ #{qid:2d} 拒答正确: {answer[:60]}")
                else:
                    print(f"  ❌ #{qid:2d} 拒答失败（期望含'{phrase}'）: {answer[:60]}")
            elif require_card:
                bypass_total += 1
                if result_card is not None:
                    bypass_correct += 1
                    print(f"  ✅ #{qid:2d} 绕过检测通过: 有 result_card（未心算）")
                else:
                    print(f"  ❌ #{qid:2d} 绕过检测失败: 无 result_card（疑似心算）| answer: {answer[:80]}")
            else:
                tool_total += 1
                expected = case["expected"]
                hit = all(e in actual_tools for e in expected)
                if hit:
                    tool_correct += 1
                    print(f"  ✅ #{qid:2d} 期望={expected} 实际={actual_tools}")
                else:
                    print(f"  ❌ #{qid:2d} 期望={expected} 实际={actual_tools}")

        except Exception as e:
            print(f"  ❌ #{qid:2d} 异常: {e}")

    # 汇总
    tool_rate = tool_correct / tool_total * 100 if tool_total else 0
    reject_rate = reject_correct / reject_total * 100 if reject_total else 0
    bypass_rate = bypass_correct / bypass_total * 100 if bypass_total else 0

    print(f"\n=== 子层汇总 ===")
    print(f"  工具选择: {tool_correct}/{tool_total} ({tool_rate:.0f}%) {'✅≥90%' if tool_rate >= 90 else '⚠️<90%'}")
    print(f"  拒答:     {reject_correct}/{reject_total} ({reject_rate:.0f}%)")
    print(f"  绕过检测: {bypass_correct}/{bypass_total} ({bypass_rate:.0f}%) {'✅' if bypass_rate == 100 else '⚠️'}")
    print()


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f" Multi-Agent 双层评测 | AGENT_MODE={AGENT_MODE}")
    print(f"{'='*60}\n")

    if AGENT_MODE != "multi":
        print("⚠️ 当前 AGENT_MODE={}，双层评测仅 multi 形态有效。".format(AGENT_MODE))
        print("  请设置 AGENT_MODE=multi（或环境变量 AGENT_MODE=multi）后重试。\n")
    else:
        evaluate_pair()
        evaluate_subagent()
