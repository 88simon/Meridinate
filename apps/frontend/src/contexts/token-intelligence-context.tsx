'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface TokenIntelligenceContextType {
  tipToken: any | null;
  openTIP: (token: any) => void;
  closeTIP: () => void;
}

const TokenIntelligenceContext = createContext<TokenIntelligenceContextType>({
  tipToken: null,
  openTIP: () => {},
  closeTIP: () => {},
});

export function useTokenIntelligence() {
  return useContext(TokenIntelligenceContext);
}

export function TokenIntelligenceProvider({ children }: { children: ReactNode }) {
  const [tipToken, setTipToken] = useState<any | null>(null);

  const openTIP = useCallback((token: any) => {
    setTipToken((prev: any) => prev?.id === token?.id ? null : token);
  }, []);

  const closeTIP = useCallback(() => {
    setTipToken(null);
  }, []);

  return (
    <TokenIntelligenceContext.Provider value={{ tipToken, openTIP, closeTIP }}>
      {children}
    </TokenIntelligenceContext.Provider>
  );
}
