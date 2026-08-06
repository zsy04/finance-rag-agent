"""持久化存储层（用户上下文持久化 §5.1）

- MemoryStore 抽象接口 + SQLiteStore 实现（sqlite3 标准库，零外部依赖）
- 后期换 MongoDB：仅替换实现类，业务侧零改动
"""
