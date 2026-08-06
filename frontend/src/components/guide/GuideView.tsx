/** 申报指引 — 独立静态指引页（2026-08-06 设计稿落地：复用《个税操作指南.md》要点） */
const GUIDE_STEPS = [
  {
    title: '确认申报身份',
    desc: '判断你是雇员（单位代扣代缴）还是个体工商户/自由职业者（自行申报），选择对应的申报类型。',
  },
  {
    title: '汇总收入与扣除',
    desc: '整理全年综合所得（工资薪金、劳务报酬、稿酬、特许权使用费），汇总专项扣除与专项附加扣除（子女教育、住房贷款、赡养老人等）。',
  },
  {
    title: '计算应纳税额',
    desc: '使用「税率计算」功能输入收入与扣除项，自动计算应纳税所得额与税额（也可咨询智能问答）。',
  },
  {
    title: '申报与缴款',
    desc: '在征期内（综合所得汇算每年 3-6 月）通过个人所得税 APP 或办税服务厅完成申报，选择补税或退税。',
  },
];

const FAQ_ITEMS = [
  { q: '什么时候需要年度汇算？', a: '取得综合所得且需要退税，或年收入超过 12 万元且补税超过 400 元的纳税人，应在次年 3 月 1 日至 6 月 30 日办理汇算。' },
  { q: '专项附加扣除有哪些项目？', a: '子女教育、继续教育、大病医疗、住房贷款利息、住房租金、赡养老人、3 岁以下婴幼儿照护共 7 项。' },
  { q: '申报材料要准备什么？', a: '身份证件、收入凭证、扣除凭证（如房租合同、贷款合同、继续教育证书等），通过「材料生成」可快速生成申报表。' },
];

export function GuideView() {
  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto px-8 py-6">
      {/* 页头 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">申报指引</h2>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          面向零基础用户的申报流程速览，结合《个税操作指南》整理
        </p>
      </div>

      {/* 流程步骤 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {GUIDE_STEPS.map((s, i) => (
          <div
            key={s.title}
            className="flex gap-4 rounded-xl border border-[var(--color-border)] bg-white p-5"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-primary)] text-sm font-semibold text-white">
              {i + 1}
            </span>
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-primary)]">{s.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-secondary)]">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* 常见问题 */}
      <div className="rounded-xl border border-[var(--color-border)] bg-white p-5">
        <h3 className="mb-3 text-sm font-medium text-[var(--color-text-primary)]">常见问题</h3>
        <div className="space-y-4">
          {FAQ_ITEMS.map((f) => (
            <div key={f.q}>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">{f.q}</p>
              <p className="mt-0.5 text-sm leading-relaxed text-[var(--color-text-secondary)]">{f.a}</p>
            </div>
          ))}
        </div>
      </div>

      <p className="text-xs text-[var(--color-text-tertiary)]">
        提示：具体政策以税务机关最新规定为准，本页内容由 AI 根据《个税操作指南》整理，仅供参考。
      </p>
    </div>
  );
}
