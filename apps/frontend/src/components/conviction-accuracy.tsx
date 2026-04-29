'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface AccuracyData {
  total_with_verdict: number;
  overall_accuracy: number | null;
  by_status: Record<string, {
    total: number;
    wins: number;
    losses: number;
    accuracy: number | null;
    description: string;
  }>;
  message: string;
}

export function ConvictionAccuracy() {
  const [data, setData] = useState<AccuracyData | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/ingest/realtime/accuracy`)
      .then((r) => r.ok ? r.json() : null)
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data || data.total_with_verdict === 0) {
    return (
      <TooltipProvider>
        <div className='rounded-lg border p-3'>
          <div className='flex items-center gap-2'>
            <span className='text-xs font-medium'>Conviction Accuracy</span>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className='text-muted-foreground text-[10px] cursor-help border-b border-dotted border-muted-foreground/30'>
                  No data yet
                </span>
              </TooltipTrigger>
              <TooltipContent className='max-w-xs'>
                <p className='text-xs'>
                  Accuracy data populates once tokens detected by the real-time feed
                  go through the full pipeline and receive a verdict (verified-win or verified-loss).
                  This takes days as the MC tracker monitors token performance.
                </p>
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </TooltipProvider>
    );
  }

  const statuses = [
    { key: 'high_conviction', label: 'High Conviction', color: 'text-green-400', bg: 'bg-green-500/10' },
    { key: 'watching', label: 'Watching', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
    { key: 'weak', label: 'Weak', color: 'text-zinc-400', bg: 'bg-zinc-500/10' },
    { key: 'rejected', label: 'Rejected', color: 'text-red-400', bg: 'bg-red-500/10' },
  ];

  return (
    <TooltipProvider>
      <div className='rounded-lg border p-3'>
        <div className='flex items-center justify-between mb-2'>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className='text-xs font-medium cursor-help border-b border-dotted border-muted-foreground/30'>
                Conviction Accuracy Report Card
              </span>
            </TooltipTrigger>
            <TooltipContent className='max-w-xs'>
              <p className='text-xs'>
                Measures how well our birth conviction labels predicted actual token outcomes.
                HIGH CONVICTION accuracy = % that actually won. REJECTED accuracy = % correctly
                identified as losses. Higher = our scoring system is more reliable.
              </p>
            </TooltipContent>
          </Tooltip>
          {data.overall_accuracy !== null && (
            <span className={cn(
              'text-sm font-bold',
              data.overall_accuracy >= 70 ? 'text-green-400' :
              data.overall_accuracy >= 50 ? 'text-yellow-400' : 'text-red-400'
            )}>
              {data.overall_accuracy}% overall
            </span>
          )}
        </div>

        <div className='grid grid-cols-4 gap-2'>
          {statuses.map(({ key, label, color, bg }) => {
            const s = data.by_status[key];
            if (!s) return (
              <div key={key} className={cn('rounded p-2 text-center', bg)}>
                <div className={cn('text-lg font-bold', color)}>—</div>
                <div className='text-muted-foreground text-[9px]'>{label}</div>
              </div>
            );
            return (
              <Tooltip key={key}>
                <TooltipTrigger asChild>
                  <div className={cn('rounded p-2 text-center cursor-help', bg)}>
                    <div className={cn('text-lg font-bold', color)}>
                      {s.accuracy !== null ? `${s.accuracy}%` : '—'}
                    </div>
                    <div className='text-muted-foreground text-[9px]'>{label}</div>
                    <div className='text-muted-foreground text-[8px]'>
                      {s.wins}W / {s.losses}L ({s.total})
                    </div>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className='text-xs'>{s.description}</p>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>

        <p className='text-muted-foreground text-[9px] mt-1.5'>
          {data.total_with_verdict < 20 && (
            <span className='text-amber-400 font-medium'>
              ⚠️ Low sample size ({data.total_with_verdict} tokens).
              Accuracy is unreliable below ~50 samples.{' '}
            </span>
          )}
          {data.message}
        </p>
      </div>
    </TooltipProvider>
  );
}
