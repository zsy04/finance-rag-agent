import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

/**
 * 全局错误边界（2026-08-13）：渲染异常时降级为可恢复 UI，避免整个应用白屏。
 * React 19 中未捕获的渲染错误会卸载根节点，必须在此兜底。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(err: unknown): State {
    return {
      hasError: true,
      message: err instanceof Error ? err.message : '未知错误',
    };
  }

  handleReload = () => {
    this.setState({ hasError: false, message: '' });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[var(--color-bg-page)] p-8 text-center">
          <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">
            页面出现异常
          </h1>
          <p className="max-w-md text-sm text-[var(--color-text-secondary)]">
            {this.state.message || '渲染过程中发生未预期的错误'}
          </p>
          <button
            type="button"
            onClick={this.handleReload}
            className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm text-white transition-colors hover:opacity-90"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
