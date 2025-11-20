'use client';

import React from 'react';

interface StatusBarProps {
  tokensScanned: number;
  latestAnalysis: string | null;
  latestTokenName?: string | null;
  latestWalletsFound?: number | null;
  latestApiCredits?: number | null;
  totalApiCreditsToday?: number;
  isFiltered?: boolean;
  filteredCount?: number;
}

export function StatusBar({
  tokensScanned,
  latestAnalysis,
  latestTokenName,
  latestWalletsFound,
  latestApiCredits,
  totalApiCreditsToday = 0,
  isFiltered = false,
  filteredCount = 0
}: StatusBarProps) {
  return (
    <div className='bg-card/95 fixed right-0 bottom-0 left-0 z-50 border-t backdrop-blur-sm'>
      <div className='container mx-auto flex items-center justify-between px-4 py-2'>
        <div className='flex items-center gap-4'>
          {/* Tokens Scanned */}
          <div className='flex items-center gap-2'>
            <span className='text-muted-foreground text-xs font-medium'>
              Tokens Scanned:
            </span>
            <span className='text-sm font-bold'>
              {isFiltered ? (
                <>
                  {filteredCount}
                  <span className='text-muted-foreground ml-1 text-xs font-normal'>
                    of {tokensScanned}
                  </span>
                </>
              ) : (
                tokensScanned
              )}
            </span>
          </div>

          {/* Total API Credits Today */}
          <div className='flex items-center gap-2'>
            <span className='text-muted-foreground text-xs font-medium'>
              API Credits Used Today:
            </span>
            <span className='text-sm font-bold'>{totalApiCreditsToday}</span>
          </div>

          {/* Latest Analysis */}
          <div className='hidden items-center gap-2 lg:flex'>
            <span className='text-muted-foreground text-xs font-medium'>
              Latest:
            </span>
            <div className='flex flex-col'>
              {latestAnalysis && latestTokenName ? (
                <>
                  <span className='text-xs font-semibold'>
                    {latestTokenName}
                  </span>
                  <div className='text-muted-foreground flex gap-2 text-[10px]'>
                    <span>
                      {new Date(
                        latestAnalysis.replace(' ', 'T') + 'Z'
                      ).toLocaleString()}
                    </span>
                    {latestWalletsFound !== null && (
                      <span>• {latestWalletsFound} wallets</span>
                    )}
                    {latestApiCredits !== null && (
                      <span>• {latestApiCredits} credits</span>
                    )}
                  </div>
                </>
              ) : (
                <span className='text-sm font-medium'>-</span>
              )}
            </div>
          </div>
        </div>

        {/* Optional: Add more status info or actions here */}
        <div className='flex items-center gap-2'>
          {/* Future: Can add quick actions here */}
        </div>
      </div>
    </div>
  );
}
