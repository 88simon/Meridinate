'use client';

import { useState, useEffect, useCallback } from 'react';
import { getScheduledJobs, ScheduledJob } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { X, Clock, Play, Pause, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ScheduledJobsPanelProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Format seconds into HH:MM:SS countdown string
 */
function formatCountdown(seconds: number): string {
  if (seconds <= 0) return '00:00:00';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Calculate seconds until next run from ISO timestamp
 */
function getSecondsUntil(isoTimestamp: string | null): number {
  if (!isoTimestamp) return -1;

  const targetTime = new Date(isoTimestamp).getTime();
  const now = Date.now();
  const diffMs = targetTime - now;

  return Math.max(0, Math.floor(diffMs / 1000));
}

export function ScheduledJobsPanel({ open, onClose }: ScheduledJobsPanelProps) {
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdowns, setCountdowns] = useState<Record<string, number>>({});

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getScheduledJobs();
      setJobs(data.jobs);
      setSchedulerRunning(data.scheduler_running);

      // Initialize countdowns
      const initialCountdowns: Record<string, number> = {};
      for (const job of data.jobs) {
        initialCountdowns[job.id] = getSecondsUntil(job.next_run_at);
      }
      setCountdowns(initialCountdowns);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  // Load jobs when panel opens
  useEffect(() => {
    if (open) {
      loadJobs();
    }
  }, [open, loadJobs]);

  // Countdown timer - update every second
  useEffect(() => {
    if (!open || jobs.length === 0) return;

    const intervalId = setInterval(() => {
      setCountdowns((prev) => {
        const updated: Record<string, number> = {};
        for (const job of jobs) {
          const current = prev[job.id] ?? getSecondsUntil(job.next_run_at);
          updated[job.id] = Math.max(0, current - 1);
        }
        return updated;
      });
    }, 1000);

    return () => clearInterval(intervalId);
  }, [open, jobs]);

  // Refresh data every 30 seconds to keep next_run_at accurate
  useEffect(() => {
    if (!open) return;

    const refreshInterval = setInterval(() => {
      loadJobs();
    }, 30000);

    return () => clearInterval(refreshInterval);
  }, [open, loadJobs]);

  if (!open) return null;

  return (
    <div
      className={cn(
        'bg-background fixed top-0 right-0 z-50 flex h-full w-80 flex-col border-l shadow-lg',
        'transform transition-transform duration-200 ease-in-out',
        open ? 'translate-x-0' : 'translate-x-full'
      )}
    >
      {/* Header */}
      <div className='flex items-center justify-between border-b px-4 py-3'>
        <div className='flex items-center gap-2'>
          <Clock className='h-4 w-4' />
          <span className='font-semibold'>Scheduled Jobs</span>
        </div>
        <div className='flex items-center gap-1'>
          <Button
            variant='ghost'
            size='icon'
            className='h-7 w-7'
            onClick={loadJobs}
            disabled={loading}
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          </Button>
          <Button
            variant='ghost'
            size='icon'
            className='h-7 w-7'
            onClick={onClose}
          >
            <X className='h-4 w-4' />
          </Button>
        </div>
      </div>

      {/* Scheduler Status */}
      <div className='border-b px-4 py-2'>
        <div className='flex items-center gap-2 text-xs'>
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              schedulerRunning ? 'bg-green-500' : 'bg-red-500'
            )}
          />
          <span className='text-muted-foreground'>
            Scheduler: {schedulerRunning ? 'Running' : 'Stopped'}
          </span>
        </div>
      </div>

      {/* Jobs List */}
      <div className='flex-1 overflow-y-auto p-4'>
        {loading && jobs.length === 0 ? (
          <div className='flex items-center justify-center py-8'>
            <Loader2 className='h-5 w-5 animate-spin' />
          </div>
        ) : error ? (
          <div className='text-destructive py-4 text-center text-sm'>
            {error}
          </div>
        ) : (
          <div className='space-y-3'>
            {jobs.map((job) => {
              const countdown = countdowns[job.id] ?? -1;
              const isActive = job.enabled && countdown >= 0;

              return (
                <div
                  key={job.id}
                  className={cn(
                    'rounded-lg border p-3 transition-colors',
                    job.enabled ? 'bg-card' : 'bg-muted/50 opacity-60'
                  )}
                >
                  <div className='flex items-start justify-between'>
                    <div className='flex items-center gap-2'>
                      {job.enabled ? (
                        <Play className='h-3.5 w-3.5 text-green-500' />
                      ) : (
                        <Pause className='text-muted-foreground h-3.5 w-3.5' />
                      )}
                      <span className='text-sm font-medium'>{job.name}</span>
                    </div>
                  </div>

                  <div className='mt-2 space-y-1'>
                    {isActive ? (
                      <div className='flex items-center gap-2'>
                        <span className='text-muted-foreground text-xs'>
                          Next run in:
                        </span>
                        <span
                          className={cn(
                            'font-mono text-sm font-semibold',
                            countdown <= 60
                              ? 'text-orange-500'
                              : countdown <= 300
                                ? 'text-yellow-500'
                                : 'text-foreground'
                          )}
                        >
                          {formatCountdown(countdown)}
                        </span>
                      </div>
                    ) : (
                      <span className='text-muted-foreground text-xs'>
                        {job.enabled ? 'Waiting...' : 'Disabled'}
                      </span>
                    )}

                    <div className='text-muted-foreground text-xs'>
                      Interval: {job.interval_minutes} min
                      {job.interval_minutes >= 60 &&
                        ` (${(job.interval_minutes / 60).toFixed(1)}h)`}
                    </div>
                  </div>
                </div>
              );
            })}

            {jobs.length === 0 && !loading && (
              <div className='text-muted-foreground py-4 text-center text-sm'>
                No scheduled jobs found
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className='text-muted-foreground border-t px-4 py-2 text-center text-xs'>
        Auto-refreshes every 30s
      </div>
    </div>
  );
}
