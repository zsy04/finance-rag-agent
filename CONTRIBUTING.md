# 贡献指南

感谢你考虑为财税助手项目贡献代码！本指南将帮助你快速上手。

## 行为准则

参与本项目即表示你同意遵守我们的[行为准则](CODE_OF_CONDUCT.md)。请友善、尊重地对待所有贡献者。

## 如何贡献

### 报告 Bug

在提交 Bug 前，请先搜索 [Issues](https://github.com/zsy04/lest/issues) 确认问题是否已存在。

**好的 Bug 报告应包含**：
- **标题**：简洁描述问题
- **环境**：操作系统、Python 版本、依赖版本
- **复现步骤**：详细的步骤，最好附带最小复现用例
- **预期行为**：你期望发生什么
- **实际行为**：实际发生了什么
- **截图/日志**（可选）：帮助理解问题

### 建议新功能

功能建议请通过 [Issue](https://github.com/zsy04/lest/issues/new) 提交，说明：
- **用例**：这个功能解决什么问题？
- **建议方案**：你设想的实现方式
- **替代方案**：是否考虑过其他方案？
- **优先级**：对你的工作影响程度

### 提交 Pull Request

1. **Fork 仓库**并克隆到本地：
   ```bash
   git clone https://github.com/YOUR-USERNAME/lest.git
   cd lest
   ```

2. **创建分支**：
   ```bash
   git checkout -b feat/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

3. **配置开发环境**：
   ```bash
   # 后端
   cd backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   
   # 前端
   cd frontend
   npm install
   ```

4. **进行修改**并确保：
   - 代码符合项目规范（见下文）
   - 添加了必要的测试
   - 通过所有测试
   - 更新了相关文档

5. **提交代码**：
   ```bash
   git add .
   git commit -m "feat: 添加 XXX 功能"
   # 提交信息格式见下文
   ```

6. **推送到 Fork 仓库**：
   ```bash
   git push origin feat/your-feature-name
   ```

7. **创建 Pull Request**：
   - 填写 PR 模板（标题、描述、测试方法）
   - 关联相关 Issue（`Closes #123`）
   - 等待代码审查

## 开发规范

### 提交信息格式

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型（type）**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档变更
- `style`: 代码格式（不影响逻辑）
- `refactor`: 重构
- `test`: 添加测试
- `chore`: 构建/工具变更

**示例**：
```
feat(agent): 添加年终奖计算工具

实现个税年终奖单独计税与并入综合所得的对比计算。

Closes #42
```

### 代码规范

#### Python（后端）

- **风格**：遵循 [PEP 8](https://pep8.org/)
- **类型注解**：函数签名必须添加类型提示
- **文档字符串**：公共 API 使用 Google 风格 docstring
- **导入顺序**：标准库 → 第三方 → 本地模块

**示例**：
```python
def calculate_tax(income: float, deductions: float = 0) -> dict[str, Any]:
    """计算个人所得税。

    Args:
        income: 年收入（元）
        deductions: 专项附加扣除（元，默认0）

    Returns:
        包含 tax_amount、effective_rate 的字典
    """
    # 实现
```

**运行检查**：
```bash
cd backend
# 暂无 linter 配置，建议手动检查 PEP 8
python -m pytest tests/  # 运行测试
```

#### TypeScript（前端）

- **风格**：使用 oxlint 检查
- **组件**：函数式组件 + TypeScript
- **命名**：
  - 组件：PascalCase（`ChatView.tsx`）
  - 函数/变量：camelCase
  - 常量：UPPER_SNAKE_CASE

**运行检查**：
```bash
cd frontend
npm run lint      # Oxlint 检查
npm run build     # TypeScript 编译检查
```

### 测试要求

- **新功能**：必须包含单元测试
- **Bug 修复**：添加回归测试防止复现
- **覆盖率**：核心计算引擎（`services/tax_engine.py`）需达到 80%+

**运行测试**：
```bash
# 后端
cd backend
python eval/run_all.py  # 运行评测（检索+工具+生成+防注入）

# 前端（待添加）
cd frontend
npm test
```

## 项目结构

```
backend/
├── agent/           # Agent 引擎与 prompts
├── rag/             # RAG 检索链路
├── services/        # 计算引擎（税率/社保，纯代码零幻觉）
├── tools/           # 8 个 @tool 工具
├── routers/         # FastAPI 路由
├── eval/            # 四层评测
└── storage/         # SQLite 持久化

frontend/
└── src/
    ├── components/  # React 组件
    ├── hooks/       # 自定义 Hooks
    └── lib/         # 工具函数与类型
```

**关键文件**：
- `backend/config.py` - 全局配置
- `backend/agent/prompts.py` - Agent 系统提示词
- `backend/services/tax_engine.py` - 税率计算核心
- `frontend/src/lib/types.ts` - 前后端类型契约

## 常见任务

### 添加新工具（Tool）

1. 在 `backend/tools/` 创建新文件（如 `my_tool.py`）
2. 使用 `@tool` 装饰器定义：
   ```python
   from langchain_core.tools import tool
   from tools.base import tag_tool_result
   
   @tool
   def my_tool(param: str) -> str:
       """工具描述（LLM 可见）。
       
       Args:
           param: 参数说明
       """
       result = {"answer": "xxx", "data": {}}
       return tag_tool_result(result)
   ```
3. 在 `backend/tools/__init__.py` 导出
4. 在 `backend/agent/engine.py` 的 `ALL_TOOLS` 列表中添加
5. 添加测试用例到 `backend/eval/agent_eval.py`

### 修改税率数据

税率表位于 `rag-data/processed/national/rates/`：
- `income_tax_rates.json` - 个税综合所得
- `business_income_rates.json` - 经营所得
- 等

修改后重新向量化：
```bash
cd scripts
python embed_and_upsert.py
```

### 更新前端 UI

1. 修改 `frontend/src/components/` 下的组件
2. 确保符合设计令牌（见 `docs/主题文档/财务RAG-前端设计文档.md`）
3. 本地测试：`npm run dev`
4. 构建检查：`npm run build`

## 获取帮助

- **文档**：先查阅 `docs/主题文档/` 下的设计文档
- **Issue 讨论**：在相关 Issue 下提问
- **邮件**：[在此填入联系邮箱]

## 许可证

提交 Pull Request 即表示你同意将代码以 [MIT License](LICENSE) 授权给本项目。

---

再次感谢你的贡献！🎉
