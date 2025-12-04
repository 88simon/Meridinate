'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { getScheduledJobs, ScheduledJob, RunningJob } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  X,
  Clock,
  Play,
  Pause,
  RefreshCw,
  Loader2,
  Activity
} from 'lucide-react';
import { cn } from '@/lib/utils';

// Session storage cache key
const CACHE_KEY_JOBS = 'scheduler_panel_jobs';

interface CachedJobsData {
  jobs: ScheduledJob[];
  running_jobs: RunningJob[];
  scheduler_running: boolean;
  cached_at: number;
}

interface ScheduledJobsPanelProps {
  open: boolean;
  onClose: () => void;
}

// Cache helpers
function getFromCache(): CachedJobsData | null {
  try {
    const cached = sessionStorage.getItem(CACHE_KEY_JOBS);
    if (!cached) return null;
    const data = JSON.parse(cached) as CachedJobsData;
    // Consider cache stale after 5 minutes, but still usable
    return data;
  } catch {
    return null;
  }
}

function setInCache(data: Omit<CachedJobsData, 'cached_at'>): void {
  try {
    sessionStorage.setItem(
      CACHE_KEY_JOBS,
      JSON.stringify({ ...data, cached_at: Date.now() })
    );
  } catch {
    // Ignore storage errors
  }
}

/**
 * Format seconds into HH:MM:SS string
 */
function formatTime(seconds: number): string {
  if (seconds < 0) return '00:00:00';

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
  // Initialize from cache
  const cachedData = useRef(getFromCache());

  const [jobs, setJobs] = useState<ScheduledJob[]>(
    cachedData.current?.jobs || []
  );
  const [runningJobs, setRunningJobs] = useState<RunningJob[]>(
    cachedData.current?.running_jobs || []
  );
  const [schedulerRunning, setSchedulerRunning] = useState(
    cachedData.current?.scheduler_running ?? false
  );
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdowns, setCountdowns] = useState<Record<string, number>>({});
  const [elapsedTimes, setElapsedTimes] = useState<Record<string, number>>({});

  // Track if we have any data to show
  const hasData = jobs.length > 0 || runningJobs.length > 0;

  const loadJobs = useCallback(
    async (showLoader = true) => {
      if (showLoader && !hasData) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      setError(null);

      try {
        const data = await getScheduledJobs();
        setJobs(data.jobs);
        setRunningJobs(data.running_jobs || []);
        setSchedulerRunning(data.scheduler_running);

        // Cache the data
        setInCache({
          jobs: data.jobs,
          running_jobs: data.running_jobs || [],
          scheduler_running: data.scheduler_running
        });

        // Initialize countdowns
        const initialCountdowns: Record<string, number> = {};
        for (const job of data.jobs) {
          initialCountdowns[job.id] = getSecondsUntil(job.next_run_at);
        }
        setCountdowns(initialCountdowns);

        // Initialize elapsed times for running jobs
        const initialElapsed: Record<string, number> = {};
        for (const rj of data.running_jobs || []) {
          initialElapsed[rj.id] = rj.elapsed_seconds;
        }
        setElapsedTimes(initialElapsed);
      } catch (err) {
        // Only show error if we have no cached data
        if (!hasData) {
          setError(err instanceof Error ? err.message : 'Failed to load jobs');
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [hasData]
  );

  // Load jobs when panel opens - show cached immediately, refresh in background
  useEffect(() => {
    if (open) {
      // If we have cached data, initialize countdowns immediately
      if (cachedData.current?.jobs) {
        const initialCountdowns: Record<string, number> = {};
        for (const job of cachedData.current.jobs) {
          initialCountdowns[job.id] = getSecondsUntil(job.next_run_at);
        }
        setCountdowns(initialCountdowns);

        const initialElapsed: Record<string, number> = {};
        for (const rj of cachedData.current.running_jobs || []) {
          initialElapsed[rj.id] = rj.elapsed_seconds;
        }
        setElapsedTimes(initialElapsed);
      }

      // Always refresh data (background if we have cache)
      loadJobs(!cachedData.current);
    }
  }, [open, loadJobs]);

  // Timer - update countdowns and elapsed times every second
  useEffect(() => {
    if (!open) return;

    const intervalId = setInterval(() => {
      // Update countdowns (decrement)
      setCountdowns((prev) => {
        const updated: Record<string, number> = {};
        for (const job of jobs) {
          const current = prev[job.id] ?? getSecondsUntil(job.next_run_at);
          updated[job.id] = Math.max(0, current - 1);
        }
        return updated;
      });

      // Update elapsed times (increment)
      setElapsedTimes((prev) => {
        const updated: Record<string, number> = {};
        for (const rj of runningJobs) {
          updated[rj.id] = (prev[rj.id] ?? rj.elapsed_seconds) + 1;
        }
        return updated;
      });
    }, 1000);

    return () => clearInterval(intervalId);
  }, [open, jobs, runningJobs]);

  // Refresh data every 5 seconds when jobs are running, 30 seconds otherwise
  useEffect(() => {
    if (!open) return;

    const refreshMs = runningJobs.length > 0 ? 5000 : 30000;
    const refreshInterval = setInterval(() => {
      loadJobs(false); // Background refresh
    }, refreshMs);

    return () => clearInterval(refreshInterval);
  }, [open, loadJobs, runningJobs.length]);

  return (
    <div
      className={cn(
        'bg-background flex flex-col border-l transition-all duration-300 ease-in-out',
        open ? 'w-80' : 'w-0 border-l-0'
      )}
    >
      {open && (
        <div className='flex h-full flex-col overflow-hidden'>
          {/* Header */}
          <div className='flex items-center justify-between border-b px-4 py-3'>
            <div className='flex items-center gap-2'>
              <Clock className='h-4 w-4' />
              <span className='font-semibold'>Scheduled Jobs</span>
              {refreshing && (
                <Loader2 className='text-muted-foreground h-3 w-3 animate-spin' />
              )}
            </div>
            <div className='flex items-center gap-1'>
              <Button
                variant='ghost'
                size='icon'
                className='h-7 w-7'
                onClick={() => loadJobs(false)}
                disabled={loading || refreshing}
              >
                <RefreshCw
                  className={cn(
                    'h-4 w-4',
                    (loading || refreshing) && 'animate-spin'
                  )}
                />
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
            {loading && !hasData ? (
              <div className='flex items-center justify-center py-8'>
                <Loader2 className='h-5 w-5 animate-spin' />
              </div>
            ) : error && !hasData ? (
              <div className='flex flex-col items-center gap-3 py-4'>
                <div className='text-destructive text-center text-sm'>
                  {error}
                </div>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => loadJobs(true)}
                >
                  <RefreshCw className='mr-2 h-3 w-3' />
                  Retry
                </Button>
              </div>
            ) : (
              <div className='space-y-4'>
                {/* Running Jobs Section */}
                {runningJobs.length > 0 && (
                  <div className='space-y-2'>
                    <div className='flex items-center gap-2 text-xs font-semibold tracking-wide text-blue-500 uppercase'>
                      <Activity className='h-3.5 w-3.5 animate-pulse' />
                      Running Now
                    </div>
                    {runningJobs.map((rj) => {
                      const elapsed = elapsedTimes[rj.id] ?? rj.elapsed_seconds;
                      return (
                        <div
                          key={rj.id}
                          className='rounded-lg border border-blue-500/30 bg-blue-500/10 p-3'
                        >
                          <div className='flex items-center gap-2'>
                            <Loader2 className='h-3.5 w-3.5 animate-spin text-blue-500' />
                            <span className='text-sm font-medium'>
                              {rj.name}
                            </span>
                          </div>
                          <div className='mt-2 flex items-center gap-2'>
                            <span className='text-muted-foreground text-xs'>
                              Running for:
                            </span>
                            <span className='font-mono text-sm font-semibold text-blue-500'>
                              {formatTime(elapsed)}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Scheduled Jobs Section */}
                {jobs.length > 0 && (
                  <div className='space-y-2'>
                    {runningJobs.length > 0 && (
                      <div className='text-muted-foreground text-xs font-semibold tracking-wide uppercase'>
                        Scheduled
                      </div>
                    )}
                    {jobs.map((job) => {
                      const countdown = countdowns[job.id] ?? -1;
                      const isActive = job.enabled && countdown >= 0;
                      const isRunning = runningJobs.some(
                        (rj) => rj.id === job.id
                      );

                      // Skip jobs that are currently running
                      if (isRunning) return null;

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
                              <span className='text-sm font-medium'>
                                {job.name}
                              </span>
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
                                  {formatTime(countdown)}
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
                  </div>
                )}

                {jobs.length === 0 && runningJobs.length === 0 && !loading && (
                  <div className='text-muted-foreground py-4 text-center text-sm'>
                    No scheduled jobs found
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className='text-muted-foreground border-t px-4 py-2 text-center text-xs'>
            {runningJobs.length > 0
              ? 'Auto-refreshes every 5s'
              : 'Auto-refreshes every 30s'}
          </div>
        </div>
      )}
    </div>
  );
}
