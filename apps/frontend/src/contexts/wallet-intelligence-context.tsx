'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface WalletIntelligenceContextType {
  /** Currently open wallet address, or null if closed */
  wirAddress: string | null;
  /** Open the Wallet Intelligence Report for an address */
  openWIR: (address: string) => void;
  /** Close the panel */
  closeWIR: () => void;
}

const WalletIntelligenceContext = createContext<WalletIntelligenceContextType>({
  wirAddress: null,
  openWIR: () => {},
  closeWIR: () => {},
});

export function useWalletIntelligence() {
  return useContext(WalletIntelligenceContext);
}

export function WalletIntelligenceProvider({ children }: { children: ReactNode }) {
  const [wirAddress, setWirAddress] = useState<string | null>(null);

  const openWIR = useCallback((address: string) => {
    setWirAddress((prev) => prev === address ? null : address);
  }, []);

  const closeWIR = useCallback(() => {
    setWirAddress(null);
  }, []);

  return (
    <WalletIntelligenceContext.Provider value={{ wirAddress, openWIR, closeWIR }}>
      {children}
    </WalletIntelligenceContext.Provider>
  );
}
