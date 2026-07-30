import { useState, useCallback } from 'react';
import { AppProvider, useApp } from '@/context/AppContext';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ChatView } from '@/components/chat/ChatView';
import { TaxCalculator } from '@/components/calculator/TaxCalculator';
import { FilingForm } from '@/components/form/FilingForm';
import { useChat } from '@/hooks/useChat';

function AppContent() {
  const { activeView } = useApp();
  const { messages, isLoading, sendMessage } = useChat();
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);

  const handleSend = useCallback(
    (msg: string) => {
      sendMessage(msg);
      setPendingMessage(null);
    },
    [sendMessage],
  );

  return (
    <div className="app-container flex h-screen bg-[var(--color-bg-page)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          {activeView === 'chat' && (
            <ChatView
              messages={messages}
              isLoading={isLoading}
              onSend={handleSend}
              lastUserMessage={pendingMessage}
            />
          )}
          {activeView === 'calculator' && <TaxCalculator />}
          {activeView === 'form' && <FilingForm />}
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
