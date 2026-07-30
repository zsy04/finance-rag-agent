interface WelcomeScreenProps {
  onSuggestionClick: (text: string) => void;
}

const SUGGESTIONS = [
  '工资 8000 在郑州交多少税？',
  '租房能扣多少税？',
  '帮我生成个税申报表',
];

export function WelcomeScreen({ onSuggestionClick }: WelcomeScreenProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 px-8">
      {/* Logo */}
      <img
        src="/icons/logo.svg"
        alt="财税助手"
        className="h-16 w-16"
      />

      {/* 标题 */}
      <div className="text-center">
        <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
          欢迎使用财税助手
        </h1>
        <p className="mt-2 max-w-md text-sm text-[var(--color-text-secondary)]">
          我是你的 AI 财税顾问，可以帮你：计算个税和社保 · 解答财税问题 · 生成申报材料
        </p>
      </div>

      {/* 示例问题 */}
      <div className="flex flex-col gap-2 w-full max-w-md">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => onSuggestionClick(text)}
            className="rounded-[var(--radius-lg)] border border-[#E2E8F0] bg-[var(--color-bg-page)] p-3 text-left text-sm transition-all duration-[var(--transition-fast)] hover:border-[#93C5FD] hover:bg-[var(--color-primary-light)]"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
