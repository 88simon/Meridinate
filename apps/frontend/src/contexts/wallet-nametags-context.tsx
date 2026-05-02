'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';

type NametagMap = Record<string, string>;

interface WalletNametagsContextValue {
  nametags: NametagMap;
  isLoading: boolean;
  getNametag: (address: string | null | undefined) => string | null;
  setNametag: (address: string, nametag: string) => Promise<boolean>;
  clearNametag: (address: string) => Promise<boolean>;
  refresh: () => Promise<void>;
}

const WalletNametagsContext = createContext<WalletNametagsContextValue | undefined>(undefined);

export function WalletNametagsProvider({ children }: { children: React.ReactNode }) {
  const [nametags, setNametags] = useState<NametagMap>({});
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/wallets/nametags`);
      if (res.ok) {
        const data = await res.json();
        setNametags(data.nametags || {});
      }
    } catch {
      // network blip — keep last good map rather than wiping it
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Cross-component sync: any setter dispatches this so other panels rerender immediately.
  useEffect(() => {
    const handler = () => { refresh(); };
    window.addEventListener('walletNametagsChanged', handler);
    return () => window.removeEventListener('walletNametagsChanged', handler);
  }, [refresh]);

  const getNametag = useCallback(
    (address: string | null | undefined) => (address ? nametags[address] || null : null),
    [nametags]
  );

  const setNametag = useCallback(async (address: string, nametag: string) => {
    const trimmed = nametag.trim();
    if (!trimmed) return false;
    try {
      const res = await fetch(`${API_BASE_URL}/wallets/${address}/nametag`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nametag: trimmed }),
      });
      if (!res.ok) return false;
      // Optimistic update so the calling panel rerenders before the bulk refresh completes
      setNametags((prev) => ({ ...prev, [address]: trimmed }));
      window.dispatchEvent(new CustomEvent('walletNametagsChanged', { detail: { address } }));
      return true;
    } catch {
      return false;
    }
  }, []);

  const clearNametag = useCallback(async (address: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/wallets/${address}/nametag`, { method: 'DELETE' });
      if (!res.ok) return false;
      setNametags((prev) => {
        const next = { ...prev };
        delete next[address];
        return next;
      });
      window.dispatchEvent(new CustomEvent('walletNametagsChanged', { detail: { address } }));
      return true;
    } catch {
      return false;
    }
  }, []);

  return (
    <WalletNametagsContext.Provider value={{ nametags, isLoading, getNametag, setNametag, clearNametag, refresh }}>
      {children}
    </WalletNametagsContext.Provider>
  );
}

export function useWalletNametags(): WalletNametagsContextValue {
  const ctx = useContext(WalletNametagsContext);
  if (!ctx) throw new Error('useWalletNametags must be used within a WalletNametagsProvider');
  return ctx;
}

export function useWalletNametag(address: string | null | undefined): string | null {
  const { getNametag } = useWalletNametags();
  return getNametag(address);
}
