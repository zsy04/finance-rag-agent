"""个税申报表填表工具 — 包装 scripts/fill_tax_form.py

将对话中收集的用户信息填入申报表模板（A表/B表），生成填好的 xlsx 文件。
纯 openpyxl 字段映射填表，不走 LLM。
"""

import importlib.util
import json
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# 按需加载 scripts/fill_tax_form.py，避免污染全局 sys.path
_scripts_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "fill_tax_form.py"
_spec = importlib.util.spec_from_file_location("_scripts_fill_tax_form", _scripts_path)
_scripts_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scripts_module)
fill_form = _scripts_module.fill_form
_get_required_fields_raw = _scripts_module.get_required_fields


class FillFormInput(BaseModel):
    """申报表填写输入参数。"""
    form_type: str = Field(
        description='表单类型: "A表"（扣缴义务人填报）或 "B表"（纳税人自行申报）'
    )
    user_data: dict = Field(
        description='用户信息字典，key 为字段名，value 为字段值。必填字段: 纳税人姓名、身份证件类型、身份证件号码、出生日期、国籍/地区。可选: 手机号码、联系地址、开户银行、银行账号等'
    )


@tool(args_schema=FillFormInput)
def fill_tax_form(form_type: str, user_data: dict) -> str:
    """填写个税申报表。当用户说"生成申报表""填写申报表""填表""申报材料""基础信息表""个税申报""帮我填报"等请求时**立即调用此工具**，不要先收集信息。用户已提供的字段直接传入 user_data，缺失字段工具会自动跳过。会将用户信息填入官方模板生成 xlsx 文件。

    参数:
        form_type: 表单类型: "A表"（单位职工，扣缴义务人填报）或 "B表"（自行申报，个体户/自由职业者）
        user_data: 用户信息字典。
            A表常见字段（雇员）:
                - 纳税人姓名, 身份证件类型, 身份证件号码, 出生日期, 国籍/地区
                - 扣缴义务人名称, 扣缴义务人识别号, 任职受雇从业类型, 职务, 手机号码
            B表常见字段（个体户）:
                - 纳税人姓名, 身份证件类型, 身份证件号码, 出生日期, 国籍/地区
                - 被投资单位名称（个体工商户名称）, 被投资单位信用代码（统一社会信用代码）
                - 经营收入, 成本费用, 自己交的社保, 以前年度亏损, 申报周期
                - 注意: B表不填任职单位信息（个体户没有雇主）
    """
    # 调用现有 fill_form 函数
    result_json = fill_form(form_type, user_data)
    result = json.loads(result_json)

    if not result.get("success"):
        return json.dumps(
            {"answer": f"填表失败: {result.get('message', '未知错误')}"},
            ensure_ascii=False,
        )

    # 构建回答文本
    answer_parts = [
        f"申报表（{form_type}）已生成成功！",
        f"已填写 {result.get('filled_fields', 0)} 个字段",
    ]
    if result.get("skipped_fields"):
        answer_parts.append(f"跳过未知字段: {', '.join(result['skipped_fields'])}")

    answer_parts.append(f"文件路径: {result.get('file', '')}")
    answer_parts.append("同时保留了空白原表供下载核对。")

    result_card = {
        "type": "form_result",
        "data": {
            "form_type": form_type,
            "file_path": result.get("file", ""),
            "filled_fields": result.get("filled_fields", 0),
            "skipped_fields": result.get("skipped_fields", []),
        },
    }

    return json.dumps(
        {
            "answer": "\n".join(answer_parts),
            "result_card": result_card,
        },
        ensure_ascii=False,
    )


@tool
def get_required_fields(form_type: str) -> str:
    """获取个税申报表的必填字段列表。当用户想生成申报表但还不清楚需要提供哪些信息时，先调用此工具了解必填字段。

    参数:
        form_type: 表单类型: "A表" 或 "B表"
    """
    # 调用原始函数（注意：不能用同名变量，否则递归调用自身）
    result_json = _get_required_fields_raw(form_type)
    return result_json  # 直接返回原始 JSON，LLM 可读取字段列表
