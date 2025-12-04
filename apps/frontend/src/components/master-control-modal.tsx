'use client';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Settings2 } from 'lucide-react';
import {
  ScanningTab,
  SchedulerTab,
  WebhooksTab,
  SystemTab,
  ApiSettings
} from '@/components/master-control';

interface MasterControlModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apiSettings: ApiSettings;
  setApiSettings: (settings: ApiSettings) => void;
  defaultApiSettings: ApiSettings;
  children: React.ReactNode;
}

export function MasterControlModal({
  open,
  onOpenChange,
  apiSettings,
  setApiSettings,
  defaultApiSettings,
  children
}: MasterControlModalProps) {
  return (
    <TooltipProvider>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogTrigger asChild>{children}</DialogTrigger>
        <DialogContent className='max-h-[85vh] w-full max-w-2xl overflow-hidden'>
          <DialogHeader>
            <DialogTitle className='flex items-center gap-2'>
              <Settings2 className='h-5 w-5' />
              Settings
            </DialogTitle>
            <DialogDescription>
              Controls for scanning, ingestion, and tracking
            </DialogDescription>
          </DialogHeader>

          <Tabs defaultValue='scheduler' className='flex-1'>
            <TabsList className='grid w-full grid-cols-4'>
              <TabsTrigger value='scheduler' className='text-xs'>
                Scheduler
              </TabsTrigger>
              <TabsTrigger value='scanning' className='text-xs'>
                Scanning
              </TabsTrigger>
              <TabsTrigger value='webhooks' className='text-xs'>
                Webhooks
              </TabsTrigger>
              <TabsTrigger value='system' className='text-xs'>
                System
              </TabsTrigger>
            </TabsList>

            <div className='mt-4 h-[55vh] overflow-y-auto pr-2'>
              <TabsContent value='scheduler'>
                <SchedulerTab
                  bypassLimits={apiSettings.bypassLimits ?? false}
                />
              </TabsContent>

              <TabsContent value='scanning'>
                <ScanningTab
                  apiSettings={apiSettings}
                  setApiSettings={setApiSettings}
                  defaultApiSettings={defaultApiSettings}
                />
              </TabsContent>

              <TabsContent value='webhooks'>
                <WebhooksTab />
              </TabsContent>

              <TabsContent value='system'>
                <SystemTab />
              </TabsContent>
            </div>
          </Tabs>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}

// Re-export types for backwards compatibility
export type { ApiSettings } from '@/components/master-control';
