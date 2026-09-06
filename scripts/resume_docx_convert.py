"""基于 Aspose 图形化简历模板 docx 改内容并导出 PDF（多岗位参数化版）。
用法: python resume_docx_convert.py <java|agent>
- 解析 word/document.xml，遍历所有 w:txbxContent 节点
- 按"内容指纹"识别四大块：个人信息 / 技术栈 / 项目经历 / 相关技能
- 项目经历：18 段替换（3 项目 = 5 + 1 空 + 6 + 1 空 + 5）
- 每段都是单 w:t 直接替换文本，保留段样式
- 写回 docx → 用 docx2pdf (Word COM) 转 PDF
"""
import os
import shutil
import sys
import zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

SRC = r'F:\lest\outputs\简历-周嵩原.docx'
OUT_DIR = r'F:\lest\outputs'
BACKUP = r'F:\lest\outputs\简历-周嵩原-通用版-原版备份.docx'

# ============ 岗位配置 ============
CONFIGS = {
    # ---------- Java 后端（电商 SaaS） ----------
    'java': {
        'suffix': 'Java后端-电商SaaS定制版',
        'personal': {
            '求职意向：Java 后端 / AI 应用': '求职意向：Java 后端开发（电商 SaaS / 高并发分布式）',
            '期望城市：苏州/杭州/郑州/天津': '期望城市：北京/杭州/苏州',
            '期望薪资：面议': '期望薪资：8k-10k',
        },
        'tech_stack': [
            '后端：Java 21/17、Python；Spring Boot 3、MyBatis-Plus、Spring Security',
            '数据库/中间件：MySQL、Redis、RabbitMQ、RocketMQ、Redisson、Caffeine、MinIO',
            '分布式：MQ 异步削峰、三级缓存、限流（滑动窗口/令牌桶）、幂等、分布式锁',
            '部署：Docker、Docker Compose、K8s、Linux、Git、JMeter 压测',
            'AI/前端：Vue 3、React（了解）、LangChain Agent、RAG 全链路、SSE｜GitHub：github.com/zsy04',
        ],
        'skills': [
            'Java 基础扎实：OOP / 集合 / 异常 / 多线程；Spring Boot 全流程开发',
            '分布式工程：MQ 削峰、三级缓存、限流、分布式锁、幂等、最终一致性实战',
            'Spring Boot + MyBatis-Plus + MySQL + Redis + RabbitMQ 全链路实战',
            'LangChain Agent 编排 + RAG 全链路（BGE-M3 + Qdrant + BGE-Reranker）',
            'GitHub 开源项目 + 50+ 篇全生命周期工程文档（PRD/架构/评测/复盘）',
            'Docker 容器化部署 + Linux + Git + JMeter 压测 + 评测驱动迭代',
        ],
        'projects': [
            # 打印驿站 5 段
            '打印驿站 — 校园打印快递服务平台',
            'Java 17 + Spring Boot 3 + MyBatis-Plus + MySQL + Redis + RabbitMQ + Redisson + Vue 3｜独立开发',
            'V1.0→V1.5 五次架构演进，覆盖从单体到高并发分布式的完整后端工程场景。',
            '｜MQ 削峰：下单拆"受理+建单"两阶段，RT 从 500ms+ 降至 50ms 以下',
            '｜三级缓存 + 双算法限流 + 三层幂等 + 死信延迟取消兜底',
            '',
            # DoVideoAI 6 段
            'DoVideoAI — 长视频内容理解平台',
            'Java 21 + Spring Boot 3.5 + MyBatis-Plus + RocketMQ + Redis + MySQL + MinIO｜独立开发',
            '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
            '｜分布式：RocketMQ 异步削峰，Redisson 锁防重 + Redis+MySQL Checkpoint 断点恢复',
            '｜高可用：双限流（用户级+全局令牌桶）+ Qdrant 不可用降级纯关键词',
            '｜上传：5MB 分片 + 断点续传 + MinIO 存储 + SSE 实时进度推送',
            '',
            # FinRAG 5 段
            'FinRAG 财税助手 — RAG Agent 开源项目',
            'Python + FastAPI + LangChain + BGE-M3 + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
            '面向零财务基础大众的 AI 问答助手，覆盖个税计算、社保查询、政策问答。',
            '｜RAG：四层分层检索，Recall@5 67.5%→85%，8 轮迭代驱动',
            '｜评测驱动：60+26+长对话+对拍四层评测，工具路由准确率 100%',
        ],
        'must_have': [
            'Java 后端开发（电商 SaaS',
            '期望城市：北京/杭州/苏州',
            '期望薪资：8k-10k',
            '打印驿站 — 校园打印快递服务平台',
            'DoVideoAI — 长视频内容理解平台',
            'FinRAG 财税助手 — RAG Agent 开源项目',
            '｜MQ 削峰：下单拆"受理+建单"两阶段，RT 从 500ms+ 降至 50ms 以下',
            'Recall@5 67.5%→85%',
            'Java 21/17、Python；Spring Boot 3',
            'Docker Compose、K8s、Linux',   # 技术栈含 K8s
            'Java 基础扎实',
            'GitHub 开源项目 + 50+ 篇',
        ],
        'must_not_have': [
            '财务 RAG Agent', 'AI 智能客服系统', '打印接单系统',
            '求职意向：Java 后端 / AI 应用',
            '期望城市：苏州/杭州/郑州/天津', '期望薪资：面议',
            '（Java 高并发主项目）', '（Java 全栈深度）', '（技术广度）',
            'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
            'Java / Python 双语言开发，熟悉面向对象与多线程',
        ],
    },

    # ---------- LLM Agent 工程师 ----------
    'agent': {
        'suffix': 'LLM-Agent工程师定制版',
        'personal': {
            '求职意向：Java 后端 / AI 应用': '求职意向：LLM Agent 工程师 / AI Agent 应用开发',
            '期望城市：苏州/杭州/郑州/天津': '期望城市：北京/杭州/苏州',
            '期望薪资：面议': '期望薪资：8k-10k',
        },
        'tech_stack': [
            'AI/Agent：LangChain Agent、Multi-Agent、AgentLoop(Planner-Executor-Critic)、MCP 封装',
            'RAG：BGE-M3 混合检索、Qdrant、BGE-Reranker 精排、Recall@5 85%',
            '上下文：Prompt/Context Engineering、防注入、SSE 流式',
            '后端：Python(FastAPI)、Java 21(Spring Boot + MyBatis-Plus + RocketMQ)',
            '部署：Docker、Docker Compose、K8s、Linux、Git、MinIO、限流/降级/幂等｜GitHub：github.com/zsy04',
        ],
        'skills': [
            'Agent 工程化：LangChain Agent 完整落地 + Multi-Agent 架构 + AgentLoop 闭环 + MCP 标准化封装',
            '系统级评测：四层自动化评测基准 + 回归脚本，工具路由准确率 100%，指标驱动调优',
            'RAG 全链路：数据清洗→切分→混合检索→重排→评测迭代，Recall@5 85%',
            '上下文工程：提取式压缩 + 历史摘要 + 防注入，长对话 40K 不爆窗',
            '高吞吐高可用：FastAPI SSE 流式、Docker 部署、限流/降级/幂等/分布式锁',
            '开源生态：GitHub 开源项目 + 50+ 篇文档，持续跟进 Agent/LLM 生态新进展',
        ],
        'projects': [
            # FinRAG 5 段
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'Python + FastAPI + LangChain + BGE-M3 + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
            '面向零财务基础大众的 AI 问答助手，实现提问→检索→工具调用→生成→出表完整闭环。',
            '｜Multi-Agent 双子架构：主 Agent 意图路由 → tax/social 子 Agent，领域隔离防 prompt 污染',
            '｜8 个 @tool + 四层评测基准(60+26+长对话+对拍)：工具路由 100%，Recall@5 67.5%→85%',
            '',
            # DoVideoAI 6 段
            'DoVideoAI — 长视频 Video Agent 平台',
            'Java 21 + Spring Boot 3 + RocketMQ + Redis + MySQL + MinIO + Qdrant + LangChain4j｜独立开发',
            '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
            '｜AgentLoop 闭环：Planner 拆解 → Executor 带证据结论 → Critic 校验，2 轮上限 + 600s 超时',
            '｜多模态上下文：ASR 语音 + OCR 关键帧双路并行，感知哈希去重，单路失败另一路保留',
            '｜高可用：混合检索优雅降级 + Checkpoint 断点恢复 + 双限流 + RocketMQ 削峰',
            '',
            # 抖音电商 5 段
            '抖音电商数智员工 — 自动化运营 Agent',
            'Python + FastAPI + APScheduler + LangChain + DeepSeek + SQLite｜独立开发',
            '抖音电商运营自动化原型，6 个业务规则自动触发 + AI 数智员工复盘 + 人工确认兜底。',
            '｜Agent 双层路由：预置 4 类问题规则路由 + 自由提问 LLM 路由，未配 Key 自动降级',
            '｜工程可靠性：StateMachine 白名单状态机 + 三重幂等 + 52 项冒烟测试',
        ],
        'must_have': [
            'LLM Agent 工程师 / AI Agent 应用开发',
            '期望城市：北京/杭州/苏州',
            '期望薪资：8k-10k',
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'DoVideoAI — 长视频 Video Agent 平台',
            '抖音电商数智员工 — 自动化运营 Agent',
            'Multi-Agent 双子架构：主 Agent 意图路由',
            'AgentLoop 闭环：Planner 拆解',
            '四层评测基准',
            'AI/Agent：LangChain Agent、Multi-Agent',
            'Docker Compose、K8s、Linux',   # 技术栈含 K8s
            '系统级评测：四层自动化评测基准',
        ],
        'must_not_have': [
            '财务 RAG Agent', 'AI 智能客服系统', '打印接单系统',
            '求职意向：Java 后端 / AI 应用',
            '期望城市：苏州/杭州/郑州/天津', '期望薪资：面议',
            '（Java 高并发主项目）', '（Java 全栈深度）', '（技术广度）',
            'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
            'Java / Python 双语言开发，熟悉面向对象与多线程',
        ],
    },

    # ---------- 综合版（Java 后端 + LLM 应用 + 实习） ----------
    'combo': {
        'suffix': '综合版-Java后端+LLM应用',
        'skill_title': '实习与技能',   # 相关技能区标题（含实习经历）
        'personal': {
            '求职意向：Java 后端 / AI 应用': '求职意向：Java 后端开发 / LLM 应用工程师',
            '期望城市：苏州/杭州/郑州/天津': '期望城市：北京/杭州/苏州',
            '期望薪资：面议': '期望薪资：8k-10k',
        },
        'tech_stack': [
            '后端：Java 21/17(Spring Boot 3 + MyBatis-Plus + Security)、Python 3.13(FastAPI)',
            '中间件/数据库：MySQL、Redis、RabbitMQ、RocketMQ、Redisson、Caffeine、MinIO、Qdrant',
            '分布式：MQ 异步削峰、三级缓存、限流（滑动窗口/令牌桶）、幂等、分布式锁',
            'AI/LLM：LangChain Agent、Multi-Agent、RAG 全链路（BGE-M3+Qdrant+Reranker）、MCP 封装、SSE',
            '部署：Docker、Docker Compose、K8s、Linux、Git、JMeter 压测｜GitHub：github.com/zsy04',
        ],
        'skills': [
            # 实习经历 3 段 + 关键技能 3 段（区标题改为"实习与技能"）
            '实习经历 — 河南智游盛景｜AI 应用开发实习生（RAG 方向）',
            '2025.07 - 2025.09｜Python + ChromaDB + BGE + LangChain',
            '｜300+ 份文档清洗流水线 + 50+ 条评测集，检索命中率 76%→86%',
            'Java 基础扎实 + 分布式工程：MQ 削峰、三级缓存、限流、幂等、分布式锁实战',
            'RAG 全链路：数据清洗→混合检索→重排→评测迭代，Recall@5 85%',
            '文档与产品化：50+ 篇工程文档 + GitHub 开源 + 习惯用 AI 工具提效',
        ],
        'projects': [
            # 打印驿站 5 段（Java 主推）
            '打印驿站 — 校园打印快递服务平台',
            'Java 17 + Spring Boot 3 + MyBatis-Plus + MySQL + Redis + RabbitMQ + Redisson｜独立开发',
            'V1.0→V1.5 五次架构演进，覆盖从单体到高并发分布式的完整后端工程场景。',
            '｜MQ 异步削峰(RT 500ms→50ms) + 三级缓存 + 双算法限流 + 三层幂等',
            '｜秒杀防超卖（Redis 预扣 + 唯一索引 + 乐观锁）+ Spring Security + JWT',
            '',
            # DoVideoAI 6 段
            'DoVideoAI — 长视频 Video Agent 平台',
            'Java 21 + Spring Boot 3 + RocketMQ + Redis + MySQL + MinIO + Qdrant + LangChain4j｜独立开发',
            '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
            '｜AgentLoop 闭环（Planner-Executor-Critic）+ 多模态上下文(ASR+OCR)',
            '｜混合检索优雅降级 + Checkpoint 断点恢复 + 双限流 + RocketMQ 削峰',
            '｜5MB 分片上传 + 断点续传 + MinIO + SSE 实时进度推送',
            '',
            # FinRAG 5 段
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'Python + FastAPI + LangChain + BGE-M3 + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
            '面向零财务基础大众的 AI 问答助手，实现提问→检索→工具调用→生成完整 Agent 闭环。',
            '｜四层 RAG 检索 + 四层评测基准：Recall@5 67.5%→85%，工具路由 100%',
            '｜数据工程：115+ 份文档清洗流水线 + MCP 插件封装（FastMCP）',
        ],
        'must_have': [
            'Java 后端开发 / LLM 应用工程师',
            '期望城市：北京/杭州/苏州',
            '期望薪资：8k-10k',
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'DoVideoAI — 长视频 Video Agent 平台',
            '打印驿站 — 校园打印快递服务平台',
            '实习与技能',               # 相关技能区标题已改
            '实习经历 — 河南智游盛景',
            '76%→86%',
            'Docker Compose、K8s、Linux',
            'Recall@5 67.5%→85%',
        ],
        'must_not_have': [
            '财务 RAG Agent', 'AI 智能客服系统', '打印接单系统',
            '求职意向：Java 后端 / AI 应用',
            '期望城市：苏州/杭州/郑州/天津', '期望薪资：面议',
            '（Java 高并发主项目）', '（Java 全栈深度）', '（技术广度）',
            'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
            'Java / Python 双语言开发，熟悉面向对象与多线程',
            '相关技能',                # 原标题已改为"实习与技能"
        ],
    },

    # ---------- 综合版两页（Java + LLM + 完整实习 + 教育背景） ----------
    'combo2': {
        'suffix': '综合版-Java后端+LLM应用-两页版',
        'two_page': True,   # 启用两页扩展布局（教育背景 + 完整实习）
        'personal': {
            '求职意向：Java 后端 / AI 应用': '求职意向：Java 后端开发 / LLM 应用工程师',
            '期望城市：苏州/杭州/郑州/天津': '期望城市：北京/杭州/苏州',
            '期望薪资：面议': '期望薪资：8k-10k',
        },
        'tech_stack': [
            '后端：Java 21/17(Spring Boot 3 + MyBatis-Plus + Security)、Python 3.13(FastAPI)',
            '中间件/数据库：MySQL、Redis、RabbitMQ、RocketMQ、Redisson、Caffeine、MinIO、Qdrant',
            '分布式：MQ 异步削峰、三级缓存、限流（滑动窗口/令牌桶）、幂等、分布式锁',
            'AI/LLM：LangChain Agent、Multi-Agent、RAG 全链路（BGE-M3+Qdrant+Reranker）、MCP 封装、SSE',
            '部署：Docker、Docker Compose、K8s、Linux、Git、JMeter 压测｜GitHub：github.com/zsy04',
        ],
        'skills': [
            'Java 基础扎实：OOP / 集合 / 异常 / 多线程；Spring Boot + MyBatis-Plus 全流程',
            '分布式工程：MQ 削峰、三级缓存、限流、分布式锁、幂等、最终一致性实战',
            'RAG 全链路：数据清洗→混合检索→重排→评测迭代，Recall@5 85%',
            'Agent 工程化：Multi-Agent 架构 + AgentLoop 闭环 + MCP 标准化封装',
            '文档与产品化：50+ 篇工程文档 + GitHub 开源 + 从 0 到 1 全流程交付',
            '协作与学习：2-3 人团队主负责人 + 双段企业实习，习惯用 AI 工具提升效率',
        ],
        'projects': [
            # 打印驿站 5 段（Java 主推）
            '打印驿站 — 校园打印快递服务平台',
            'Java 17 + Spring Boot 3 + MyBatis-Plus + MySQL + Redis + RabbitMQ + Redisson｜独立开发',
            'V1.0→V1.5 五次架构演进，覆盖从单体到高并发分布式的完整后端工程场景。',
            '｜MQ 异步削峰(RT 500ms→50ms) + 三级缓存 + 双算法限流 + 三层幂等',
            '｜秒杀防超卖（Redis 预扣 + 唯一索引 + 乐观锁）+ Spring Security + JWT',
            '',
            # DoVideoAI 6 段
            'DoVideoAI — 长视频 Video Agent 平台',
            'Java 21 + Spring Boot 3 + RocketMQ + Redis + MySQL + MinIO + Qdrant + LangChain4j｜独立开发',
            '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
            '｜AgentLoop 闭环（Planner-Executor-Critic）+ 多模态上下文(ASR+OCR)',
            '｜混合检索优雅降级 + Checkpoint 断点恢复 + 双限流 + RocketMQ 削峰',
            '｜5MB 分片上传 + 断点续传 + MinIO + SSE 实时进度推送',
            '',
            # FinRAG 5 段
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'Python + FastAPI + LangChain + BGE-M3 + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
            '面向零财务基础大众的 AI 问答助手，实现提问→检索→工具调用→生成完整 Agent 闭环。',
            '｜四层 RAG 检索 + 四层评测基准：Recall@5 67.5%→85%，工具路由 100%',
            '｜数据工程：115+ 份文档清洗流水线 + MCP 插件封装（FastMCP）',
        ],
        'edu_lines': [
            '黄河交通学院｜智能科学与技术｜本科｜2023.09 - 2027.06（2027 届）',
            '核心课程：数据结构与算法、操作系统、计算机网络、数据库原理、Java 程序设计、人工智能导论、机器学习',
            'GitHub 开源：github.com/zsy04/finance-rag-agent',
        ],
        'intern_lines': [
            '河南智游盛景旅游规划设计有限公司 — AI 应用开发实习生（RAG 方向）',
            '2025.07 - 2025.09｜Python + ChromaDB + BGE + LangChain｜300+ 份文档清洗流水线 + 50+ 条评测集，检索命中率 76%→86%',
            '',
            '河南同桌比邻教育科技有限公司 — 项目经理实习生（小程序方向）',
            '2026.01 - 2026.06｜2-3 人团队主负责人｜从 0 到 1 主导全流程 + 独立 PRD + 技术选型，按期交付上线',
        ],
        'must_have': [
            'Java 后端开发 / LLM 应用工程师',
            '期望城市：北京/杭州/苏州',
            '期望薪资：8k-10k',
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'DoVideoAI — 长视频 Video Agent 平台',
            '打印驿站 — 校园打印快递服务平台',
            '实习经历',                    # 第二页实习经历标题
            '河南智游盛景',
            '河南同桌比邻',
            '教育背景',                    # 第一页教育背景标题
            '黄河交通学院',
            '76%→86%',
            'Docker Compose、K8s、Linux',
            'Recall@5 67.5%→85%',
        ],
        'must_not_have': [
            '财务 RAG Agent', 'AI 智能客服系统', '打印接单系统',
            '求职意向：Java 后端 / AI 应用',
            '期望城市：苏州/杭州/郑州/天津', '期望薪资：面议',
            '（Java 高并发主项目）', '（Java 全栈深度）', '（技术广度）',
            'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
            'Java / Python 双语言开发，熟悉面向对象与多线程',
        ],
    },

    # ---------- Java 后端（AI 全栈方向） ----------
    'javaai': {
        'suffix': 'Java后端-AI全栈定制版',
        'enlarge_project': True,   # 项目技术栈较长，扩高项目区
        'personal': {
            '求职意向：Java 后端 / AI 应用': '求职意向：Java 后端开发（AI 全栈方向）',
            '期望城市：苏州/杭州/郑州/天津': '期望城市：北京/杭州/苏州',
            '期望薪资：面议': '期望薪资：8k-10k',
        },
        'tech_stack': [
            '后端：Java 21/17、Python；Spring Boot 3、MyBatis-Plus、Spring Security',
            '中间件：Redis、RabbitMQ、RocketMQ、Redisson、Caffeine、MinIO',
            '分布式：MQ 异步削峰、三级缓存、限流（滑动窗口/令牌桶）、幂等、分布式锁',
            'AI：LangChain Agent、Multi-Agent、RAG 全链路、MCP 封装、Vibe Coding 开发流',
            '部署：Docker、Docker Compose、K8s、Linux、Git、JMeter 压测｜GitHub：github.com/zsy04',
        ],
        'skills': [
            'Java 基础扎实：OOP / 集合 / 异常 / 多线程；Spring Boot + MyBatis-Plus 全流程',
            '分布式工程：MQ 削峰（RabbitMQ/RocketMQ）、三级缓存、限流、分布式锁、幂等实战',
            'AI Agent 开发经验：Multi-Agent 架构 + AgentLoop 闭环 + MCP 封装 + RAG 全链路',
            'Vibe Coding：深度使用 Codex/Copilot 等 AI 编程工具驱动开发全流程',
            '文档与画图：50+ 篇工程文档 + Mermaid/SVG 流程图、类图、时序图',
            '协作与学习：2-3 人团队主负责人 + 双段实习，热爱钻研 AI/Agent 前沿技术',
        ],
        'projects': [
            # 打印驿站 5 段（Java 主推）
            '打印驿站 — 校园打印快递服务平台',
            'Java 17 + Spring Boot 3 + MyBatis-Plus + MySQL + Redis + RabbitMQ + Redisson + Vue 3｜独立开发',
            'V1.0→V1.5 五次架构演进，覆盖从单体到高并发分布式的完整后端工程场景。',
            '｜MQ 异步削峰(RT 500ms→50ms) + 三级缓存 + 双算法限流 + 三层幂等',
            '｜秒杀防超卖（Redis 预扣 + 唯一索引 + 乐观锁）+ WebSocket 实时推送 + 压测',
            '',
            # DoVideoAI 6 段（Java + AI 全栈）
            'DoVideoAI — 长视频 Video Agent 平台',
            'Java 21 + Spring Boot 3 + RocketMQ + Redis + MySQL + MinIO + Qdrant + LangChain4j｜独立开发',
            '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
            '｜AgentLoop 闭环（Planner-Executor-Critic）+ 多模态上下文(ASR+OCR)',
            '｜RocketMQ 异步削峰 + Redisson 锁防重 + Checkpoint 断点恢复 + 双限流',
            '｜5MB 分片上传 + 断点续传 + MinIO + SSE 实时进度推送',
            '',
            # FinRAG 5 段（Agent 加分）
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'Python + FastAPI + LangChain + BGE-M3 + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
            '面向零财务基础大众的 AI 问答助手，实现提问→检索→工具调用→生成完整 Agent 闭环。',
            '｜Multi-Agent 双子架构 + 四层 RAG 检索：Recall@5 67.5%→85%，工具路由 100%',
            '｜MCP 插件封装 + 上下文工程 + FastAPI SSE 流式 + Docker Compose 部署',
        ],
        'must_have': [
            'Java 后端开发（AI 全栈方向）',
            '期望城市：北京/杭州/苏州',
            '期望薪资：8k-10k',
            '打印驿站 — 校园打印快递服务平台',
            'DoVideoAI — 长视频 Video Agent 平台',
            'FinRAG 财税助手 — RAG + Multi-Agent 智能问答系统',
            'Vibe Coding：深度使用 Codex/Copilot',
            'AI Agent 开发经验：Multi-Agent',
            'Docker Compose、K8s、Linux',
            'Recall@5 67.5%→85%',
        ],
        'must_not_have': [
            '财务 RAG Agent', 'AI 智能客服系统', '打印接单系统',
            '求职意向：Java 后端 / AI 应用',
            '期望城市：苏州/杭州/郑州/天津', '期望薪资：面议',
            '（Java 高并发主项目）', '（Java 全栈深度）', '（技术广度）',
            'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
            'Java / Python 双语言开发，熟悉面向对象与多线程',
        ],
    },

    # ---------- 前端/全栈开发 ----------
    'fe': {
        'suffix': '前端全栈定制版',
        'enlarge_project': True,   # 项目文本较长，扩高项目区+下移相关技能
        'personal': {
            '求职意向：Java 后端 / AI 应用': '求职意向：全栈开发工程师（React + TypeScript）',
            '期望城市：苏州/杭州/郑州/天津': '期望城市：北京/杭州/苏州',
            '期望薪资：面议': '期望薪资：8k-10k',
        },
        'tech_stack': [
            '前端：React 19 + TypeScript、shadcn/ui、Vue 3 + Element Plus、Vant 4、Tailwind CSS',
            '后端：Java 21/17(Spring Boot 3)、Python 3.13(FastAPI)、RESTful、SSE、WebSocket',
            '数据库/中间件：MySQL、Redis、SQLite、RabbitMQ、RocketMQ',
            '工程：Docker、Docker Compose、K8s、Linux、Git、JMeter 压测、单元测试',
            'AI：LangChain Agent、RAG 全链路、MCP 封装、Vibe Coding 开发流｜GitHub：github.com/zsy04',
        ],
        'skills': [
            'React 19 + TypeScript + shadcn/ui：SSE 流式对话 UI、状态管理、错误/加载/空态处理',
            '全栈工程：前端页面 + 后端接口 + 联调测试 + 问题修复全流程，Vue 3/Element Plus 多端经验',
            '工程责任感：接口设计、边界条件、异常兜底、性能优化、线上问题定位有完整实践',
            '后端支撑：Java Spring Boot + Python FastAPI 独立全栈交付能力',
            'Vibe Coding：深度使用 Codex/Copilot 等 AI 编程工具提升开发效率',
            '开源与分享：GitHub 开源项目 + 50+ 篇技术文档（PRD/架构/评测/复盘）',
        ],
        'projects': [
            # 打印驿站 5 段（Java 主推）
            '打印驿站 — 校园打印快递服务平台',
            'Java 17 + Spring Boot 3 + MySQL + Redis + RabbitMQ + Vue 3 + Element Plus + Redisson｜独立开发',
            'V1.0→V1.5 五次架构演进，覆盖从单体到高并发分布式的完整后端工程场景。',
            '｜MQ 异步削峰(RT 500ms→50ms) + 三级缓存 + 双算法限流 + 三层幂等',
            '｜Vue 3 + TypeScript + Element Plus 双端页面 + WebSocket STOMP 实时订单推送',
            '',
            # DoVideoAI 6 段（SSE 全栈）
            'DoVideoAI — 长视频 Video Agent 平台',
            'Java 21 + Spring Boot 3 + RocketMQ + Redis + MinIO + Qdrant + LangChain4j｜独立开发',
            '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
            '｜SSE 实时进度推送（解析→检索→分析→完成）+ 5MB 分片上传/断点续传',
            '｜AgentLoop 闭环 + RocketMQ 异步削峰 + Redisson 锁防重 + 双限流',
            '｜前后端联调与问题修复闭环 + Checkpoint 断点恢复',
            '',
            # FinRAG 5 段（React 全栈）
            'FinRAG 财税助手 — AI 智能问答系统',
            'React 19 + TS + shadcn/ui + FastAPI + LangChain + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
            '面向零财务基础大众的 AI 问答助手，SSE 流式对话 + 多会话管理 + BYOK 模型切换。',
            '｜React 19 + TS 组件化：SSE 流式渲染(7 事件)、会话历史回显、localStorage 持久化',
            '｜全栈闭环 + FastAPI + SQLite + Docker Compose 部署，RAG Recall@5 85%',
        ],
        'must_have': [
            '全栈开发工程师（React + TypeScript）',
            '期望城市：北京/杭州/苏州',
            '期望薪资：8k-10k',
            'FinRAG 财税助手 — AI 智能问答系统',
            '打印驿站 — 校园打印快递服务平台',
            'DoVideoAI — 长视频 Video Agent 平台',
            'React 19 + TS 组件化：SSE 流式渲染',
            'Vue 3 + TypeScript + Element Plus 双端页面',
            'Vibe Coding：深度使用 Codex/Copilot',
            'Docker Compose、K8s、Linux',
        ],
        'must_not_have': [
            '财务 RAG Agent', 'AI 智能客服系统', '打印接单系统',
            '求职意向：Java 后端 / AI 应用',
            '期望城市：苏州/杭州/郑州/天津', '期望薪资：面议',
            '（Java 高并发主项目）', '（Java 全栈深度）', '（技术广度）',
            'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
            'Java / Python 双语言开发，熟悉面向对象与多线程',
        ],
    },
}

# ============ 工具函数 ============
WPG = 'http://schemas.microsoft.com/office/word/2010/wordprocessingGroup'
WPS = 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape'
WP  = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A   = 'http://schemas.openxmlformats.org/drawingml/2006/main'

# 所有岗位共用的个人信息替换（电话/邮箱/薪资）
# 策略：邮箱放右列第 5 段（1 行），GitHub 合并到技术栈末尾，避免扩高右列
PERSONAL_COMMON = {
    '政治面貌：群众': '电话：13733872193',
    '期望薪资：面议': '期望薪资：8k-10k',
    'GitHub：github.com/zsy04': '邮箱：13733872193@163.com',
}

def get_anchor_posv(group):
    cur = group
    while cur is not None:
        if cur.tag == '{%s}anchor' % WP:
            posv = cur.find('{%s}positionV' % WP)
            off = posv.find('{%s}posOffset' % WP)
            return int(off.text)
        cur = cur.getparent()
    raise RuntimeError('未找到 anchor')

def enlarge_personal(root, add_emu=500000):
    """个人信息区扩高：右列内容 shape + 组 ext 加高，技术栈/项目经历/相关技能组整体下移，
    为新增的电话/邮箱行腾空间。"""
    groups = root.findall('.//{%s}wgp' % WPG)
    g0, g3, g4, g2 = groups[0], groups[3], groups[4], groups[2]
    # 右列 shape（含"专    业"文本）加高
    for shp in g0.findall('.//{%s}wsp' % WPS):
        tx = shp.find('.//{%s}txbxContent' % W)
        if tx is None:
            continue
        joined = ' '.join(para_text(p) for p in tx.findall('{%s}p' % W))
        if '专' in joined and '业' in joined:
            sxfrm = shp.find('.//{%s}xfrm' % A)
            sext = sxfrm.find('{%s}ext' % A)
            sext.set('cy', str(int(sext.get('cy')) + add_emu))
    # 组 ext 加高
    grpsppr = g0.find('{%s}grpSpPr' % WPG)
    xfrm = grpsppr.find('{%s}xfrm' % A)
    ext = xfrm.find('{%s}ext' % A)
    ext.set('cy', str(int(ext.get('cy')) + add_emu))
    # 下方三组整体下移
    for g in (g3, g4, g2):
        set_anchor_posv(g, get_anchor_posv(g) + add_emu)


def enlarge_project(root, add_emu=400000):
    """项目经历 shape 扩高 + 组4 ext 扩高 + 组2（相关技能）下移，
    容纳较长的项目技术栈/要点行。"""
    groups = root.findall('.//{%s}wgp' % WPG)
    g4, g2 = groups[4], groups[2]
    # 项目内容 shape（含"财务 RAG Agent"特征文本）加高
    for shp in g4.findall('.//{%s}wsp' % WPS):
        tx = shp.find('.//{%s}txbxContent' % W)
        if tx is None:
            continue
        joined = ' '.join(para_text(p) for p in tx.findall('{%s}p' % W))
        if 'RAG Agent' in joined or '项目经历' in joined:
            sxfrm = shp.find('.//{%s}xfrm' % A)
            sext = sxfrm.find('{%s}ext' % A)
            sext.set('cy', str(int(sext.get('cy')) + add_emu))
    # 组4 ext 加高
    grpsppr = g4.find('{%s}grpSpPr' % WPG)
    xfrm = grpsppr.find('{%s}xfrm' % A)
    ext = xfrm.find('{%s}ext' % A)
    ext.set('cy', str(int(ext.get('cy')) + add_emu))
    # 组2（相关技能）下移
    set_anchor_posv(g2, get_anchor_posv(g2) + add_emu)


def find_group_para(root, group_idx):
    """返回含第 group_idx 个 wpg:wgp 组的 w:p 段落元素。"""
    groups = root.findall('.//{%s}wgp' % WPG)
    cur = groups[group_idx]
    while cur is not None and etree.QName(cur).localname != 'p':
        cur = cur.getparent()
    return cur

def group_of(para):
    return para.find('.//{%s}wgp' % WPG)

def set_anchor_posv(group, new_y):
    """改组的 wp:anchor 的 positionV/posOffset（页面 Y，EMU）。"""
    cur = group
    anchor = None
    while cur is not None:
        if cur.tag == '{%s}anchor' % WP:
            anchor = cur
            break
        cur = cur.getparent()
    if anchor is None:
        raise RuntimeError('未找到 anchor')
    posv = anchor.find('{%s}positionV' % WP)
    off = posv.find('{%s}posOffset' % WP)
    off.text = str(int(new_y))

def set_group_text(group, title, lines):
    """按文本特征改 wpg 组内 shape 文本：标题 shape → title，内容 shape → lines（变长替换）。"""
    n_title = 0
    for shp in group.findall('.//{%s}wsp' % WPS):
        tx = shp.find('.//{%s}txbxContent' % W)
        if tx is None:
            continue
        paras = tx.findall('{%s}p' % W)
        texts = [para_text(p) for p in paras]
        joined = ' '.join(texts).strip()
        if joined in ('相关技能', '技术栈', '项目经历', '个人信息'):
            # 标题 shape：单段，直接改写
            if paras:
                set_para_text(paras[0], title)
                n_title += 1
        else:
            replace_block_varlen(tx, lines)
    return n_title


def replace_block_varlen(tx, new_lines):
    """变长替换：前 min 段改写，多余段删除（用于跨区块复制后的内容注入）。"""
    paras = tx.findall('{%s}p' % W)
    n = min(len(paras), len(new_lines))
    for i in range(n):
        set_para_text(paras[i], new_lines[i])
    for p in paras[n:]:
        tx.remove(p)

def dedup_docpr(para, id_base):
    """把段落内所有 wp:docPr id 改为不冲突的新 id。"""
    ids = []
    for dp in para.iter('{%s}docPr' % WP):
        old = dp.get('id')
        new = id_base + len(ids)
        dp.set('id', str(new))
        ids.append((old, new))
    return ids

def build_two_page(root, cfg):
    """两页版：第一页（个人信息/技术栈/项目经历/教育背景）+ 分页 + 第二页（实习经历/相关技能）。
    教育背景、实习经历均复制"相关技能"组（组2 结构：标题/内容/图标/分隔线）。"""
    body = root.find('{%s}body' % W)
    p_proj = find_group_para(root, 4)   # 项目经历组所在段落
    p_skill = find_group_para(root, 2)  # 相关技能组所在段落

    # 教育背景组（第一页底部 y=8.5M）
    p_edu = __import__('copy').deepcopy(p_skill)
    p_proj.addnext(p_edu)
    set_anchor_posv(group_of(p_edu), 8500000)
    set_group_text(group_of(p_edu), '教育背景', cfg['edu_lines'])
    dedup_docpr(p_edu, 100)

    # 分页符段落
    p_pb = etree.fromstring(
        ('<w:p xmlns:w="%s"><w:r><w:br w:type="page"/></w:r></w:p>' % W).encode())
    p_edu.addnext(p_pb)

    # 实习经历组（第二页 y=1.2M）
    p_intern = __import__('copy').deepcopy(p_skill)
    p_pb.addnext(p_intern)
    set_anchor_posv(group_of(p_intern), 1200000)
    set_group_text(group_of(p_intern), '实习经历', cfg['intern_lines'])
    dedup_docpr(p_intern, 200)

    # 原相关技能组移到第二页（y=5.2M）
    body.remove(p_skill)
    p_intern.addnext(p_skill)
    set_anchor_posv(group_of(p_skill), 5200000)


def para_text(p):
    return ''.join((t.text or '') for t in p.iter('{%s}t' % W))

def set_para_text(p, new_text):
    """整段重写为单段文本（保留段首 run 的 rPr 样式），其余 run 清空。"""
    runs = p.findall('{%s}r' % W)
    if not runs:
        return False
    first_run = runs[0]
    ts = first_run.findall('{%s}t' % W)
    if not ts:
        t = etree.SubElement(first_run, '{%s}t' % W)
        t.text = new_text
    else:
        ts[0].text = new_text
        for t in ts[1:]:
            t.text = ''
    for r in runs[1:]:
        for t in r.findall('{%s}t' % W):
            t.text = ''
    return True

def replace_block(tx, new_lines):
    """按位置把 txbxContent 内每段替换为 new_lines。段数必须相等。"""
    paras = tx.findall('{%s}p' % W)
    if len(paras) != len(new_lines):
        raise RuntimeError(
            f'段数不匹配: tx 有 {len(paras)} 段, new 有 {len(new_lines)} 段。\n'
            f'  现有: {[para_text(p) for p in paras]}\n'
            f'  新内容: {new_lines}'
        )
    for p, new in zip(paras, new_lines):
        set_para_text(p, new)

# ============ 主流程 ============
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CONFIGS:
        print(f'用法: python {os.path.basename(__file__)} <{"|".join(CONFIGS)}>')
        sys.exit(1)
    cfg = CONFIGS[sys.argv[1]]
    DST_DOCX = os.path.join(OUT_DIR, f'简历-周嵩原-{cfg["suffix"]}.docx')
    DST_PDF  = os.path.join(OUT_DIR, f'简历-周嵩原-{cfg["suffix"]}.pdf')

    if not os.path.exists(BACKUP):
        shutil.copy2(SRC, BACKUP)
        print(f'[备份] {BACKUP}')
    shutil.copy2(SRC, DST_DOCX)
    print(f'[复制] {SRC} -> {DST_DOCX}')

    with zipfile.ZipFile(DST_DOCX, 'r') as zin:
        items = {n: zin.read(n) for n in zin.namelist()}

    root = etree.fromstring(items['word/document.xml'])
    txbxs = [e for e in root.iter()
             if isinstance(e.tag, str) and e.tag.endswith('}txbxContent')]
    print(f'[解析] 共 {len(txbxs)} 个 txbxContent 节点')

    n_personal = n_tech = n_proj = n_skill = 0
    for tx in txbxs:
        paras = tx.findall('{%s}p' % W)
        full  = ' '.join(para_text(p) for p in paras)

        if '财务 RAG Agent' in full and 'AI 智能客服系统' in full and '打印接单系统' in full:
            replace_block(tx, cfg['projects'])
            n_proj += 1
        elif 'Java、Python' in full and '框架 Spring Boot、MyBatis、FastAPI' in full:
            replace_block(tx, cfg['tech_stack'])
            n_tech += 1
        elif 'Java / Python 双语言开发' in full and 'Tailwind CSS，SSE 实时通信' in full:
            replace_block(tx, cfg['skills'])
            n_skill += 1
        elif full.strip() == '相关技能' and 'skill_title' in cfg:
            # 相关技能区标题改名（如"实习与技能"）
            replace_block(tx, [cfg['skill_title']])
            n_skill += 1
        elif ('姓' in full and '政治面貌' in full) or ('求职意向' in full and '期望城市' in full):
            # 个人信息左右两列：先应用通用替换（电话/邮箱/薪资），再应用岗位配置替换
            for p in paras:
                orig = para_text(p)
                if orig in PERSONAL_COMMON:
                    set_para_text(p, PERSONAL_COMMON[orig])
                elif orig in cfg['personal']:
                    set_para_text(p, cfg['personal'][orig])
            n_personal += 1

    print(f'[替换] 个人信息={n_personal} 技术栈={n_tech} 项目={n_proj} 技能={n_skill}')

    # 项目经历区扩高（容纳较长技术栈/要点行），按配置开关启用
    if cfg.get('enlarge_project'):
        enlarge_project(root)
        print('[布局] 项目经历区已扩高，相关技能下移')

    # 两页版扩展布局（需在替换后、序列化前执行）
    if cfg.get('two_page'):
        build_two_page(root, cfg)
        print('[两页] 已扩展：第一页=教育背景，第二页=实习经历+相关技能')

    new_xml = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    items['word/document.xml'] = new_xml
    with zipfile.ZipFile(DST_DOCX, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n, data in items.items():
            zout.writestr(n, data)
    print(f'[打包] {DST_DOCX}')

    # 验证
    with zipfile.ZipFile(DST_DOCX, 'r') as zin:
        check_root = etree.fromstring(zin.read('word/document.xml'))
    all_text = ' '.join(t.text or '' for t in check_root.iter('{%s}t' % W))

    print('\n[验证]')
    ok_cnt = 0
    must_have = list(cfg['must_have']) + ['电话：13733872193', '邮箱：13733872193@163.com', 'GitHub：github.com/zsy04']
    must_not_have = list(cfg['must_not_have']) + ['政治面貌：群众']
    for s in must_have:
        ok = s in all_text
        ok_cnt += ok
        print(f'  {"✓" if ok else "✗"} 必含: {s}')
    for s in must_not_have:
        ok = s not in all_text
        ok_cnt += ok
        print(f'  {"✓" if ok else "✗"} 必不含: {s}')
    total = len(must_have) + len(must_not_have)
    print(f'[验证结果] {ok_cnt}/{total} 通过')
    if ok_cnt < total:
        print('!! 有未通过项，继续转 PDF 但请注意检查')

    print('\n[转 PDF] 启动 Word...')
    import docx2pdf
    docx2pdf.convert(DST_DOCX, DST_PDF)
    size = os.path.getsize(DST_PDF)
    print(f'[完成] {DST_PDF}  ({size/1024:.1f} KB)')

    if cfg.get('two_page'):
        import pymupdf
        doc = pymupdf.open(DST_PDF)
        print(f'[页数检查] 共 {len(doc)} 页' + (' ✓' if len(doc) == 2 else ' !! 期望 2 页，请检查'))

if __name__ == '__main__':
    main()
