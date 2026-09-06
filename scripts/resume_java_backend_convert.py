"""基于 Aspose 图形化简历模板 docx 改内容并导出 PDF。
- 解析 word/document.xml，遍历所有 w:txbxContent 节点
- 按"内容指纹"识别四大块：个人信息 / 技术栈 / 项目经历 / 相关技能
- 每段都是单 w:t 直接替换文本，保留段样式
- 写回 docx → 用 docx2pdf (Word COM) 转 PDF
"""
import os
import shutil
import zipfile
import sys
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# ========= 路径 =========
SRC = r'F:\lest\outputs\简历-周嵩原.docx'
DST_DOCX = r'F:\lest\outputs\简历-周嵩原-Java后端-电商SaaS定制版.docx'
DST_PDF  = r'F:\lest\outputs\简历-周嵩原-Java后端-电商SaaS定制版.pdf'
BACKUP   = r'F:\lest\outputs\简历-周嵩原-通用版-原版备份.docx'

# ========= 新内容 =========
# 项目经历：18 段（5 项目1 + 1 空 + 6 项目2 + 1 空 + 5 项目3），标题不含括号说明
NEW_PROJECT_BLOCK = [
    # —— 打印驿站 5 段 ——
    '打印驿站 — 校园打印快递服务平台',
    'Java 17 + Spring Boot 3 + MyBatis-Plus + MySQL + Redis + RabbitMQ + Redisson + Vue 3｜独立开发',
    'V1.0→V1.5 五次架构演进，覆盖从单体到高并发分布式的完整后端工程场景。',
    '｜MQ 削峰：下单拆"受理+建单"两阶段，RT 从 500ms+ 降至 50ms 以下',
    '｜三级缓存 + 双算法限流 + 三层幂等 + 死信延迟取消兜底',
    '',  # 空行段（保留间距）
    # —— DoVideoAI 6 段 ——
    'DoVideoAI — 长视频内容理解平台',
    'Java 21 + Spring Boot 3.5 + MyBatis-Plus + RocketMQ + Redis + MySQL + MinIO｜独立开发',
    '将长视频（课程/会议/录屏）转化为可检索、可追溯、可追问的结构化知识。',
    '｜分布式：RocketMQ 异步削峰，Redisson 锁防重 + Redis+MySQL Checkpoint 断点恢复',
    '｜高可用：双限流（用户级+全局令牌桶）+ Qdrant 不可用降级纯关键词',
    '｜上传：5MB 分片 + 断点续传 + MinIO 存储 + SSE 实时进度推送',
    '',  # 空行段
    # —— FinRAG 5 段 ——
    'FinRAG 财税助手 — RAG Agent 开源项目',
    'Python + FastAPI + LangChain + BGE-M3 + Qdrant + DeepSeek｜独立开发｜GitHub 开源',
    '面向零财务基础大众的 AI 问答助手，覆盖个税计算、社保查询、政策问答。',
    '｜RAG：四层分层检索，Recall@5 67.5%→85%，8 轮迭代驱动',
    '｜评测驱动：60+26+长对话+对拍四层评测，工具路由准确率 100%',
]

# 技术栈：5 段
NEW_TECH_STACK = [
    '后端：Java 21/17、Python；Spring Boot 3、MyBatis-Plus、Spring Security',
    '数据库/中间件：MySQL、Redis、RabbitMQ、RocketMQ、Redisson、Caffeine、MinIO',
    '分布式：MQ 异步削峰、三级缓存、限流（滑动窗口/令牌桶）、幂等、分布式锁',
    '部署：Docker、Docker Compose、Linux、Git、JMeter 压测',
    'AI/前端：Vue 3、React（了解）、LangChain Agent、RAG 全链路、SSE',
]

# 相关技能：6 段
NEW_SKILLS = [
    'Java 基础扎实：OOP / 集合 / 异常 / 多线程；Spring Boot 全流程开发',
    '分布式工程：MQ 削峰、三级缓存、限流、分布式锁、幂等、最终一致性实战',
    'Spring Boot + MyBatis-Plus + MySQL + Redis + RabbitMQ 全链路实战',
    'LangChain Agent 编排 + RAG 全链路（BGE-M3 + Qdrant + BGE-Reranker）',
    'GitHub 开源项目 + 50+ 篇全生命周期工程文档（PRD/架构/评测/复盘）',
    'Docker 容器化部署 + Linux + Git + JMeter 压测 + 评测驱动迭代',
]

# 个人信息：按原段做精确替换
PERSONAL_REPLACE = {
    '求职意向：Java 后端 / AI 应用':
        '求职意向：Java 后端开发（电商 SaaS / 高并发分布式）',
    '期望城市：苏州/杭州/郑州/天津':
        '期望城市：北京/杭州/苏州',
    '期望薪资：面议':
        '期望薪资：8k-10k',
}

# ========= 工具函数 =========
def para_text(p):
    return ''.join((t.text or '') for t in p.iter('{%s}t' % W))

def set_para_text(p, new_text):
    """整段重写为单段文本（保留段首 run 的 rPr 样式），其余 run 清空。"""
    runs = p.findall('{%s}r' % W)
    if not runs:
        return False
    # 在第一个 run 内找/创建 w:t
    first_run = runs[0]
    ts = first_run.findall('{%s}t' % W)
    if not ts:
        t = etree.SubElement(first_run, '{%s}t' % W)
        t.text = new_text
    else:
        ts[0].text = new_text
        for t in ts[1:]:
            t.text = ''
    # 后续 run 全部清空文本（保留 rPr 以维持原样）
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


def delete_project_desc(tx):
    """项目经历区：只保留标题段（含 '—'）与空段（间距），删除其余描述段；
    保留的标题段按顺序替换为新标题。"""
    paras = tx.findall('{%s}p' % W)
    keep = [p for p in paras
            if para_text(p) == '' or '—' in para_text(p)]
    # 按出现顺序替换非空标题段为新标题
    title_idx = 0
    for p in keep:
        if para_text(p) != '':
            set_para_text(p, NEW_PROJECT_TITLES[title_idx])
            title_idx += 1
    for p in paras:
        if p not in keep:
            tx.remove(p)
    titles = [para_text(p) for p in keep if para_text(p)]
    print(f'  项目经历: {len(paras)} 段 -> {len(keep)} 段 | 标题: {titles}')

# ========= 主流程 =========
def main():
    # 1. 备份原 docx（一次性）
    if not os.path.exists(BACKUP):
        shutil.copy2(SRC, BACKUP)
        print(f'[备份] {BACKUP}')
    # 2. 复制为目标 docx
    shutil.copy2(SRC, DST_DOCX)
    print(f'[复制] {SRC} -> {DST_DOCX}')

    # 3. 解压 → 解析 → 修改 document.xml
    with zipfile.ZipFile(DST_DOCX, 'r') as zin:
        items = {n: zin.read(n) for n in zin.namelist()}

    doc_xml = items['word/document.xml']
    root = etree.fromstring(doc_xml)

    txbxs = [e for e in root.iter()
             if isinstance(e.tag, str) and e.tag.endswith('}txbxContent')]
    print(f'[解析] 共 {len(txbxs)} 个 txbxContent 节点')

    # 按"内容指纹"路由到对应替换
    n_personal = n_tech = n_proj = n_skill = 0
    for tx in txbxs:
        paras = tx.findall('{%s}p' % W)
        full  = ' '.join(para_text(p) for p in paras)

        if '财务 RAG Agent' in full and 'AI 智能客服系统' in full and '打印接单系统' in full:
            replace_block(tx, NEW_PROJECT_BLOCK)
            n_proj += 1
        elif 'Java、Python' in full and '框架 Spring Boot、MyBatis、FastAPI' in full:
            replace_block(tx, NEW_TECH_STACK)
            n_tech += 1
        elif 'Java / Python 双语言开发' in full and 'Tailwind CSS，SSE 实时通信' in full:
            replace_block(tx, NEW_SKILLS)
            n_skill += 1
        elif '求职意向' in full and '期望城市' in full:
            # 个人信息：按段做精确替换
            for p in paras:
                orig = para_text(p)
                if orig in PERSONAL_REPLACE:
                    set_para_text(p, PERSONAL_REPLACE[orig])
            n_personal += 1
        # 其他（标题段"个人信息"/"技术栈"/"项目经历"/"相关技能"）不动

    print(f'[替换] 个人信息={n_personal} 技术栈={n_tech} 项目={n_proj} 技能={n_skill}')

    # 4. 重打包 docx
    new_xml = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    items['word/document.xml'] = new_xml
    with zipfile.ZipFile(DST_DOCX, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n, data in items.items():
            zout.writestr(n, data)
    print(f'[打包] {DST_DOCX}')

    # 5. 验证：抽 w:t 拼接后看关键文本
    with zipfile.ZipFile(DST_DOCX, 'r') as zin:
        check_root = etree.fromstring(zin.read('word/document.xml'))
    all_text = ' '.join(t.text or '' for t in check_root.iter('{%s}t' % W))

    must_have = [
        'Java 后端开发（电商 SaaS',          # 求职意向
        '期望城市：北京/杭州/苏州',          # 期望城市
        '期望薪资：8k-10k',                  # 期望薪资
        '打印驿站 — 校园打印快递服务平台',   # 项目 1 标题（无括号说明）
        'DoVideoAI — 长视频内容理解平台',    # 项目 2 标题（无括号说明）
        'FinRAG 财税助手 — RAG Agent 开源项目',  # 项目 3 标题（无括号说明）
        '｜MQ 削峰：下单拆"受理+建单"两阶段，RT 从 500ms+ 降至 50ms 以下',  # 项目描述已恢复
        'Recall@5 67.5%→85%',              # FinRAG 描述
        'Java 21/17、Python；Spring Boot 3',  # 技术栈
        'Java 基础扎实',                     # 相关技能
        'GitHub 开源项目 + 50+ 篇',
    ]
    must_not_have = [
        '财务 RAG Agent',
        'AI 智能客服系统',
        '打印接单系统',
        '求职意向：Java 后端 / AI 应用',
        '期望城市：苏州/杭州/郑州/天津',
        '期望薪资：面议',
        '（Java 高并发主项目）',   # 标题括号说明已去
        '（Java 全栈深度）',
        '（技术广度）',
        'Java、Python；框架 Spring Boot、MyBatis、FastAPI',
        'Java / Python 双语言开发，熟悉面向对象与多线程',
    ]
    print('\n[验证]')
    for s in must_have:
        ok = s in all_text
        print(f'  {"✓" if ok else "✗"} 必含: {s}')
    for s in must_not_have:
        ok = s in all_text
        print(f'  {"✓" if not ok else "✗"} 必不含: {s}')

    # 6. 转 PDF
    print('\n[转 PDF] 启动 Word...')
    import docx2pdf
    docx2pdf.convert(DST_DOCX, DST_PDF)
    size = os.path.getsize(DST_PDF)
    print(f'[完成] {DST_PDF}  ({size/1024:.1f} KB)')

if __name__ == '__main__':
    main()
