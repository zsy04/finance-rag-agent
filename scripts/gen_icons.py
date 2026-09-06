"""
财税助手 - SVG 图标批量生成
方案A: 手写规范 SVG，2px stroke, #1E3A8A, 圆角端点, 透明背景, currentColor
"""

import os
from pathlib import Path

OUT = str(Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons")
C = "#1E3A8A"  # fallback color
SW = "stroke-width=\"2\""
LC = 'stroke-linecap="round"'
LJ = 'stroke-linejoin="round"'
FN = 'fill="none"'
SA = f'stroke="{C}" {SW} {LC} {LJ} {FN}'

def svg(vb, body, w=24, h=24):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{h}">
{body}
</svg>'''

# ─── 1. Logo (64x64) ──────────────────────────────────────────
icons = {}
icons["logo.svg"] = svg("0 0 64 64", f'''
  <!-- Shield -->
  <path d="M32 8 L52 16 L52 32 C52 44 42 54 32 58 C22 54 12 44 12 32 L12 16 Z" {SA}/>
  <!-- Calculator -->
  <rect x="24" y="22" width="16" height="22" rx="2" {SA}/>
  <line x1="24" y1="29" x2="40" y2="29" {SA}/>
  <line x1="28" y1="34" x2="28" y2="35" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="33" y1="34" x2="33" y2="35" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="38" y1="34" x2="38" y2="35" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="28" y1="39" x2="28" y2="40" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="33" y1="39" x2="33" y2="40" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="38" y1="39" x2="38" y2="40" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <!-- Speech bubble accent -->
  <path d="M46 12 C49 12 51 14 51 17 C51 20 49 22 46 22 L44 22 L41 25 L41 22 C39 21 37 19 37 17 C37 14 39 12 43 12 Z" {SA}/>
''', 64, 64)

# ─── 2. icon-chat 对话气泡 ─────────────────────────────────
icons["icon-chat.svg"] = svg("0 0 24 24", f'''
  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" {SA}/>
  <line x1="8" y1="10" x2="16" y2="10" {SA}/>
  <line x1="8" y1="14" x2="13" y2="14" {SA}/>
''')

# ─── 3. icon-calculator 计算器 ─────────────────────────────
icons["icon-calculator.svg"] = svg("0 0 24 24", f'''
  <rect x="5" y="2" width="14" height="20" rx="2" {SA}/>
  <rect x="7" y="4" width="10" height="5" rx="1" fill="{C}" fill-opacity="0.1" stroke="{C}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="9" cy="14" r="0.8" fill="{C}"/>
  <circle cx="12" cy="14" r="0.8" fill="{C}"/>
  <circle cx="15" cy="14" r="0.8" fill="{C}"/>
  <circle cx="9" cy="18" r="0.8" fill="{C}"/>
  <circle cx="12" cy="18" r="0.8" fill="{C}"/>
  <circle cx="15" cy="18" r="0.8" fill="{C}"/>
''')

# ─── 4. icon-document 文档 ─────────────────────────────────
icons["icon-document.svg"] = svg("0 0 24 24", f'''
  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" {SA}/>
  <polyline points="14 2 14 8 20 8" {SA}/>
  <line x1="8" y1="13" x2="16" y2="13" {SA}/>
  <line x1="8" y1="17" x2="16" y2="17" {SA}/>
  <line x1="8" y1="9" x2="12" y2="9" {SA}/>
''')

# ─── 5. icon-help 帮助/问号 ────────────────────────────────
icons["icon-help.svg"] = svg("0 0 24 24", f'''
  <circle cx="12" cy="12" r="10" {SA}/>
  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" {SA}/>
  <circle cx="12" cy="17" r="0.5" fill="{C}" stroke="none"/>
''')

# ─── 6. icon-warning 警告三角 ─────────────────────────────
icons["icon-warning.svg"] = svg("0 0 24 24", f'''
  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" {SA}/>
  <line x1="12" y1="9" x2="12" y2="13" {SA}/>
  <circle cx="12" cy="17" r="0.6" fill="{C}" stroke="none"/>
''')

# ─── 7. icon-location 定位针 ──────────────────────────────
icons["icon-location.svg"] = svg("0 0 24 24", f'''
  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" {SA}/>
  <circle cx="12" cy="9" r="2.5" {SA}/>
''')

# ─── 8. icon-loading 加载圆环 ─────────────────────────────
icons["icon-loading.svg"] = svg("0 0 24 24", f'''
  <path d="M21 12a9 9 0 1 1-6.219-8.56" {SA}/>
''')

# ─── 9. icon-send 发送/纸飞机 ────────────────────────────
icons["icon-send.svg"] = svg("0 0 24 24", f'''
  <line x1="22" y1="2" x2="11" y2="13" {SA}/>
  <polygon points="22 2 15 22 11 13 2 9 22 2" {SA}/>
''')

# ─── 10. icon-confirm 确认/勾选 ───────────────────────────
icons["icon-confirm.svg"] = svg("0 0 24 24", f'''
  <polyline points="20 6 9 17 4 12" {SA}/>
''')

# ─── 11. icon-edit 编辑/铅笔 ─────────────────────────────
icons["icon-edit.svg"] = svg("0 0 24 24", f'''
  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" {SA}/>
  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" {SA}/>
''')

# ─── 12. icon-retry 重试/循环箭头 ─────────────────────────
icons["icon-retry.svg"] = svg("0 0 24 24", f'''
  <polyline points="23 4 23 10 17 10" {SA}/>
  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" {SA}/>
''')

# ─── 13. icon-save 保存/软盘 ──────────────────────────────
icons["icon-save.svg"] = svg("0 0 24 24", f'''
  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" {SA}/>
  <polyline points="17 21 17 13 7 13 7 21" {SA}/>
  <polyline points="7 3 7 8 15 8" {SA}/>
''')

# ─── 14. icon-generate 魔法棒 ─────────────────────────────
icons["icon-generate.svg"] = svg("0 0 24 24", f'''
  <path d="M15 4V2a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v2" {SA}/>
  <path d="M15 4H9v2h6V4z" {SA}/>
  <line x1="18" y1="14" x2="5" y2="14" {SA}/>
  <line x1="7.5" y1="7.5" x2="6" y2="6" {SA}/>
  <line x1="15.5" y1="7.5" x2="17" y2="6" {SA}/>
  <line x1="7.5" y1="10.5" x2="5.5" y2="8.5" {SA}/>
  <line x1="15.5" y1="10.5" x2="17.5" y2="8.5" {SA}/>
  <path d="M3 21l2-7 7 2-2 7-7-2z" {SA}/>
''')

# ─── 15. icon-download 下载 ───────────────────────────────
icons["icon-download.svg"] = svg("0 0 24 24", f'''
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" {SA}/>
  <polyline points="7 10 12 15 17 10" {SA}/>
  <line x1="12" y1="15" x2="12" y2="3" {SA}/>
''')

# ─── 16. icon-blank-doc 空白文档 ──────────────────────────
icons["icon-blank-doc.svg"] = svg("0 0 24 24", f'''
  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" {SA}/>
  <polyline points="14 2 14 8 20 8" {SA}/>
''')

# ─── Favicon SVG 变体 ─────────────────────────────────────
icons["favicon.svg"] = svg("0 0 64 64", f'''
  <path d="M32 8 L52 16 L52 32 C52 44 42 54 32 58 C22 54 12 44 12 32 L12 16 Z" {SA}/>
  <rect x="24" y="22" width="16" height="22" rx="2" {SA}/>
  <line x1="24" y1="29" x2="40" y2="29" {SA}/>
  <line x1="28" y1="34" x2="28" y2="35" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="33" y1="34" x2="33" y2="35" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="38" y1="34" x2="38" y2="35" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="28" y1="39" x2="28" y2="40" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="33" y1="39" x2="33" y2="40" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <line x1="38" y1="39" x2="38" y2="40" stroke-width="3" stroke="{C}" stroke-linecap="round" fill="none"/>
  <path d="M46 12 C49 12 51 14 51 17 C51 20 49 22 46 22 L44 22 L41 25 L41 22 C39 21 37 19 37 17 C37 14 39 12 43 12 Z" {SA}/>
''', 64, 64)

# ─── 写入所有文件 ─────────────────────────────────────────
os.makedirs(OUT, exist_ok=True)
for name, content in icons.items():
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ {name}")

print(f"\nDone! Generated {len(icons)} SVG files in {OUT}")
