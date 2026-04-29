'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { TokenAddressCell } from '@/components/token-address-cell';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface TrajectoryReading {
  timestamp: string;
  mc: number;
  minutes_since_creation: number;
}

interface LifecycleData {
  token_address: string;
  birth: {
    detected_at: string;
    conviction_score: number;
    deployer_score: number;
    safety_score: number;
    social_proof_score: number;
    status: string;
    deployer_address: string | null;
    deployer_token_count: number;
    deployer_win_rate: number | null;
    token_name: string | null;
    token_symbol: string | null;
    initial_sol: number;
  } | null;
  trajectory: {
    trajectory: TrajectoryReading[];
    peak_mc: number;
    peak_mc_at: string | null;
    peak_minutes: number;
    readings_count: number;
    final_mc: number;
    tracking_duration_minutes: number;
    stop_reason: string | null;
  } | null;
  analysis: {
    token_id: number;
    analysis_timestamp: string | null;
    market_cap_usd: number | null;
    market_cap_usd_current: number | null;
    market_cap_ath: number | null;
    wallets_found: number | null;
    score_momentum: number | null;
    score_smart_money: number | null;
    score_risk: number | null;
    score_composite: number | null;
    webhook_detected_at: string | null;
    webhook_conviction_score: number | null;
    time_to_migration_minutes: number | null;
  } | null;
  verdict: {
    verdict: string | null;
    multiplier: string | null;
    ath_multiple: number | null;
  } | null;
  accuracy: {
    birth_prediction: string;
    actual_outcome: string;
    prediction_correct: boolean;
  } | null;
}

function formatMC(mc: number | null | undefined): string {
  if (!mc) return '—';
  if (mc >= 1_000_000) return `$${(mc / 1_000_000).toFixed(1)}M`;
  if (mc >= 1_000) return `$${(mc / 1_000).toFixed(1)}k`;
  return `$${mc.toFixed(0)}`;
}

function formatTime(isoStr: string | null): string {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

interface Props {
  open: boolean;
  onClose: () => void;
  tokenAddress: string | null;
}

export function LifecyclePanel({ open, onClose, tokenAddress }: Props) {
  const [data, setData] = useState<LifecycleData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !tokenAddress) { setData(null); return; }
    setLoading(true);
    fetch(`${API_BASE_URL}/api/ingest/lifecycle/${tokenAddress}`)
      .then((r) => r.ok ? r.json() : null)
      .then(setData)
      .catch(() => toast.error('Failed to load lifecycle'))
      .finally(() => setLoading(false));
  }, [open, tokenAddress]);

  if (!open) return null;

  const trajectory = data?.trajectory?.trajectory || [];
  const maxMC = trajectory.length > 0 ? Math.max(...trajectory.map(r => r.mc)) : 0;

  return (
    <div className='fixed inset-0 z-50 flex justify-end bg-black/40' onClick={onClose}>
      <div
        className='flex h-full w-[550px] flex-col border-l bg-background shadow-xl animate-in slide-in-from-right duration-200'
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-4 py-3'>
          <div>
            <h3 className='text-sm font-semibold'>
              Token Lifecycle — {data?.birth?.token_name || data?.birth?.token_symbol || tokenAddress?.slice(0, 12) + '...'}
            </h3>
            {tokenAddress && (
              <div className='mt-0.5'>
                <TokenAddressCell address={tokenAddress} compact showTwitter={false} />
              </div>
            )}
          </div>
          <Button variant='ghost' size='sm' onClick={onClose} className='h-7 w-7 p-0'>
            <X className='h-4 w-4' />
          </Button>
        </div>

        {/* Content */}
        <div className='flex-1 overflow-y-auto p-4 space-y-4'>
          {loading && <div className='py-8 text-center text-muted-foreground text-sm'>Loading lifecycle data...</div>}

          {data && !loading && (
            <>
              {/* Accuracy banner */}
              {data.accuracy && (
                <div className={cn(
                  'rounded-lg border p-3',
                  data.accuracy.prediction_correct ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'
                )}>
                  <div className='flex items-center justify-between'>
                    <span className='text-xs font-medium'>
                      {data.accuracy.prediction_correct ? '✓ Prediction Correct' : '✗ Prediction Wrong'}
                    </span>
                    <span className='text-[10px] text-muted-foreground'>
                      Birth: {data.accuracy.birth_prediction.toUpperCase()} → Actual: {data.accuracy.actual_outcome === 'verified-win' ? 'WIN' : 'LOSS'}
                    </span>
                  </div>
                </div>
              )}

              {/* Stage 0: Birth */}
              {data.birth && (
                <div className='rounded-lg border p-3'>
                  <div className='text-xs font-medium mb-2'>Stage 0 — Birth Detection (RTTF)</div>
                  <div className='space-y-1 text-[11px]'>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Detected At</span>
                      <span>{formatTime(data.birth.detected_at)}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Conviction Score</span>
                      <span className={cn(
                        'font-bold',
                        data.birth.conviction_score >= 70 ? 'text-green-400' :
                        data.birth.conviction_score >= 40 ? 'text-yellow-400' : 'text-red-400'
                      )}>
                        {data.birth.conviction_score}/100
                      </span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Score Breakdown</span>
                      <span>D:{data.birth.deployer_score} S:{data.birth.safety_score} P:{data.birth.social_proof_score}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Birth Status</span>
                      <span className={cn(
                        data.birth.status === 'high_conviction' ? 'text-green-400' :
                        data.birth.status === 'rejected' ? 'text-red-400' :
                        data.birth.status === 'weak' ? 'text-zinc-400' : 'text-yellow-400'
                      )}>
                        {data.birth.status.toUpperCase().replace('_', ' ')}
                      </span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Initial SOL</span>
                      <span>{data.birth.initial_sol?.toFixed(2)} SOL</span>
                    </div>
                    {data.birth.deployer_address && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Deployer</span>
                        <span className='font-mono text-[10px]'>
                          {data.birth.deployer_address.slice(0, 12)}...
                          {data.birth.deployer_token_count > 0 && ` (${data.birth.deployer_token_count} tokens`}
                          {data.birth.deployer_win_rate !== null && `, ${(data.birth.deployer_win_rate * 100).toFixed(0)}% win)`}
                          {data.birth.deployer_token_count > 0 && !data.birth.deployer_win_rate && ')'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Stage 0.5: Trajectory */}
              {data.trajectory && data.trajectory.trajectory.length > 0 && (
                <div className='rounded-lg border p-3'>
                  <div className='text-xs font-medium mb-2'>Stage 0.5 — MC Trajectory</div>
                  <div className='space-y-1 text-[11px] mb-3'>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Peak MC</span>
                      <span className='text-green-400 font-bold'>{formatMC(data.trajectory.peak_mc)}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Time to Peak</span>
                      <span>{data.trajectory.peak_minutes.toFixed(1)} min</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Final MC</span>
                      <span>{formatMC(data.trajectory.final_mc)}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Duration</span>
                      <span>{data.trajectory.tracking_duration_minutes.toFixed(0)} min ({data.trajectory.readings_count} readings)</span>
                    </div>
                    {data.trajectory.stop_reason && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Stop Reason</span>
                        <span className='text-muted-foreground'>{data.trajectory.stop_reason}</span>
                      </div>
                    )}
                  </div>

                  {/* Mini bar chart of trajectory */}
                  <div className='flex items-end gap-px h-16'>
                    {trajectory.map((r, i) => {
                      const height = maxMC > 0 ? Math.max(2, (r.mc / maxMC) * 100) : 2;
                      const isPeak = r.mc === data.trajectory!.peak_mc;
                      return (
                        <div
                          key={i}
                          className={cn(
                            'flex-1 rounded-t-sm min-w-[2px]',
                            isPeak ? 'bg-green-400' :
                            r.mc >= (data.trajectory!.peak_mc * 0.8) ? 'bg-green-500/50' :
                            r.mc >= (data.trajectory!.peak_mc * 0.3) ? 'bg-blue-500/50' :
                            'bg-red-500/50'
                          )}
                          style={{ height: `${height}%` }}
                          title={`${r.minutes_since_creation.toFixed(0)}min: ${formatMC(r.mc)}`}
                        />
                      );
                    })}
                  </div>
                  <div className='flex justify-between text-[9px] text-muted-foreground mt-1'>
                    <span>{trajectory[0]?.minutes_since_creation.toFixed(0)}min</span>
                    <span>{trajectory[trajectory.length - 1]?.minutes_since_creation.toFixed(0)}min</span>
                  </div>
                </div>
              )}

              {/* Stage 1-2: Analysis */}
              {data.analysis && (
                <div className='rounded-lg border p-3'>
                  <div className='text-xs font-medium mb-2'>Stage 1-2 — Full Analysis</div>
                  <div className='space-y-1 text-[11px]'>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Analyzed At</span>
                      <span>{formatTime(data.analysis.analysis_timestamp)}</span>
                    </div>
                    {data.analysis.time_to_migration_minutes && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Time to Migration</span>
                        <span>{data.analysis.time_to_migration_minutes.toFixed(1)} min</span>
                      </div>
                    )}
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>MC at Scan</span>
                      <span>{formatMC(data.analysis.market_cap_usd)}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>MC Current</span>
                      <span>{formatMC(data.analysis.market_cap_usd_current)}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>ATH</span>
                      <span className='text-green-400'>{formatMC(data.analysis.market_cap_ath)}</span>
                    </div>
                    <div className='flex justify-between'>
                      <span className='text-muted-foreground'>Wallets Found</span>
                      <span>{data.analysis.wallets_found}</span>
                    </div>
                    {data.analysis.score_composite !== null && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Scores</span>
                        <span>
                          M:{data.analysis.score_momentum?.toFixed(0)}
                          {' '}S:{data.analysis.score_smart_money?.toFixed(0)}
                          {' '}R:{data.analysis.score_risk?.toFixed(0)}
                          {' '}= {data.analysis.score_composite?.toFixed(0)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Verdict */}
              {data.verdict && data.verdict.verdict && (
                <div className={cn(
                  'rounded-lg border p-3',
                  data.verdict.verdict === 'verified-win' ? 'border-green-500/30' : 'border-red-500/30'
                )}>
                  <div className='text-xs font-medium mb-2'>Final Verdict</div>
                  <div className='flex items-center gap-3'>
                    <span className={cn(
                      'text-lg font-bold',
                      data.verdict.verdict === 'verified-win' ? 'text-green-400' : 'text-red-400'
                    )}>
                      {data.verdict.verdict === 'verified-win' ? 'WIN' : 'LOSS'}
                      {data.verdict.multiplier && ` ${data.verdict.multiplier.replace('win:', '').toUpperCase()}`}
                    </span>
                    {data.verdict.ath_multiple && (
                      <span className='text-muted-foreground text-sm'>
                        {data.verdict.ath_multiple.toFixed(1)}x ATH multiple
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* No data states */}
              {!data.birth && !data.analysis && (
                <div className='py-8 text-center text-muted-foreground text-sm'>
                  No lifecycle data found for this token.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
