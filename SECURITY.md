# 安全政策

## 支持的版本

当前项目处于活跃开发状态，仅最新的 main 分支版本接收安全更新。

| 版本 | 支持状态 |
| --- | --- |
| main (最新) | :white_check_mark: |
| < 1.0 | :x: |

## 报告漏洞

### 如何报告

如果您发现安全漏洞，**请勿**通过公开 Issue 报告。请通过以下方式联系：

- **邮箱**：[在此填入联系邮箱]
- **响应时间**：我们会在 48 小时内确认收到，并在 7 个工作日内提供初步评估

### 报告应包含

1. **漏洞描述**：详细说明安全问题的性质
2. **影响范围**：受影响的组件、版本
3. **复现步骤**：如何触发该漏洞
4. **潜在影响**：可能导致的安全风险
5. **修复建议**（可选）

## 安全最佳实践

### 1. API 密钥管理

**禁止**将 API 密钥提交到版本控制：
```bash
# ❌ 错误做法
git add backend/.env
git commit -m "add config"

# ✅ 正确做法
cp backend/.env.example backend/.env
# 编辑 .env 填入真实密钥（已在 .gitignore 中排除）
```

**密钥轮换**：
- 定期更换 `DEEPSEEK_API_KEY`（建议每 90 天）
- 如发现密钥泄露，立即在 [DeepSeek 控制台](https://platform.deepseek.com/api_keys) 删除旧密钥并生成新密钥

### 2. 生产环境配置

**CORS 限制**：
```python
# .env 生产配置
ALLOWED_ORIGINS=https://your-domain.com
```

**数据库访问控制**：
- 生产环境切换至 PostgreSQL（SQLite 仅适用于开发/演示）
- 启用数据库连接加密
- 定期备份 `backend/data/chat.db`

### 3. 防注入措施

项目已实施以下安全措施：
- ✅ 三层标签隔离（`<user_input>`/`<context>`/`<tool_result>`）
- ✅ Canary 探针（`canary-7f3a9c`）
- ✅ 输出侧审计（`routers/chat.py:_audit_security`）
- ⚠️ 已知限制：防注入评测 8/10 通过，存在 2 条边界用例

**用户输入验证**：
```python
# 所有用户输入都经过 Pydantic 验证
class ChatRequest(BaseModel):
    message: str = Field(max_length=2000)  # 限制长度
```

### 4. 依赖项安全

**定期更新**：
```bash
# 检查依赖漏洞（使用 pip-audit）
pip install pip-audit
pip-audit -r requirements.txt

# 更新依赖
pip install --upgrade -r requirements.txt
```

**锁定版本**：
- `requirements.txt` 已固定主版本号（如 `langchain>=1.3.0,<2.0.0`）
- 前端依赖使用精确版本（`package-lock.json` 锁定）

### 5. 日志安全

**敏感数据脱敏**：
```python
# ✅ 正确：仅记录必要上下文
logger.info("工具审计 thread_id=%s: %s", thread_id, tool_names)

# ❌ 错误：记录完整用户输入
logger.info("用户输入: %s", user_message)  # 可能含身份证/手机号
```

## 已知安全限制

### 1. 防注入未完全覆盖
- **状态**：防注入评测 8/10 通过
- **风险**：1 条心算诱导失败 + 1 条过度拦截误伤
- **缓解措施**：输出侧审计告警（日志监控）
- **修复计划**：P0 优先级修复中

### 2. SQLite 并发限制
- **状态**：当前使用 SQLite（单文件数据库）
- **风险**：多进程写入可能冲突
- **适用场景**：单用户演示/开发环境
- **生产方案**：迁移至 PostgreSQL（见 `storage/sqlite_store.py` 接口设计）

### 3. 模型切换器 SSRF 风险
- **状态**：用户可自定义 `base_url`
- **缓解措施**：
  - 自定义 base_url 必须提供 api_key（禁止回退服务端密钥）
  - 文档警告：仅连接可信端点
- **限制**：无 URL 白名单校验

## 安全开发检查清单

提交代码前请确认：

- [ ] 无硬编码密钥（`git grep -i "sk-"`）
- [ ] `.env` 文件已在 `.gitignore` 中
- [ ] 用户输入已验证（Pydantic models）
- [ ] 敏感日志已脱敏
- [ ] 外部请求已添加超时（`timeout=30`）
- [ ] SQL 查询使用参数化（避免注入）
- [ ] 文件路径已校验（避免路径穿越）

## 致谢

感谢所有负责任地披露安全问题的研究人员。贡献者将在修复后被公开致谢（如您希望）。
