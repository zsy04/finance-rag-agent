import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { ActiveView, UserContext } from '@/lib/types';

interface AppState {
  activeView: ActiveView;
  setActiveView: (v: ActiveView) => void;
  userContext: UserContext;
  updateUserContext: (p: Partial<UserContext>) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ActiveView>('chat');
  const [userContext, setUserContext] = useState<UserContext>({
    city: '郑州',
    deductions: {},
  });

  const updateUserContext = useCallback((p: Partial<UserContext>) => {
    setUserContext((prev) => ({ ...prev, ...p }));
  }, []);

  return (
    <AppContext.Provider value={{ activeView, setActiveView, userContext, updateUserContext }}>
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
