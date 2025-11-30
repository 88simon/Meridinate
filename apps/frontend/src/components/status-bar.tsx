'use client';

import React from 'react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover';
import { AggregatedOperation } from '@/lib/api';
import { ChevronUp, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface StatusBarProps {
  tokensScanned: number;
  latestAnalysis: string | null;
  latestTokenName?: string | null;
  latestWalletsFound?: number | null;
  latestApiCredits?: number | null;
  totalApiCreditsToday?: number;
  isFiltered?: boolean;
  filteredCount?: number;
  recentOperations?: AggregatedOperation[];
  onRefresh?: () => void;
  lastUpdated?: Date | null;
}

// Format timestamp to short time
function formatTime(timestamp: string | null): string {
  if (!timestamp) return '';
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

// Format credits with comma separators
function formatCredits(credits: number): string {
  return credits.toLocaleString();
}

export function StatusBar({
  tokensScanned,
  latestAnalysis,
  latestTokenName,
  latestWalletsFound,
  latestApiCredits,
  totalApiCreditsToday = 0,
  isFiltered = false,
  filteredCount = 0,
  recentOperations = [],
  onRefresh,
  lastUpdated
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

          {/* Total API Credits Today with Recent Operations Popover */}
          <Popover>
            <PopoverTrigger asChild>
              <button className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 transition-colors'>
                <span className='text-muted-foreground text-xs font-medium'>
                  API Credits Today:
                </span>
                <span className='text-sm font-bold'>
                  {formatCredits(totalApiCreditsToday)}
                </span>
                {recentOperations.length > 0 && (
                  <ChevronUp className='text-muted-foreground h-3 w-3' />
                )}
              </button>
            </PopoverTrigger>
            <PopoverContent
              className='w-80 p-0'
              side='top'
              align='start'
              sideOffset={8}
            >
              <div className='border-b px-3 py-2'>
                <h4 className='text-sm font-semibold'>Recent Operations</h4>
                {lastUpdated && (
                  <p className='text-muted-foreground text-xs'>
                    Updated {formatTime(lastUpdated.toISOString())}
                  </p>
                )}
              </div>
              <div className='max-h-56 overflow-y-auto'>
                {recentOperations.length > 0 ? (
                  <ul className='divide-y'>
                    {recentOperations.map((op, idx) => (
                      <li
                        key={`${op.timestamp}-${idx}`}
                        className='flex items-center justify-between px-3 py-2.5 text-xs'
                      >
                        <div className='flex flex-col gap-0.5'>
                          <span className='font-medium'>{op.label}</span>
                          <span className='text-muted-foreground'>
                            {formatTime(op.timestamp)}
                            {op.transaction_count > 1 && (
                              <span className='ml-1'>
                                ({op.transaction_count} calls)
                              </span>
                            )}
                          </span>
                        </div>
                        <span className='font-mono text-sm font-semibold'>
                          {formatCredits(op.credits)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className='text-muted-foreground px-3 py-4 text-center text-xs'>
                    No operations today
                  </p>
                )}
              </div>
              {onRefresh && (
                <div className='border-t px-3 py-2'>
                  <Button
                    variant='ghost'
                    size='sm'
                    className='h-7 w-full text-xs'
                    onClick={onRefresh}
                  >
                    <RefreshCw className='mr-1 h-3 w-3' />
                    Refresh
                  </Button>
                </div>
              )}
            </PopoverContent>
          </Popover>

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

        {/* Right side - refresh button for manual trigger */}
        <div className='flex items-center gap-2'>
          {onRefresh && (
            <Button
              variant='ghost'
              size='sm'
              className='h-7 text-xs'
              onClick={onRefresh}
            >
              <RefreshCw className='mr-1 h-3 w-3' />
              Refresh
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
