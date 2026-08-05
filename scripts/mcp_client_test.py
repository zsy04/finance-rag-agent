"""MCP Client 调用验证 — 对拍 scripts/mcp_server_demo.py

对应《财务RAG-工程收尾待办清单》§1 验收标准：
① MCP 标准协议下能 list_tools + call_tool；
② 计算结果与既有工具一致（同一输入对拍）。

用法（stdio 模式，直接拉起 server 子进程）：
  python scripts/mcp_client_test.py

预期输出：
  ── 1. list_tools ──
  工具数量: 3
  ...（工具名 + 描述摘要）
  ── 2. call_tool: calculate_income_tax ──
  年收入: 96000 元（salary，计入比例 100%）
  应纳税所得额: 36000.00 元
  应纳税额: 1080.00 元
  ...
  ✅ 结果中包含 result_card，MCP 链路验证通过
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).resolve().parent / "mcp_server_demo.py"


def _pretty_summary(text: str) -> str:
    """把工具返回的 JSON 字符串解析后只打印关键行，便于人眼对拍。"""
    try:
        data = json.loads(text)
        answer = data.get("answer", "")
        lines = [l for l in answer.split("\n") if any(k in l for k in ("年收入", "应纳税所得额", "应纳税额", "适用税率", "月缴合计", "推荐"))]
        return "\n".join(lines)
    except json.JSONDecodeError:
        return text[:300]


async def main() -> None:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── 1. list_tools ──
            print("── 1. list_tools ──")
            tools = await session.list_tools()
            print(f"工具数量: {len(tools.tools)}")
            for t in tools.tools:
                print(f"  · {t.name}: {t.description[:40]}...")
            assert len(tools.tools) >= 3, "工具数量不足 3 个"
            print("✅ list_tools 通过\n")

            # ── 2. call_tool: 个税（含年终奖对比） ──
            print("── 2. call_tool: calculate_income_tax ──")
            res = await session.call_tool(
                "calculate_income_tax",
                {"annual_income": 96000, "income_type": "salary",
                 "social_insurance": 0, "deductions": {}, "bonus": 0},
            )
            text = res.content[0].text if res.content else ""
            print(_pretty_summary(text))
            assert "result_card" in text, "返回值缺少 result_card"
            assert "1080.00" in text, "对拍失败：96000 年收入（无扣除）应纳税额应为 1080.00"
            print("✅ 个税对拍通过（96000 → 1080.00）\n")

            # ── 3. call_tool: 社保（郑州，单位职工） ──
            print("── 3. call_tool: query_social_insurance ──")
            res = await session.call_tool(
                "query_social_insurance",
                {"salary": 8000, "employment_type": "employee"},
            )
            text = res.content[0].text if res.content else ""
            print(_pretty_summary(text))
            assert "result_card" in text, "返回值缺少 result_card"
            print("✅ 社保调用通过\n")

            # ── 4. call_tool: 经营所得（个体户 B 表） ──
            print("── 4. call_tool: calculate_business_tax_mcp ──")
            res = await session.call_tool(
                "calculate_business_tax_mcp",
                {"period": "quarter", "income": 300000, "cost": 120000},
            )
            text = res.content[0].text if res.content else ""
            print(_pretty_summary(text))
            assert "result_card" in text, "返回值缺少 result_card"
            print("✅ 经营所得调用通过\n")

            print("══ 全部通过：list_tools + 3 个工具 call_tool 均正常 ══")


if __name__ == "__main__":
    asyncio.run(main())
