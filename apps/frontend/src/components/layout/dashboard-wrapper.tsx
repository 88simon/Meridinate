'use client';

import { useState } from 'react';
import AppSidebar from '@/components/layout/app-sidebar';
import Header from '@/components/layout/header';
import { CodexPanel } from '@/components/codex-panel';
import { ScheduledJobsPanel } from '@/components/scheduled-jobs-panel';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { CodexContext } from '@/contexts/codex-context';
import { ApiSettingsProvider } from '@/contexts/ApiSettingsContext';

interface DashboardWrapperProps {
  children: React.ReactNode;
  defaultOpen: boolean;
}

function DashboardContent({ children, defaultOpen }: DashboardWrapperProps) {
  const [showCodex, setShowCodex] = useState(false);
  const [showScheduler, setShowScheduler] = useState(false);

  const handleCodexToggle = () => {
    setShowCodex((prev) => !prev);
  };

  const handleSchedulerToggle = () => {
    setShowScheduler((prev) => !prev);
  };

  return (
    <CodexContext.Provider value={{ isCodexOpen: showCodex }}>
      <div className='flex h-screen overflow-hidden'>
        <SidebarProvider defaultOpen={defaultOpen}>
          <AppSidebar
            onCodexToggle={handleCodexToggle}
            onSchedulerToggle={handleSchedulerToggle}
          />
          <div className='flex flex-1 overflow-hidden'>
            <SidebarInset className='flex-1 overflow-auto'>
              <Header />
              {children}
            </SidebarInset>
            <CodexPanel open={showCodex} onClose={() => setShowCodex(false)} />
            <ScheduledJobsPanel
              open={showScheduler}
              onClose={() => setShowScheduler(false)}
            />
          </div>
        </SidebarProvider>
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
      <DashboardContent defaultOpen={defaultOpen}>{children}</DashboardContent>
    </ApiSettingsProvider>
  );
}
