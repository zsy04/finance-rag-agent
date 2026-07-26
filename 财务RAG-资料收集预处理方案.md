# 财务 RAG Agent · 资料收集预处理方案

> **文档类型**：前期准备部署方案 | **决策日期**：2026-07-26 | **项目**：毕设
> **关联文档链**：`财务RAG-资料收集蓝图.md`（概念层）→ `财务RAG-MVP资料收集执行表.md`（清单层）→ **本文档**（部署层）→ `财务RAG-技术架构与Agent方案.md`（编码层）
> **本文定位**：资料收集阶段的唯一执行依据。不涉及编码、向量库部署、前端开发。系统架构与 Agent 设计见技术方案文档。

---

## 一、资料收集全景回顾

经过三轮迭代，项目文档的演进路径如下：

```
蓝图（概念层）        →  执行表（清单层）        →  方案（部署层）
 7大知识域/51项           5大模块/70项+链接          4阶段/含目录结构
 "收集什么"              "从哪里收集"               "怎么组织、怎么验证"
```

本文档基于执行表中的 70 项资料清单，定义收集阶段的目标产出物、目录结构、元数据标准、执行步骤和质量检查标准。

---

## 二、关键决策摘要

> 以下决策均通过对话逐项确认，作为本方案的约束条件。

| # | 决策项 | 结论 |
|:--:|------|------|
| D1 | 资料范围 | 全国统一政策 + 河南郑州地方政策（后续城市可插拔扩展） |
| D2 | 完成标准 | 70 项资料全部收集 → PDF 转 Markdown → 为切分向量化做好准备 |
| D3 | 执行策略 | 分两轮：第一轮网页类（~50 项）→ 第二轮 PDF 类（~20 项） |
| D4 | 分块粒度 | 目标 800 tokens/chunk，每个 chunk 为独立 Q&A 单元 |
| D5 | 目录结构 | `rag-data/raw/`（原始）+ `rag-data/processed/`（处理后 Markdown） |
| D6 | 元数据标准 | YAML frontmatter：source_url, doc_number, effective_from, expiry_date, module, category, city, doc_title |
| D7 | 申报材料生成 | 方案1 字段映射填表；MVP 支持 3 种申报表；保留空白原表供下载 |
| D8 | PDF 转换工具 | **Microsoft MarkItDown v0.1.6**，已验证可用 |
| D9 | 来源锚定 | 所有操作指引、即问即答统一指向河南省税务局（`henan.chinatax.gov.cn`） |

> 📎 技术架构与 Agent 设计 → 见 `财务RAG-技术架构与Agent方案.md`

---

## 三、目标产出物

### 3.1 目录结构

收集完成后，在项目根目录生成以下结构：

```
F:\lest\rag-data\
│
├── README.md                        # 目录说明 + 处理流程手册
│
├── manifest.json                    # 70项收集进度追踪文件
│
├── raw/                             # 原始下载文件（不改动）
│   ├── pdf/                         # 所有 PDF 原文
│   └── web/                         # 网页原文 HTML（转换前保留）
│
├── processed/                       # 转换清洗后的最终交付物
│   │
│   ├── national/                    # 全国统一政策（模块一~四）
│   │   ├── tax_law/                 # #1-#7  税法原文 .md
│   │   ├── qa_corpus/               # #8-#12 即问即答 .md
│   │   ├── rates/                   # #26-#34 税率表 .json
│   │   ├── operations/              # #35-#43 操作指引 .md
│   │   └── templates/               # #44-#55 申报表模板（.md + 空白原表 .pdf）
│   │
│   └── cities/                      # 城市差异化覆盖（模块五）
│       └── zhengzhou/
│           ├── social_insurance.json # #56 社保缴费标准
│           ├── housing_fund.json     # #57 公积金政策
│           ├── medical.md            # #58-#60 医保报销规则
│           └── tax_operations.md     # #61-#65 地方电子税务局操作
```

### 3.2 manifest.json 结构

```json
[
  {
    "id": 1,
    "name": "中华人民共和国个人所得税法（2018修正）",
    "status": "pending",
    "round": 1,
    "format": "md",
    "module": "一",
    "category": "tax_law",
    "source_url": "https://www.gov.cn/guoqing/2021-10/29/content_5647614.htm",
    "doc_number": "主席令第9号",
    "local_path": null,
    "notes": ""
  }
]
```

### 3.3 元数据标准

每个 `processed/` 下的 `.md` 文件**必须以 YAML frontmatter 开头**：

```yaml
---
source_url: https://www.gov.cn/zhengce/content/202308/content_6901206.htm
doc_number: 国发〔2023〕13号
effective_from: 2023-01-01
expiry_date: null
module: 一
category: tax_law
city: national
doc_title: 国务院关于提高个人所得税有关专项附加扣除标准的通知
---
```

### 3.4 JSON 结构化数据示例

```json
{
  "city": "郑州", "province": "河南",
  "effective_from": "2025-07-01", "effective_to": "2026-06-30",
  "social_avg_wage": 6385,
  "base_min": 3831, "base_max": 19155,
  "insurance": {
    "pension":    { "employer_rate": 0.16, "employee_rate": 0.08 },
    "medical":    { "employer_rate": 0.07, "employee_rate": 0.02 },
    "unemployment": { "employer_rate": 0.007, "employee_rate": 0.003 },
    "work_injury": { "employer_rate_min": 0.002, "employer_rate_max": 0.019, "employee_rate": 0 },
    "maternity":  { "employer_rate": 0.01, "employee_rate": 0 }
  },
  "flexible_employment": {
    "pension": { "rate": 0.20, "base_options": [3831,5108,6385,12770,19155] },
    "medical": { "base": 5108, "rate": 0.10 }
  }
}
```

---

## 四、执行步骤

### 阶段 1：环境准备

| 步骤 | 操作 | 产出 |
|:--:|------|------|
| 1.1 | 创建 `rag-data/` 完整目录树 | 目录就绪 |
| 1.2 | 创建 `manifest.json`（70 项均为 pending） | 进度追踪文件 |
| 1.3 | 安装 PDF→MD 转换工具 | 已安装 **Microsoft MarkItDown v0.1.6**（`pip install 'markitdown[pdf]'`），路径：`C:/Users/22808/.workbuddy/binaries/python/envs/default/Scripts/markitdown` | ✅ 已完成 |
| 1.4 | 用 1~2 个 PDF 小样本测试转换质量 | 已验证：税法类 PDF（政府网站渲染型）内容混入了大量导航/页眉/页脚噪声，正文提取质量⸺。**结论见下方工具评估** | ✅ 已完成 |

### 阶段 2：第一轮 — 网页类资料（按批次顺序执行）

| 批次 | 内容 | 编号 | 数量 | 备注 |
|------|------|:--:|:--:|------|
| 2.1 | 税法核心 | #1-#7 | 7 | 个税法、实施条例、汇缴办法、专项扣除、扣缴办法、年终奖 |
| 2.2 | 即问即答 | #8-#12 | 5 | RAG 最优质料源，Q&A 天然结构 |
| 2.3 | 小企业与个体户 | #13-#16 | 4 | 个体户计税办法、小微优惠、增值税减免、六税两费 |
| 2.4 | 社保与房产 | #17-#21 | 5 | 社保法、公积金条例、降费方案、契税法、车辆购置税法 |
| 2.5 | 操作指引 | #35-#43 | 9 | 个税APP操作、专项扣除填报、个体户申报、小规模申报 |
| 2.6 | 填报规则 | #50-#55 | 6 | 申报表填报说明、汇算公式、豁免条件、申报地规则 |
| 2.7 | 郑州web类 | #58-#65 | 8 | 医保规则、电子税务局操作入口 |
| 2.8 | 自建资料 | #22-#25 | 4 | 税率速查表、专项扣除速查表、发票大全、含税价转换 |

**每批次的处理流程**：
1. 打开 source_url → 复制网页正文
2. 清洗 HTML 标签（保留表格结构）
3. 添加 YAML frontmatter（来源 + 文号 + 时效）
4. 保存到 `processed/` 对应子目录
5. 在 `manifest.json` 中更新 status → done

### 阶段 3：第二轮 — PDF 类资料

| 批次 | 内容 | 编号 | 数量 | 说明 |
|------|------|:--:|:--:|------|
| 3.1 | 法律 PDF | #1, #13, #17, #18 | 4 | 先以网页版 MD 为基础，PDF 作为校对源 |
| 3.2 | 申报表模板 | #44-#49 | 6 | **保留原 PDF**（供用户空白下载）+ 转 MD（供字段映射） |
| 3.3 | 结构化 JSON | #26-#34 | 9 | 税率表、专项扣除标准等，全部手动整理为 JSON |

> ⚠️ PDF→MD 完成后必须验证：表格完整性、特殊符号（‰、{}）、文号、金额数字

### 阶段 4：质量检查

| 检查项 | 通过标准 |
|--------|---------|
| 完整性 | `manifest.json` 中 #1-#65 全部 status = done（#66-#70 标 pending/Phase2） |
| 元数据 | 每个 `.md` 文件包含完整 YAML frontmatter（8 个字段） |
| 可追溯 | source_url 字段指向有效官方链接 |
| JSON 校验 | 每个 `.json` 文件通过 `JSON.parse()` 无报错 |
| 空白表保留 | `templates/` 下 3 种空白表 PDF 可正常下载打开 |
| 时效标注 | 时间敏感数据（社保基数/优惠截止）标注 effective_from 和 expiry_date |

---

## 五、PDF 转换工具评估：Microsoft MarkItDown

### 安装与可用性

```
工具：Microsoft MarkItDown v0.1.6
仓库：https://github.com/microsoft/markitdown
安装：pip install 'markitdown[pdf]'
路径：C:/Users/22808/.workbuddy/binaries/python/envs/default/Scripts/markitdown
状态：✅ 已安装、已导入、CLI 正常、Python API 正常
```

### 实测结论

用国家税务总局政策法规库的 PDF 做样本测试，结论如下：

| 场景 | 表现 | 对本项目的建议 |
|------|------|--------------|
| 政府网站渲染型 PDF（税法公告、通知全文） | 正文混入大量导航/页眉/页脚/侧边栏噪声，需手工清洗 | **不用 PDF 源**，改直接从网页 HTML 版抓取 → 清洗 → 存 MD |
| 申报表模板 PDF（A表/B表等） | 可提取文字字段，表格结构部分保留 | **双轨**：保留原 PDF 供下载 + 转 MD 供字段映射 |
| 原生文档型 PDF（法律出版社电子版等） | 转换质量良好 | 可用 MarkItDown 一键转换 |

### 对 70 项收集策略的调整

| 类型 | 原定计划 | 调整后 |
|------|---------|--------|
| 税法原文 #1-#7 | PDF → MD | **网页 HTML → MD**（政府网站网页比 PDF 干净得多） |
| 即问即答 #8-#12 | 网页 → MD | 不变 |
| 操作指引 #35-#43 | 网页 → MD | 不变 |
| 申报表模板 #44-#49 | PDF → MD | **双轨**：MarkItDown 转 MD + 保留 PDF 原件 |
| 郑州 #58-#65 | 网页 → MD | 不变 |

> **结论**：MarkItDown 对财务 RAG 项目主要价值在于申报表模板 PDF 的转换。税法原文/政策公告的最佳来源是政府网站 HTML 版。

---

## 六、明确不在本期范围

| 事项 | 归属阶段 |
|------|---------|
| 资料切分（chunking） | 下一阶段（向量化前） |
| Embedding + Qdrant 写入 | 开发阶段 |
| 混合检索 + 重排实现 | 开发阶段 |
| 申报材料字段映射逻辑编码 | 开发阶段 |
| 前端界面开发 | 开发阶段 |
| #66-#70 郑州特色政策 | Phase 2（答辩后） |
| 其他城市扩展（北京/上海/深圳） | Phase 2 |

---

## 七、文档关联图谱

```
财务RAG-资料收集蓝图.md              概念层  "收集什么"
        │
        ▼
财务RAG-MVP资料收集执行表.md          清单层  "从哪收集"（70项+链接）
        │
        ▼
财务RAG-资料收集预处理方案.md         部署层  "怎么执行"（本文）
        │
        ▼
财务RAG-技术架构与Agent方案.md        编码层  "怎么搭建"（系统设计）
```
