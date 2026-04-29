'use client';

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { API_BASE_URL } from '@/lib/api';

interface StarredContextType {
  starredWallets: Set<string>;
  starredTokens: Set<string>;
  isStarred: (type: 'wallet' | 'token', address: string) => boolean;
  toggleStar: (type: 'wallet' | 'token', address: string) => void;
  refreshStarred: () => void;
}

const StarredContext = createContext<StarredContextType>({
  starredWallets: new Set(),
  starredTokens: new Set(),
  isStarred: () => false,
  toggleStar: () => {},
  refreshStarred: () => {},
});

export function useStarred() {
  return useContext(StarredContext);
}

export function StarredProvider({ children }: { children: ReactNode }) {
  const [starredWallets, setStarredWallets] = useState<Set<string>>(new Set());
  const [starredTokens, setStarredTokens] = useState<Set<string>>(new Set());

  const refreshStarred = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/starred/addresses`);
      if (res.ok) {
        const data = await res.json();
        setStarredWallets(new Set(data.wallets || []));
        setStarredTokens(new Set(data.tokens || []));
      }
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refreshStarred();
  }, [refreshStarred]);

  const isStarred = useCallback((type: 'wallet' | 'token', address: string) => {
    return type === 'wallet' ? starredWallets.has(address) : starredTokens.has(address);
  }, [starredWallets, starredTokens]);

  const toggleStar = useCallback(async (type: 'wallet' | 'token', address: string) => {
    const currently = type === 'wallet' ? starredWallets.has(address) : starredTokens.has(address);

    // Optimistic update
    if (type === 'wallet') {
      setStarredWallets(prev => {
        const next = new Set(prev);
        if (currently) next.delete(address); else next.add(address);
        return next;
      });
    } else {
      setStarredTokens(prev => {
        const next = new Set(prev);
        if (currently) next.delete(address); else next.add(address);
        return next;
      });
    }

    try {
      if (currently) {
        await fetch(`${API_BASE_URL}/api/starred?item_type=${type}&item_address=${address}`, { method: 'DELETE' });
      } else {
        await fetch(`${API_BASE_URL}/api/starred`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_type: type, item_address: address }),
        });
      }
    } catch {
      // Revert on error
      if (type === 'wallet') {
        setStarredWallets(prev => {
          const next = new Set(prev);
          if (currently) next.add(address); else next.delete(address);
          return next;
        });
      } else {
        setStarredTokens(prev => {
          const next = new Set(prev);
          if (currently) next.add(address); else next.delete(address);
          return next;
        });
      }
    }
  }, [starredWallets, starredTokens]);

  return (
    <StarredContext.Provider value={{ starredWallets, starredTokens, isStarred, toggleStar, refreshStarred }}>
      {children}
    </StarredContext.Provider>
  );
}
