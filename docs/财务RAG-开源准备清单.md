# 财务RAG-开源准备清单

> 定位：GitHub 仓库 `zsy04/finance-rag-agent` 转 Public 前的**检查与执行清单**。
> 创建：2026-08-05。状态：✅ **2026-08-06 已基本完成**——git rm --cached 已提交（47f6f04）、仓库已转 Public（匿名访问 HTTP 200）、8-06 最新成果（设计稿落地/SQLite 持久化/主题文档）已准备好提交推送

---

## 1. 排除清单（已落实 .gitignore）

> ⚠️ 核心规则：**.gitignore 只对"未跟踪"文件生效，已在 git 索引里的文件必须 `git rm --cached` 才会真正移除**（本地文件保留）。

### 1.1 演示材料（已排除）

| 文件 | 说明 |
|------|------|
| `docs/财务RAG-产品定义文档.md` | 演示策略（30s 开场/演示/深度问答） |
| `docs/财务RAG-项目综合文档.md` | 论文/演示一站式文档（含 PPT 大纲、演示脚本） |
| `docs/财务RAG-项目复盘报告.md` | 内部复盘（个人反思） |
| `docs/财务RAG-后端审查与重构方案.md` | 内部审查 |
| `docs/财务RAG-前端代码审查报告.md` | 内部审查 |
| `docs/财务RAG-后端代码审查报告.md` | 内部审查 |
| `docs/主题文档/财务RAG-演示与论文材料.md` | 演示/论文/复盘/展示主题整合版（2026-08-06 重组新增） |
| `docs/主题文档/财务RAG-评测与质量文档.md` | 含前后端内部审查记录（P-01~P-16 / C1~L5），随审查类排除 |

### 1.2 展示相关（已排除）

| 文件 | 说明 |
|------|------|
| `docs/财务RAG-展示技术补强-概念梳理.md` | 个人 JD 对标、展示规划（2026-08-05 补充） |

### 1.3 部署策略（已排除）

| 文件 | 说明 |
|------|------|
| `docs/服务器部署指南.md` | 服务器部署细节（含路径/环境） |
| `docs/启动指导.md` | 本机启动说明 |
| `docs/主题文档/财务RAG-部署运维文档.md` | 部署运维主题整合版（含本机路径/启动细节，2026-08-06 随部署策略类排除） |
| `start.bat` | 本地启动脚本 |
| `**/Dockerfile`、`**/nginx.conf`、`**/.dockerignore` | Docker 构建细节 |
| `docker-compose.yml` | 完整编排（含后端/前端镜像构建） |

> 保留：`docker-compose.qdrant.yml`（仅 Qdrant，README 快速启动依赖，无敏感信息）。

> **2026-08-06 追加**：SQLite 对话库 `backend/data/`（chat.db）已加入排除——含真实用户对话数据，绝不上传。

### 1.4 源文本数据（排除）+ 向量数据（入库）

> **决策定案（2026-08-06，二轮调整）**：`embed_and_upsert.py` 重建向量库**只读 `chunks.jsonl`**（已含全部分块文本）。因此——**chunks.jsonl 入库公开**（3.1MB，clone 后直接重建 Qdrant）；**源文本（原始下载/清洗后法规/问答语料）本地保留**（数据资产考量，且重建非必需）。

| 路径 | 说明 |
|------|------|
| ✅ `rag-data/chunks.jsonl` | **入库**：向量化分块文本（3.1MB），`embed_and_upsert.py` 唯一输入，重建 Qdrant 必需 |
| 🚫 `rag-data/raw/` | 原始下载文件（20MB，本地保留） |
| 🚫 `rag-data/staging/` | 原始法规 .doc/.html（12MB，本地保留） |
| 🚫 `rag-data/processed/national/tax_law/` | 清洗后法规 MD（1.1MB，本地保留） |
| 🚫 `rag-data/processed/national/qa_corpus/` | 问答语料（1.6MB，本地保留） |
| 🚫 `rag-data/processed/national/operations/` | 操作指引（本地保留） |

> 结构化数据（代码运行时依赖，已入库）：`processed/national/rates/*.json`、`processed/national/templates/form_field_map.json`、`processed/cities/zhengzhou/social_insurance.json`、`processed/metadata/cities_index.json`、`relations.json`、`manifest.json`。

### 1.5 个人/生成物（已排除）

| 路径 | 说明 |
|------|------|
| `outputs/` | 个人文档、头像、测试导出 xlsx（未跟踪 ✅） |
| `backend/eval/report.json` | 评测生成物 |
| `.env` / `*.env` | 密钥 |

---

## 2. 待执行：移除已跟踪文件（用户手动执行）

```bash
# 进入仓库根目录
cd /f/lest

# 移除训练数据（120 个原始法规文件，本地保留）
git rm -r --cached rag-data/staging

# 移除演示/展示/部署文档（本地保留）
git rm --cached "docs/启动指导.md" "docs/服务器部署指南.md" \
  "docs/财务RAG-产品定义文档.md" "docs/财务RAG-后端审查与重构方案.md" \
  "docs/财务RAG-展示技术补强-概念梳理.md"

# 确认 staging 已从索引消失（预期输出为空）
git ls-files rag-data/staging/

# 提交
git commit -m "chore: 开源准备 — 排除训练数据/演示/部署/展示文档"
```

> 注意：转 Public 前**先推送这次提交**，确认远程仓库已不含上述文件，再改 visibility。

---

## 3. 转 Public 前最终检查清单

- [x] 上述 `git rm --cached` 已执行并提交、推送（commit 47f6f04，2026-08-05）
- [x] `git ls-files` 全量扫一遍无遗漏敏感文件（2026-08-06 复查：仅 .env.example 占位保留）
- [x] README 已重写（2026-08-05 版），badge/技术栈与代码一致（React 19 ✅）
- [x] README 中不引用被排除的文档（演示策略/部署指南等；2026-08-06 主题文档索引已收敛为 6 份公开文档）
- [x] GitHub 仓库 Settings → Danger Zone → Change visibility → Public（2026-08-06 已转，匿名访问 HTTP 200）
- [ ] 推送 8-06 最新提交后，确认首页渲染正常、README 图片/链接无 404
- [x] 确认无 DEEPSEEK_API_KEY 等密钥暴露（.env.example 可保留为占位；.env 从未进过 git 历史）

---

## 4. 开源后建议

| 事项 | 说明 |
|------|------|
| Star/README 头图 | 可用 frontend 截图或架构图做 hero 图 |
| Issues 模板 | 可加 `bug_report.md` / `feature_request.md` |
| LICENSE | MIT 已声明（README badge），建议补 LICENSE 文件 |
| 评测数据 | eval/ 下评测集与报告是开源亮点，保留 ✅ |
| 贡献指南 | 可选：CONTRIBUTING.md |
