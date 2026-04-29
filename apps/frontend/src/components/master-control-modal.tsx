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
  IntelTab,
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
        <DialogContent className='max-h-[90vh] w-full max-w-4xl overflow-hidden'>
          <DialogHeader>
            <DialogTitle className='flex items-center gap-2'>
              <Settings2 className='h-5 w-5' />
              Settings
            </DialogTitle>
            <DialogDescription>
              Pipeline automation and analysis configuration
            </DialogDescription>
          </DialogHeader>

          <Tabs defaultValue='pipeline' className='flex-1'>
            <TabsList className='grid w-full grid-cols-3'>
              <TabsTrigger value='pipeline' className='text-xs'>
                Pipeline
              </TabsTrigger>
              <TabsTrigger value='analysis' className='text-xs'>
                Analysis
              </TabsTrigger>
              <TabsTrigger value='intel' className='text-xs'>
                Intel
              </TabsTrigger>
            </TabsList>

            <div className='mt-4 h-[75vh] overflow-y-auto pr-2'>
              <TabsContent value='pipeline'>
                <SchedulerTab
                  bypassLimits={apiSettings.bypassLimits ?? false}
                />
              </TabsContent>

              <TabsContent value='analysis'>
                <ScanningTab
                  apiSettings={apiSettings}
                  setApiSettings={setApiSettings}
                  defaultApiSettings={defaultApiSettings}
                />
              </TabsContent>

              <TabsContent value='intel'>
                <IntelTab
                  apiSettings={apiSettings}
                  setApiSettings={setApiSettings}
                />
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
