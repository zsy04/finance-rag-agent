import { AppProvider, useApp } from '@/context/AppContext';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ChatView } from '@/components/chat/ChatView';
import { TaxCalculator } from '@/components/calculator/TaxCalculator';
import { FilingForm } from '@/components/form/FilingForm';
import { GuideView } from '@/components/guide/GuideView';
import { DocumentsView } from '@/components/library/DocumentsView';
import { BenchmarkView } from '@/components/library/BenchmarkView';
import { useChat } from '@/hooks/useChat';

function AppContent() {
  const { activeView } = useApp();
  const {
    messages,
    isLoading,
    isHydrating,
    threadId,
    threads,
    sendMessage,
    stopGeneration,
    selectThread,
    createThread,
    deleteThread,
  } = useChat();

  return (
    <div className="app-container flex h-screen bg-[var(--color-bg-page)]">
      <Sidebar
        threads={threads}
        currentThreadId={threadId}
        disabled={isLoading}
        onSelectThread={selectThread}
        onCreateThread={createThread}
        onDeleteThread={deleteThread}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          {activeView === 'chat' &&
            (isHydrating ? (
              // 历史回显加载中（本地 SQLite 毫秒级，防 WelcomeScreen 闪烁）
              <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-tertiary)]">
                正在加载历史记录……
              </div>
            ) : (
              <ChatView
                messages={messages}
                isLoading={isLoading}
                onSend={sendMessage}
                onStop={stopGeneration}
              />
            ))}
          {activeView === 'calculator' && <TaxCalculator />}
          {activeView === 'form' && <FilingForm />}
          {activeView === 'guide' && <GuideView />}
          {activeView === 'documents' && <DocumentsView />}
          {activeView === 'benchmark' && <BenchmarkView />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
