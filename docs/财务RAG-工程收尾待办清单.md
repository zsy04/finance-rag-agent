# 财务RAG-工程收尾待办清单

> 定位：lest 项目**剩余工程项**的执行清单，承接《财务RAG-项目补充与添加实施规划》中尚未落地的条目。
> 创建：2026-08-05。更新：—
> 原则：每一项都是独立可交付任务，动手前先在本文档勾选 ⬜ → 拆分任务 → 写代码 → 跑对应评测。

---

## 0. 总览（3 项待办 + 1 项暂缓）

| # | 待办项 | 优先级 | 工作量 | 状态 |
|---|---|---|---|---|
| 1 | **MCP Server 封装**（个税计算工具） | 🥈 P1 | 1-2 天 | 🔲 |
| 2 | **评测集扩展 + 评测自动化**（40→60 条 + run_all.py） | 🥉 P2 | 1 天 | 🔲 |
| 3 | **MongoDB 用户上下文存储**（或 JSON 文件低配替代） | 🥉 P2 | 1 天 | 🔲 可选 |
| — | ~~LlamaIndex 对比 demo~~ | — | 半天 | ⏸️ **暂缓**（2026-08-05 决定暂不做，论文"技术选型对比"章节改以既有评测数据 + MCP demo 支撑；如需对比素材可随时恢复） |

> 已完成的补充项（不再重复）：历史摘要器 ✅、TokenBudget ✅（参数固化于摘要器）、ContextEvaluator ✅、Multi-Agent 化 ✅、对话历史摘要裁剪 ✅（已被 history_summarizer 覆盖）。

---

## 1. MCP Server 封装（P1，1-2 天）

### 目标
把 `calculate_income_tax`（+ 可选 `query_social_insurance`）封装成标准 MCP Server（FastMCP），验证"任何 MCP 兼容宿主可调用"。求职差异化亮点：MCP 18 轮学习笔记的工程落地。

### 为什么现在补
- 求职向：MCP 是 2025 后 Agent 互操作的事实标准，亲手封装一个可讲完整的协议链路
- 复用既有引擎：`services/tax_engine.py` 核心逻辑已就绪，不重复实现，半天即可跑通

### 改动文件
- 新增 `scripts/mcp_server_demo.py`（FastMCP，注册 calculate_income_tax）
- 新增 `scripts/mcp_client_test.py`（MCP Client 调用验证）

### 实施步骤
1. `pip install mcp`（仅开发环境，不引入运行时依赖——答辩环境约束）
2. `FastMCP("tax-calc")` 注册工具，直接复用 `services/tax_engine.py` 计算函数
3. 启动 server，用 MCP Client 或 `mcporter` 调用验证
4. 验证后在《求职技术补强-概念梳理》§5 补一段实战记录

### 验收标准
① MCP 标准协议下能 list_tools + call_tool；② 计算结果与既有工具一致（同一输入对拍）。

> ⚠️ 注意：MCP SDK 需联网安装，答辩现场离线时不做现场安装——demo 代码入库即可。

---

## 2. 评测集扩展 + 评测自动化（P2，1 天）

### 目标
- eval_set.json 40 条 → 60 条（重点补：个体户 B 表、年终奖、汇算清缴案例、专项附加扣除边界值）
- 三层评测串成一键脚本：检索层 + 工具层 + 生成层单命令出报告

### 为什么现在补
- 论文/答辩素材：更多评测样本 = 更可信的数据；run_all.py 现场演示"一键评测"很有说服力
- 防过拟合：评测集扩到 60 条后再跑 recall@5，验证 77.5% 不是"背题"

### 改动文件
- 修改 `backend/eval/eval_set.json`（**追加不覆盖**，遵守数据资产只增不改约定）
- 新增 `backend/eval/run_all.py`（检索层 eval.py + 工具层 agent_eval.py + 生成层 context_eval.py 一键串跑，输出三层报告）

### 实施步骤
1. 设计新增 20 条 query（与既有 10 类场景对齐，标注类别）
2. 先跑一遍新评测集，确认 recall@5 不降（若降 → 按"诊断根因 → 修复"循环）
3. 实现 run_all.py：子进程或 import 方式串跑三个评测模块，聚合输出报告
4. 出基线报告存证（答辩数据）

### 验收标准
① 新评测集跑通且 recall@5 ≥ 77.5% 不降；② `python eval/run_all.py` 单命令输出三层报告。

---

## 3. MongoDB 用户上下文存储（P2，1 天，可选）

### 目标
把 `tools/user_context.py` 的 in-memory dict 换成持久化存储，解决进程重启丢记忆问题。

### 为什么现在补（可选）
- 完整版体验：重启后端后同一 thread_id 上下文仍在
- 若不想引入新依赖，用"JSON 文件持久化"作为低配替代（不动 Docker 编排）

### 改动文件
- 修改 `backend/tools/user_context.py`（存储层抽象：`MemoryStore` 接口 + `MongoStore` / `JsonFileStore` 实现）
- 若选 MongoDB：`docker-compose.yml` 加 mongo 服务 + `requirements.txt` 加 pymongo

### 实施步骤
1. 定义 `MemoryStore` 接口（get/set/update），in-memory 实现保持现状为默认
2. 实现 `JsonFileStore`（低配，零依赖）或 `MongoStore`
3. 配置开关切换存储后端
4. 验证：重启后端后同一 thread_id 上下文仍在

### 验收标准
① 重启后端后上下文不丢；② 工具接口对外不变（Agent/前端零感知）。

> 建议：优先做 JSON 文件方案（半天），MongoDB 版本按答辩时间余量取舍。

---

## 4. 执行顺序建议

```
P1 优先级（求职/答辩收益高）
  └─→ ① MCP Server 封装（1-2 天）
P2 按时间余量
  ├─→ ② 评测集扩展 + run_all.py（1 天）—— 答辩前必做，数据即素材
  └─→ ③ MongoDB / JSON 持久化（半天-1 天）—— 答辩演示"重启不丢"加分项
⏸️ LlamaIndex 暂缓（不排期）
```

> 排期原则：**答辩/面试优先**——MCP 讲的是协议工程能力，评测自动化讲的是工程素养，二者都是"可讲 5 分钟"的素材；MongoDB 是加分项。
