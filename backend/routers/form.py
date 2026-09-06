"""申报表生成 + 下载路由 — 直接调 fill_tax_form 脚本，不走 Agent"""
import importlib.util
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 按需加载 scripts/fill_tax_form.py
_scripts_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "fill_tax_form.py"
_spec = importlib.util.spec_from_file_location("_routers_fill_tax_form", _scripts_path)
_fill_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fill_module)
fill_form_fn = _fill_module.fill_form
TEMPLATES_DIR = _fill_module.TEMPLATES_DIR

# 已生成表单的唯一合法下载根（防任意文件读取：download 只允许 outputs/ 内文件）
OUTPUTS_DIR = (Path(__file__).resolve().parent.parent.parent / "outputs").resolve()

router = APIRouter(prefix="/api/form", tags=["申报表"])


@router.post("/generate")
async def generate_form(request: Request):
    """直接生成申报表 xlsx，不走 Agent。返回文件路径供前端下载。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON")

    form_type = body.get("form_type", "")
    user_data = body.get("user_data", {})

    if not form_type:
        raise HTTPException(status_code=422, detail="缺少 form_type")

    result_json = fill_form_fn(form_type, user_data)
    result = json.loads(result_json)

    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("message", "填表失败"))

    return {
        "success": True,
        "file_path": result["file"],
        "form_type": result["form_type"],
        "filled_fields": result.get("filled_fields", 0),
        "skipped_fields": result.get("skipped_fields", []),
    }


@router.get("/download")
async def download_form(path: str = Query(default="", description="xlsx 文件路径"), blank: str = Query(default="", description='blank_A表 或 blank_B表 获取空白模板')):
    """下载已填好的 xlsx 或空白模板。

    安全约束（2026-08-13）：path 仅允许解析后位于 outputs/ 目录内的文件，
    防任意文件读取；空白模板走内置白名单映射。
    """
    if blank:
        form_type = blank.replace("blank_", "")
        form_config = {
            "A表": "个人所得税基础信息表（A表）/个人所得税基础信息表（A表）纸质表单.xlsx",
            "B表": "个人所得税基础信息表（B表）/个人所得税基础信息表（B表）纸质表单.xlsx",
        }
        if form_type not in form_config:
            raise HTTPException(status_code=404, detail="未知表单类型")
        file_path = TEMPLATES_DIR / form_config[form_type]
    else:
        # 路径白名单：解析真实路径后必须仍在 outputs/ 内（resolve 处理 .. 穿越）
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = OUTPUTS_DIR / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            raise HTTPException(status_code=404, detail="文件不存在")
        if not resolved.is_relative_to(OUTPUTS_DIR):
            raise HTTPException(status_code=400, detail="非法的下载路径")
        file_path = resolved

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = file_path.name
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
