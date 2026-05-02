'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { StatusBar } from '@/components/status-bar';
import { useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { Loader2, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface Progress {
  running: boolean;
  token_address: string | null;
  step: string;
  steps_completed: number;
  total_steps: number;
  started_at: string | null;
}

interface HistoryRun {
  id: number;
  token_address: string;
  token_id: number | null;
  token_name: string | null;
  token_symbol: string | null;
  market_cap_usd: number | null;
  clobr_score: number | null;
  lp_trust_score: number | null;
  credits_used: number;
  duration_seconds: number | null;
  started_at: string;
  completed_at: string | null;
}

function formatMC(v: number | null | undefined): string {
  if (v == null) return '--';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function formatDuration(s: number | null | undefined): string {
  if (s == null) return '--';
  if (s < 60) return `${s.toFixed(1)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function timeAgo(dateStr: string): string {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function scoreColor(score: number | null, thresholds: { green: number; yellow: number; invert?: boolean }): string {
  if (score == null) return '';
  if (thresholds.invert) {
    // higher is better (LP trust: green >70, yellow 40-70, red <40)
    if (score > thresholds.green) return 'text-green-400';
    if (score >= thresholds.yellow) return 'text-yellow-400';
    return 'text-red-400';
  }
  // CLOBr: red <30, yellow 30-59, green 60+
  if (score >= thresholds.green) return 'text-green-400';
  if (score >= thresholds.yellow) return 'text-yellow-400';
  return 'text-red-400';
}

export default function QuickDDPage() {
  const { openTIP } = useTokenIntelligence();
  const statusBarData = useStatusBarData();
  const [addressInput, setAddressInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<Progress>({ running: false, token_address: null, step: '', steps_completed: 0, total_steps: 0, started_at: null });
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/quick-dd/history?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setRuns(data.runs || []);
      }
    } catch { /* silent */ }
  }, []);

  // Load history on mount
  useEffect(() => { loadHistory(); }, [loadHistory]);

  // Poll progress when running. Skip while tab hidden — DD continues server-side.
  useEffect(() => {
    if (!progress.running) return;
    const interval = setInterval(async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/quick-dd/progress`);
        if (res.ok) {
          const data: Progress = await res.json();
          setProgress(data);
          if (!data.running) {
            toast.success('Quick DD complete');
            loadHistory();
          }
        }
      } catch { /* silent */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [progress.running, loadHistory]);

  // Elapsed timer
  useEffect(() => {
    if (progress.running && progress.started_at) {
      const start = new Date(progress.started_at).getTime();
      setElapsed(Math.floor((Date.now() - start) / 1000));
      elapsedRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - start) / 1000));
      }, 1000);
    } else {
      if (elapsedRef.current) clearInterval(elapsedRef.current);
      elapsedRef.current = null;
    }
    return () => { if (elapsedRef.current) clearInterval(elapsedRef.current); };
  }, [progress.running, progress.started_at]);

  const startDD = async () => {
    const addr = addressInput.trim();
    if (!addr) { toast.error('Paste a token address'); return; }
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/quick-dd/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token_address: addr }),
      });
      if (res.ok || res.status === 202) {
        toast.info('Quick DD started');
        setProgress({ running: true, token_address: addr, step: 'Starting...', steps_completed: 0, total_steps: 5, started_at: new Date().toISOString() });
        setAddressInput('');
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.error || `Failed to start DD (${res.status})`);
      }
    } catch { toast.error('Failed to start DD'); }
    finally { setSubmitting(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !submitting && !progress.running) startDD();
  };

  const progressSegments = 5;
  const filledSegments = Math.min(progress.steps_completed, progressSegments);

  return (
    <div className='w-full space-y-4 px-6 py-6'>
      {/* Header */}
      <div>
        <h1 className='text-2xl font-bold flex items-center gap-2'>
          <Zap className='h-6 w-6' />
          Quick DD
        </h1>
        <p className='text-muted-foreground text-sm'>
          Paste any token address for instant due diligence
        </p>
      </div>

      {/* Search bar */}
      <div className='rounded-lg border bg-card p-4'>
        <div className='flex gap-3'>
          <input
            type='text'
            placeholder='Paste token address...'
            value={addressInput}
            onChange={(e) => setAddressInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={submitting || progress.running}
            className='flex-1 bg-transparent border border-border rounded-lg px-4 py-3 text-base font-mono placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50'
          />
          <button
            onClick={startDD}
            disabled={submitting || progress.running}
            className='px-6 py-3 rounded-lg bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2'
          >
            {submitting ? <><Loader2 className='h-4 w-4 animate-spin' /> Starting...</> : 'DD Now'}
          </button>
        </div>
      </div>

      {/* Progress section */}
      {progress.running && (
        <div className='rounded-lg border bg-card p-4 space-y-3'>
          <div className='flex items-center justify-between'>
            <div className='flex items-center gap-3'>
              <Loader2 className='h-4 w-4 animate-spin text-primary' />
              <span className='text-sm font-medium'>Analyzing</span>
            </div>
            <span className='text-xs text-muted-foreground'>{elapsed}s elapsed</span>
          </div>
          <div className='font-mono text-xs text-muted-foreground break-all'>
            {progress.token_address}
          </div>
          <div className='text-xs text-muted-foreground'>{progress.step}</div>
          <div className='flex gap-1.5'>
            {Array.from({ length: progressSegments }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  'h-2 flex-1 rounded-full transition-colors duration-300',
                  i < filledSegments ? 'bg-primary' : 'bg-muted'
                )}
              />
            ))}
          </div>
          <div className='text-[10px] text-muted-foreground'>
            {progress.steps_completed}/{progress.total_steps} steps
          </div>
        </div>
      )}

      {/* History table */}
      <div className='rounded-lg border bg-card'>
        <div className='px-4 py-3 border-b'>
          <h3 className='text-sm font-semibold'>History</h3>
        </div>
        <div className='overflow-x-auto'>
          <table className='w-full text-xs'>
            <thead>
              <tr className='border-b text-muted-foreground'>
                <th className='text-left px-4 py-2 font-medium'>Token</th>
                <th className='text-right px-4 py-2 font-medium'>MC</th>
                <th className='text-right px-4 py-2 font-medium'>CLOBr</th>
                <th className='text-right px-4 py-2 font-medium'>LP Trust</th>
                <th className='text-right px-4 py-2 font-medium'>Credits</th>
                <th className='text-right px-4 py-2 font-medium'>Duration</th>
                <th className='text-right px-4 py-2 font-medium'>Time</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => run.token_id && openTIP({ id: run.token_id })}
                  className={cn(
                    'border-b last:border-b-0 transition-colors',
                    run.token_id ? 'cursor-pointer hover:bg-muted/50' : 'opacity-60'
                  )}
                >
                  <td className='px-4 py-2'>
                    <div className='flex items-center gap-1.5'>
                      <span className='font-medium text-sm'>
                        {run.token_name || (
                          <span className='font-mono text-[11px] text-muted-foreground'>
                            {run.token_address.slice(0, 6)}...{run.token_address.slice(-4)}
                          </span>
                        )}
                      </span>
                      {run.token_symbol && (
                        <span className='text-[10px] text-muted-foreground'>{run.token_symbol}</span>
                      )}
                    </div>
                  </td>
                  <td className='px-4 py-2 text-right font-mono'>{formatMC(run.market_cap_usd)}</td>
                  <td className={cn('px-4 py-2 text-right font-mono font-medium', scoreColor(run.clobr_score, { green: 60, yellow: 30 }))}>
                    {run.clobr_score != null ? run.clobr_score.toFixed(0) : '--'}
                  </td>
                  <td className={cn('px-4 py-2 text-right font-mono font-medium', scoreColor(run.lp_trust_score, { green: 70, yellow: 40, invert: true }))}>
                    {run.lp_trust_score != null ? run.lp_trust_score.toFixed(0) : '--'}
                  </td>
                  <td className='px-4 py-2 text-right text-muted-foreground'>{run.credits_used}</td>
                  <td className='px-4 py-2 text-right font-mono text-muted-foreground'>{formatDuration(run.duration_seconds)}</td>
                  <td className='px-4 py-2 text-right text-muted-foreground'>{timeAgo(run.started_at)}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={7} className='px-4 py-8 text-center text-muted-foreground text-sm'>
                    No DD runs yet. Paste a token address above to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <StatusBar
        tokensScanned={statusBarData.tokensScanned}
        tokensScannedToday={statusBarData.tokensScannedToday}
        latestAnalysis={null}
        latestTokenName={null}
        latestWalletsFound={null}
        latestApiCredits={null}
        totalApiCreditsToday={statusBarData.creditsUsedToday}
        recentOperations={statusBarData.recentOperations}
        onRefresh={statusBarData.refresh}
        lastUpdated={statusBarData.lastUpdated}
      />
    </div>
  );
}
