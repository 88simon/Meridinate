'use client';

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef
} from 'react';
import { toast } from 'sonner';
import { API_BASE_URL } from '@/lib/api';

export interface ApiSettings {
  transactionLimit: number;
  minUsdFilter: number;
  walletCount: number;
  apiRateDelay: number;
  maxCreditsPerAnalysis: number;
  maxRetries: number;
}

const defaultApiSettings: ApiSettings = {
  transactionLimit: 500,
  minUsdFilter: 50,
  walletCount: 10,
  apiRateDelay: 100,
  maxCreditsPerAnalysis: 1000,
  maxRetries: 3
};

interface ApiSettingsContextType {
  apiSettings: ApiSettings;
  setApiSettings: (settings: ApiSettings) => void;
  defaultApiSettings: ApiSettings;
  settingsLoaded: boolean;
}

const ApiSettingsContext = createContext<ApiSettingsContextType | undefined>(
  undefined
);

export function ApiSettingsProvider({
  children
}: {
  children: React.ReactNode;
}) {
  const [apiSettings, setApiSettings] =
    useState<ApiSettings>(defaultApiSettings);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const isInitialLoadRef = useRef(true);

  // Load API settings from backend on mount (silently, no UI impact)
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/settings`, { cache: 'no-store' })
      .then((res) => res.json())
      .then((settings) => {
        // Batch state updates to avoid extra render
        React.startTransition(() => {
          setApiSettings(settings);
          setSettingsLoaded(true);
        });
      })
      .catch(() => {
        setSettingsLoaded(true);
      });
  }, []);

  // Update backend whenever settings change (but not on initial load)
  useEffect(() => {
    if (!settingsLoaded) return; // Skip if not loaded yet

    // Skip the first run (when settings are initially loaded from backend)
    if (isInitialLoadRef.current) {
      isInitialLoadRef.current = false;
      return;
    }

    // Debounce to avoid too many requests (1 second wait after user stops adjusting)
    const timer = setTimeout(() => {
      fetch(`${API_BASE_URL}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(apiSettings)
      })
        .then((res) => res.json())
        .then(() => {
          // Show toast notification when settings are saved
          toast.success('Settings saved', {
            description: 'Will be used for next analysis',
            duration: 2000
          });
        })
        .catch(() => {
          toast.error('Failed to save settings');
        });
    }, 1000);

    return () => clearTimeout(timer);
  }, [apiSettings, settingsLoaded]);

  return (
    <ApiSettingsContext.Provider
      value={{
        apiSettings,
        setApiSettings,
        defaultApiSettings,
        settingsLoaded
      }}
    >
      {children}
    </ApiSettingsContext.Provider>
  );
}

export function useApiSettings() {
  const context = useContext(ApiSettingsContext);
  if (context === undefined) {
    throw new Error(
      'useApiSettings must be used within an ApiSettingsProvider'
    );
  }
  return context;
}
