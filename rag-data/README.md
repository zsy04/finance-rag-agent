# rag-data — 财务 RAG 知识库资料目录

> 这是项目的资料仓库。**不是临时目录，不要删除。**

---

## 目录结构

```
rag-data/
├── README.md                           ← 你在这里
├── manifest.json                       ← 70 项资料清单参考
│
├── staging/                            ← 下载的网页放这里 → 清洗后转到 processed/
│   └── metadata.json                   ← 元数据映射（文件名 → 标题/来源/分类）
│
├── raw/                                ← 原始文件，不改动
│   └── pdf/                            ← 下载的 PDF 原件（申报表模板等）
│
└── processed/                          ← 最终交付物
    ├── national/
    │   ├── tax_law/                    ← 税法/社保/房产原文 .md
    │   ├── qa_corpus/                  ← 即问即答 .md（RAG 最优质料源）
    │   ├── rates/                      ← 税率表 .json（结构化，供程序计算）
    │   ├── operations/                 ← 操作指引+自建资料 .md
    │   └── templates/                  ← 申报表模板（.md + 空白 .pdf）
    │
    └── cities/
        └── zhengzhou/
            ├── social_insurance.json
            ├── housing_fund.json
            ├── medical.md
            └── tax_operations.md
```

---

## 工作流程

```
浏览器打开法规页面 → 另存为 .html → 放入 staging/
                                              ↓
                    编辑 staging/metadata.json 填元数据
                                              ↓
                    python scripts/clean_to_md.py
                                              ↓
                    processed/ 下生成干净的 .md
                    （YAML frontmatter + 清洗后正文）
```

### 第一步：下载网页到 staging/

浏览器打开法规页面 → 右键"另存为" → 保存类型选 **"网页, HTML 仅 HTML"** → 保存到 `rag-data/staging/`。

文件名随意，但建议用中文方便辨认，如 `个税法.html`、`住房租金热点问答.html`。

### 第二步：编辑 metadata.json

打开 `rag-data/staging/metadata.json`，为每个 HTML 文件添加一条记录：

```json
{
  "个税法.html": {
    "doc_title": "个人所得税法（2018修正）",
    "source_url": "https://www.gov.cn/guoqing/2021-10/29/content_5647614.htm",
    "doc_number": "主席令第9号",
    "module": "一",
    "category": "tax_law",
    "city": "national"
  }
}
```

| 字段 | 说明 | 必填 |
|------|------|:--:|
| `doc_title` | 文档标题，也是输出文件名 | ✅ |
| `source_url` | 原始来源 URL | ✅ |
| `category` | 决定输出到哪个子目录（见下表） | ✅ |
| `doc_number` | 文号，如 国发〔2023〕13号 | |
| `module` | 所属模块：一/二/三/四/五 | |
| `city` | national（全国）/ zhengzhou（郑州） | |
| `effective_from` | 生效日期 | |
| `expiry_date` | 失效日期 | |

**category → 输出目录映射：**

| category | 输出到 | 适用资料 |
|----------|--------|---------|
| `tax_law` | `national/tax_law/` | 税法、社保法、契税法等法律原文 |
| `qa_corpus` | `national/qa_corpus/` | 即问即答、热点问答 |
| `operations` | `national/operations/` | 操作指引、填报说明、速查表 |
| `templates` | `national/templates/` | 申报表模板 |
| `rates` | `national/rates/` | 税率表（仅限 JSON，HTML 转来的放 operations） |

如果 `city` 填 `zhengzhou`，自动路由到 `cities/zhengzhou/`，不按 category 走。

### 第三步：批量转换

```bash
cd F:\lest

# 预览（不实际写入）
python scripts/clean_to_md.py --dry-run

# 正式转换
python scripts/clean_to_md.py
```

每条命令只转 staging/ 下有对应 metadata 的文件，不会遗漏也不会多转。

### 第四步：人工校对

转换完必须检查：
- [ ] 税率、金额数字是否准确
- [ ] 表格是否完整（无缺行列）
- [ ] 特殊符号（‰、〔〕、{}）是否正常显示
- [ ] YAML frontmatter 中文号、来源是否写对

---

## 其他类型资料

**JSON 结构化数据（11 项）**：税率表 #26-#34 + 郑州社保公积金 #56-#57。对照 `财务RAG-MVP资料收集执行表.md` 中的 JSON schema 手动填入，放到 `processed/national/rates/` 或 `cities/zhengzhou/`。

**自建资料（4 项）**：常用税率速查表 #22、专项扣除速查表 #23、发票大全 #24、含税价转换 #25。纯 Markdown 手写。

**申报表 PDF（6 项）**：#44-#49 从税总公告附件下载 → PDF 原件放 `raw/pdf/` → 用 MarkItDown 转 MD → 放 `processed/national/templates/`。

> 备选：如果以后想从 URL 直接抓取而非手动下载，可以用 `scripts/fetch_and_process.py`。但 gov.cn 的 JS 渲染页面不支持，chinatax.gov.cn 可用。

---

## 下一步

资料收集完成 → 切分 Markdown 为 800-token chunks → BGE-M3 embedding → Qdrant 写入。详见 `财务RAG-技术架构与Agent方案.md`。
