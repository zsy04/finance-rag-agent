import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import type { ActiveView, UserContext } from '@/lib/types';
import { loadActiveProviderId, saveActiveProviderId } from '@/lib/provider';

interface AppState {
  activeView: ActiveView;
  setActiveView: (v: ActiveView) => void;
  userContext: UserContext;
  updateUserContext: (p: Partial<UserContext>) => void;
  // 模型切换器（2026-08-06）：当前生效的自定义 provider id（null = 默认 DeepSeek）
  activeProviderId: string | null;
  setActiveProviderId: (id: string | null) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ActiveView>('chat');
  const [userContext, setUserContext] = useState<UserContext>({
    city: '郑州',
    deductions: {},
  });
  // 初始化从 localStorage 读（刷新后保持用户选择）
  const [activeProviderId, setActiveProviderIdState] = useState<string | null>(
    () => loadActiveProviderId(),
  );

  const updateUserContext = useCallback((p: Partial<UserContext>) => {
    setUserContext((prev) => ({ ...prev, ...p }));
  }, []);

  const setActiveProviderId = useCallback((id: string | null) => {
    saveActiveProviderId(id);
    setActiveProviderIdState(id);
  }, []);

  return (
    <AppContext.Provider
      value={{
        activeView,
        setActiveView,
        userContext,
        updateUserContext,
        activeProviderId,
        setActiveProviderId,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be inside AppProvider');
  return ctx;
}
