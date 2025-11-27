'use client';

import React, { useState } from 'react';
import Image from 'next/image';
import { cn } from '@/lib/utils';

interface MtewSwabTabsProps {
  /** Total count of filtered MTEW wallets */
  mtewCount: number;
  /** Total count of all MTEW wallets */
  mtewTotal: number;
  /** Content to render for MTEW tab */
  mtewContent: React.ReactNode;
  /** Content to render for SWAB tab */
  swabContent: React.ReactNode;
  /** Ref for scrolling to top */
  sectionRef?: React.RefObject<HTMLDivElement>;
}

type TabId = 'mtew' | 'swab';

export function MtewSwabTabs({
  mtewCount,
  mtewTotal,
  mtewContent,
  swabContent,
  sectionRef
}: MtewSwabTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>('mtew');

  return (
    <div ref={sectionRef} className='bg-card rounded-lg border p-3'>
      {/* Tab Header */}
      <div className='bg-card sticky top-0 z-10 pt-1 pb-2'>
        <div className='flex items-center gap-4'>
          {/* Tabs */}
          <div className='flex items-center'>
            {/* MTEW Tab */}
            <button
              onClick={() => setActiveTab('mtew')}
              className={cn(
                'flex items-center gap-2 rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                activeTab === 'mtew'
                  ? 'border-primary text-primary bg-primary/5'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50 border-transparent'
              )}
            >
              <Image
                src='/icons/tokens/bunny_icon.png'
                alt='Bunny'
                width={20}
                height={20}
                className='h-5 w-5'
              />
              <span>Multi-Token Early Wallets</span>
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-xs font-semibold',
                  activeTab === 'mtew'
                    ? 'bg-primary/10 text-primary'
                    : 'bg-muted text-muted-foreground'
                )}
              >
                {mtewCount}
              </span>
              {mtewCount !== mtewTotal && (
                <span className='text-muted-foreground text-xs whitespace-nowrap'>
                  of {mtewTotal}
                </span>
              )}
            </button>

            {/* SWAB Tab */}
            <button
              onClick={() => setActiveTab('swab')}
              className={cn(
                'flex items-center gap-2 rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                activeTab === 'swab'
                  ? 'border-primary text-primary bg-primary/5'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50 border-transparent'
              )}
            >
              <span className='text-lg'>📊</span>
              <span>Smart Wallet Archive Builder</span>
            </button>
          </div>
        </div>

        {/* Separator line */}
        <div className='-mx-3 mt-2 border-b' />
      </div>

      {/* Tab Content */}
      <div className='pt-2'>
        {activeTab === 'mtew' ? mtewContent : swabContent}
      </div>
    </div>
  );
}
