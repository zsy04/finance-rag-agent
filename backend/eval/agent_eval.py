"""
Agent 工具选择评测（v1.5 多 Agent 适配）
=================
构造 24 条 query，每条标注期望调用的工具，运行 Agent 统计准确率。
目标：≥ 90%

运行：cd <repo-root> && python backend/eval/agent_eval.py

工具名按 AGENT_MODE 自动适配：
  - multi 形态：计税/社保 → tax_subagent / social_subagent
  - tools 形态：计税/社保 → calculate_income_tax / calculate_business_income_tax / query_social_insurance

迁移说明（v1.1）：
  id 6-10: calculate_income_tax → tax_subagent
  id 11-14: query_social_insurance → social_subagent
  id 21-22: B 表双工具用例（fill_tax_form + tax_subagent）
  id 23-26: 邻域混淆用例（验证主 Agent 不会误派）
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGENT_MODE
from agent.engine import build_agent

# 根据 AGENT_MODE 动态生成工具名
if AGENT_MODE == "multi":
    TAX_TOOL = "tax_subagent"
    BIZ_TAX_TOOL = "tax_subagent"
    SOCIAL_TOOL = "social_subagent"
else:
    TAX_TOOL = "calculate_income_tax"
    BIZ_TAX_TOOL = "calculate_business_income_tax"
    SOCIAL_TOOL = "query_social_insurance"

# ── 评测集 ─────────────────────────────────────────────

EVAL_SET = [
    # search_knowledge (5 条)
    {"id": 1, "query": "租房扣除标准是多少", "expected_tools": ["search_knowledge"]},
    {"id": 2, "query": "增值税税率是多少", "expected_tools": ["search_knowledge"]},
    {"id": 3, "query": "子女教育专项附加扣除怎么规定的", "expected_tools": ["search_knowledge"]},
    {"id": 4, "query": "赡养老人扣除标准", "expected_tools": ["search_knowledge"]},
    {"id": 5, "query": "小规模纳税人有什么优惠", "expected_tools": ["search_knowledge"]},

    # 计税（5 条）→ multi 形态迁名为 tax_subagent
    {"id": 6, "query": "我年收入96000元工资类型社保年缴9888元租房月扣1500算个税", "expected_tools": [TAX_TOOL]},
    {"id": 7, "query": "年薪12万交多少税", "expected_tools": [TAX_TOOL]},
    {"id": 8, "query": "劳务报酬3万元个税怎么算", "expected_tools": [TAX_TOOL]},
    {"id": 9, "query": "年终奖5万要交多少税", "expected_tools": [TAX_TOOL]},
    {"id": 10, "query": "月薪8000工资扣除社保后个税多少", "expected_tools": [TAX_TOOL]},

    # 社保（4 条）→ multi 形态迁名为 social_subagent
    {"id": 11, "query": "郑州工资8000社保扣多少", "expected_tools": [SOCIAL_TOOL]},
    {"id": 12, "query": "灵活就业社保一个月交多少钱", "expected_tools": [SOCIAL_TOOL]},
    {"id": 13, "query": "五险一金缴费比例是多少", "expected_tools": [SOCIAL_TOOL]},
    {"id": 14, "query": "郑州公积金缴存基数", "expected_tools": [SOCIAL_TOOL]},

    # fill_tax_form (3 条)
    {"id": 15, "query": "帮我生成个税申报表A表", "expected_tools": ["fill_tax_form"]},
    {"id": 16, "query": "我要填写个人所得税基础信息表", "expected_tools": ["fill_tax_form"]},
    {"id": 17, "query": "生成申报材料", "expected_tools": ["fill_tax_form"]},

    # filing_guide (3 条)
    {"id": 18, "query": "个税APP怎么退税", "expected_tools": ["filing_guide"]},
    {"id": 19, "query": "年度汇算清缴怎么操作", "expected_tools": ["filing_guide"]},
    {"id": 20, "query": "个税申报流程是什么", "expected_tools": ["filing_guide"]},

    # B 表双工具用例（v1.1 新增：先 fill_tax_form 再计税）
    {"id": 21, "query": "我是个体户，帮我填B表再算税", "expected_tools": ["fill_tax_form", TAX_TOOL]},
    {"id": 22, "query": "个体工商户申报B表，先填基础信息再计税", "expected_tools": ["fill_tax_form", TAX_TOOL]},

    # 邻域混淆用例（v1.1 新增：验证主 Agent 不会误派）
    {"id": 23, "query": "个税APP怎么退税", "expected_tools": ["filing_guide"]},
    {"id": 24, "query": "租房扣除标准", "expected_tools": ["search_knowledge"]},
    {"id": 25, "query": "工资8000交多少税", "expected_tools": [TAX_TOOL]},
    {"id": 26, "query": "社保缴费比例", "expected_tools": [SOCIAL_TOOL]},
]


def extract_tool_calls(messages: list) -> list[str]:
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


def evaluate():
    agent = build_agent()
    results = []
    correct = 0
    total = len(EVAL_SET)

    print(f"=== Agent 工具选择评测 ({total} 条) | AGENT_MODE={AGENT_MODE} ===\n")

    for item in EVAL_SET:
        qid = item["id"]
        query = item["query"]
        expected = item["expected_tools"]
        config = {"configurable": {"thread_id": f"eval-{qid}"}}

        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": query}]},
                config=config,
            )
            actual_tools = extract_tool_calls(result["messages"])

            # 判定：所有期望工具都在实际调用列表中
            hit = all(e in actual_tools for e in expected)
            if hit:
                correct += 1
                status = "✅"
            else:
                status = "❌"

            results.append({
                "id": qid,
                "query": query[:40],
                "expected": expected,
                "actual": actual_tools,
                "hit": hit,
            })

            print(f"  {status} #{qid:2d} 期望={expected} 实际={actual_tools}")
            if not hit:
                print(f"       query: {query}")

        except Exception as e:
            results.append({
                "id": qid,
                "query": query[:40],
                "expected": expected,
                "actual": [],
                "hit": False,
                "error": str(e),
            })
            print(f"  ❌ #{qid:2d} 异常: {e}")

    # 按工具分类统计
    print(f"\n=== 分类统计 ===")
    categories = {
        "search_knowledge": [],
        TAX_TOOL: [],
        SOCIAL_TOOL: [],
        "fill_tax_form": [],
        "filing_guide": [],
    }
    for r in results:
        for cat in categories:
            if cat in r["expected"]:
                categories[cat].append(r)

    for cat, items in categories.items():
        hits = sum(1 for i in items if i["hit"])
        total_cat = len(items)
        rate = hits / total_cat * 100 if total_cat else 0
        print(f"  {cat:30s} {hits}/{total_cat} ({rate:.0f}%)")

    # 总结
    accuracy = correct / total * 100
    print(f"\n=== 总准确率: {correct}/{total} ({accuracy:.1f}%) ===")
    if accuracy >= 90:
        print("🎉 达标（≥90%）")
    else:
        print("⚠️ 未达标（<90%），需分析失败 case 调优 System Prompt / docstring")

    # 一致性硬校验（v1.3: multi 形态下断言无 "not registered" 错误）
    if AGENT_MODE == "multi":
        errors_with_not_registered = []
        for r in results:
            if r.get("error") and "not registered" in str(r.get("error", "")):
                errors_with_not_registered.append(r)
        if errors_with_not_registered:
            print(f"\n⚠️ 一致性硬校验失败: {len(errors_with_not_registered)} 条 'not registered' 错误")
            for r in errors_with_not_registered:
                print(f"   #{r['id']}: {r.get('error')}")
        else:
            print("\n✅ 一致性硬校验通过: 0 条 'not registered' 错误")

    # 导出报告
    report_path = Path(__file__).parent / "agent_eval_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "agent_mode": AGENT_MODE,
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy, 1),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    evaluate()
