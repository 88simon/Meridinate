'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import AppSidebar from '@/components/layout/app-sidebar';
import Header from '@/components/layout/header';
import { CodexPanel } from '@/components/codex-panel';
import { TagReferencePanel } from '@/components/tag-reference-panel';
import { PanelStack } from '@/components/layout/panel-stack';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { CodexContext } from '@/contexts/codex-context';
import { ApiSettingsProvider } from '@/contexts/ApiSettingsContext';
import { WalletIntelligenceProvider, useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { TokenIntelligenceProvider, useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { StarredProvider } from '@/contexts/starred-context';
import { WalletNametagsProvider } from '@/contexts/wallet-nametags-context';
import { TabVisibilityWatcher } from '@/components/tab-visibility-watcher';

// WIR (1k LOC) and TIR (700+ LOC) only mount when the user opens an address/token.
// Lazy-load them so the initial dashboard JS bundle is smaller — measurable win
// on first paint and on lower-end devices. ssr: false because both panels are
// purely client-side state machines with browser-only APIs.
const WalletIntelligencePanel = dynamic(
  () => import('@/components/wallet-intelligence-panel').then((m) => ({ default: m.WalletIntelligencePanel })),
  { ssr: false }
);
const TokenIntelligencePanel = dynamic(
  () => import('@/components/token-intelligence-panel').then((m) => ({ default: m.TokenIntelligencePanel })),
  { ssr: false }
);

interface DashboardWrapperProps {
  children: React.ReactNode;
  defaultOpen: boolean;
}

function DashboardContent({ children, defaultOpen }: DashboardWrapperProps) {
  const [showCodex, setShowCodex] = useState(false);
  const [showTagRef, setShowTagRef] = useState(false);

  const { wirAddress, closeWIR } = useWalletIntelligence();
  const { tipToken, closeTIP } = useTokenIntelligence();

  const handleCodexToggle = () => {
    setShowCodex((prev) => !prev);
  };

  const handleTagRefToggle = () => {
    setShowTagRef((prev) => !prev);
  };

  const closeAll = () => {
    closeWIR();
    closeTIP();
    setShowCodex(false);
  };

  return (
    <CodexContext.Provider value={{ isCodexOpen: showCodex }}>
      <div className='flex h-screen overflow-hidden'>
        <SidebarProvider defaultOpen={defaultOpen}>
          <AppSidebar onCodexToggle={handleCodexToggle} onTagRefToggle={handleTagRefToggle} showTagRef={showTagRef} />
          <div className='flex flex-1 overflow-hidden'>
            <SidebarInset className='flex-1 overflow-auto'>
              <Header />
              {children}
            </SidebarInset>
          </div>
        </SidebarProvider>

        <PanelStack
          panels={[
            {
              id: 'codex',
              width: 650,
              open: showCodex,
              content: <CodexPanel open={showCodex} onClose={() => setShowCodex(false)} />,
            },
            {
              id: 'wir',
              width: 600,
              open: !!wirAddress,
              content: (
                <WalletIntelligencePanel
                  open={!!wirAddress}
                  onClose={closeWIR}
                  walletAddress={wirAddress}
                />
              ),
            },
            {
              id: 'tir',
              width: 750,
              open: !!tipToken,
              content: (
                <TokenIntelligencePanel
                  open={!!tipToken}
                  onClose={closeTIP}
                  token={tipToken}
                />
              ),
            },
          ]}
          onCloseAll={closeAll}
        />

        <TagReferencePanel open={showTagRef} onClose={() => setShowTagRef(false)} />
      </div>
    </CodexContext.Provider>
  );
}

export function DashboardWrapper({
  children,
  defaultOpen
}: DashboardWrapperProps) {
  return (
    <ApiSettingsProvider>
      <StarredProvider>
        <WalletNametagsProvider>
          <WalletIntelligenceProvider>
            <TokenIntelligenceProvider>
              {/* Toggles data-tab-hidden on <html>; CSS pauses animations + transitions
                  while hidden so the GPU isn't churning on status pulses in the background. */}
              <TabVisibilityWatcher />
              <DashboardContent defaultOpen={defaultOpen}>{children}</DashboardContent>
            </TokenIntelligenceProvider>
          </WalletIntelligenceProvider>
        </WalletNametagsProvider>
      </StarredProvider>
    </ApiSettingsProvider>
  );
}
