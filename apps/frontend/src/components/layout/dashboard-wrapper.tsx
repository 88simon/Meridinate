'use client';

import { useState } from 'react';
import AppSidebar from '@/components/layout/app-sidebar';
import Header from '@/components/layout/header';
import { CodexPanel } from '@/components/codex-panel';
import { WalletIntelligencePanel } from '@/components/wallet-intelligence-panel';
import { TokenIntelligencePanel } from '@/components/token-intelligence-panel';
import { TagReferencePanel } from '@/components/tag-reference-panel';
import { PanelStack } from '@/components/layout/panel-stack';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { CodexContext } from '@/contexts/codex-context';
import { ApiSettingsProvider } from '@/contexts/ApiSettingsContext';
import { WalletIntelligenceProvider, useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { TokenIntelligenceProvider, useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { StarredProvider } from '@/contexts/starred-context';

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
        <WalletIntelligenceProvider>
          <TokenIntelligenceProvider>
            <DashboardContent defaultOpen={defaultOpen}>{children}</DashboardContent>
          </TokenIntelligenceProvider>
        </WalletIntelligenceProvider>
      </StarredProvider>
    </ApiSettingsProvider>
  );
}
