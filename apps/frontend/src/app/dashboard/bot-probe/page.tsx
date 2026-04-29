'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { StatusBar } from '@/components/status-bar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Loader2, Search, Play, RefreshCw, GitCompare, Download,
  ChevronDown, ChevronRight, Zap, Clock, Target, TrendingUp,
  BarChart3, Shield,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';

interface ProbeStatus {
  running: boolean;
  wallet: string | null;
  phase: string;
  detail: string;
  progress_current: number;
  progress_total: number;
  credits_used: number;
}

interface ProbeRun {
  id: number;
  wallet_address: string;
  phase: string;
  status: string;
  started_at: string;
  completed_at: string;
  credits_used: number;
  known_tokens_probed: number;
  transactions_parsed: number;
  sell_coverage_rate: number;
}

export default function BotProbePage() {
  const { openWIR } = useWalletIntelligence();
  const statusBarData = useStatusBarData();
  const [walletInput, setWalletInput] = useState('');
  const [status, setStatus] = useState<ProbeStatus>({ running: false, wallet: null, phase: '', detail: '', progress_current: 0, progress_total: 0, credits_used: 0 });
  const [runs, setRuns] = useState<ProbeRun[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [profileWallet, setProfileWallet] = useState('');
  const [comparison, setComparison] = useState<any>(null);
  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [loading, setLoading] = useState(false);

  // Poll status when running
  useEffect(() => {
    if (!status.running) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/bot-probe/status`);
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
          if (!data.running && data.phase === 'complete') {
            toast.success('Bot probe complete');
            loadRuns();
          } else if (!data.running && data.phase === 'error') {
            toast.error(`Probe error: ${data.detail}`);
          }
        }
      } catch { /* silent */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [status.running]);

  const loadRuns = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/bot-probe/runs?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setRuns(data.runs || []);
      }
    } catch { /* silent */ }
  };

  useEffect(() => { loadRuns(); }, []);

  const startProbe = async () => {
    if (!walletInput.trim()) { toast.error('Enter a wallet address'); return; }
    try {
      const res = await fetch(`${API_BASE_URL}/api/bot-probe/run?wallet=${walletInput.trim()}&phases=all`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'already_running') {
          toast.info(`Probe already running for ${data.wallet?.slice(0, 12)}...`);
        } else {
          toast.info('Bot probe started');
          setStatus({ ...status, running: true, wallet: walletInput.trim(), phase: 'starting', detail: 'Initializing...', credits_used: 0, progress_current: 0, progress_total: 0 });
        }
      }
    } catch { toast.error('Failed to start probe'); }
  };

  const loadProfile = async (addr: string) => {
    setLoading(true);
    setProfileWallet(addr);
    try {
      const res = await fetch(`${API_BASE_URL}/api/bot-probe/profile/${addr}`);
      if (res.ok) {
        const data = await res.json();
        if (data.error) { toast.error(data.error); setProfile(null); }
        else { setProfile(data.profile || data); }
      }
    } catch { toast.error('Failed to load profile'); }
    finally { setLoading(false); }
  };

  const runComparison = async () => {
    if (!compareA.trim() || !compareB.trim()) { toast.error('Enter both wallet addresses'); return; }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/bot-probe/compare?wallet_a=${compareA.trim()}&wallet_b=${compareB.trim()}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.error) { toast.error(data.error); }
        else { setComparison(data); toast.success('Comparison complete'); }
      }
    } catch { toast.error('Failed to compare'); }
    finally { setLoading(false); }
  };

  const downloadProfile = (addr: string) => {
    window.open(`${API_BASE_URL}/api/bot-probe/profile/${addr}`, '_blank');
  };

  const pct = (v: number | null | undefined) => v != null ? `${(v * 100).toFixed(1)}%` : '—';
  const sol = (v: number | null | undefined) => v != null ? `${v.toFixed(4)} SOL` : '—';
  const secs = (v: number | null | undefined) => {
    if (v == null) return '—';
    if (v < 60) return `${v.toFixed(0)}s`;
    if (v < 3600) return `${(v / 60).toFixed(1)}m`;
    return `${(v / 3600).toFixed(1)}h`;
  };

  return (
    <div className='w-full space-y-4 px-6 py-6'>
      {/* Header */}
      <div>
        <h1 className='text-2xl font-bold flex items-center gap-2'>
          <Search className='h-6 w-6' />
          Bot Probe
        </h1>
        <p className='text-muted-foreground text-sm'>
          Reverse engineer profitable bots — full transaction history, FIFO round-trips, strategy profiling
        </p>
      </div>

      {/* Probe launcher */}
      <div className='rounded-lg border bg-card p-4 space-y-3'>
        <h3 className='text-sm font-semibold'>Launch Probe</h3>
        <div className='flex gap-2'>
          <Input
            placeholder='Wallet address to probe...'
            value={walletInput}
            onChange={(e) => setWalletInput(e.target.value)}
            className='font-mono text-xs flex-1'
          />
          <Button onClick={startProbe} disabled={status.running} className='gap-2'>
            {status.running ? <><Loader2 className='h-4 w-4 animate-spin' /> Probing...</> : <><Play className='h-4 w-4' /> Probe</>}
          </Button>
        </div>
        <p className='text-[10px] text-muted-foreground'>
          Runs all phases: transaction collection, unknown token discovery, strategy profile. Typically 5-15 minutes per wallet.
        </p>
      </div>

      {/* Live progress */}
      {status.running && (
        <div className='rounded-lg border bg-card p-4 space-y-2'>
          <div className='flex items-center gap-3'>
            <Loader2 className='h-4 w-4 animate-spin text-primary' />
            <span className='text-sm font-medium capitalize'>{status.phase}</span>
            {status.progress_total > 0 && (
              <span className='text-xs text-muted-foreground ml-auto'>
                {status.progress_current}/{status.progress_total}
              </span>
            )}
          </div>
          {status.progress_total > 0 && (
            <div className='h-2 w-full rounded-full bg-muted overflow-hidden'>
              <div className='h-full rounded-full bg-primary transition-all duration-300'
                style={{ width: `${(status.progress_current / status.progress_total) * 100}%` }} />
            </div>
          )}
          <p className='text-xs text-muted-foreground'>{status.detail}</p>
          <p className='text-[10px] text-muted-foreground'>{status.credits_used.toLocaleString()} Helius credits used</p>
        </div>
      )}

      <div className='flex gap-4'>
        {/* Main content */}
        <div className='flex-1 min-w-0 space-y-4'>
          {/* Profile viewer */}
          <div className='rounded-lg border bg-card p-4 space-y-3'>
            <h3 className='text-sm font-semibold'>View Profile</h3>
            <div className='flex gap-2'>
              <Input
                placeholder='Wallet address...'
                value={profileWallet}
                onChange={(e) => setProfileWallet(e.target.value)}
                className='font-mono text-xs flex-1'
              />
              <Button variant='outline' size='sm' onClick={() => loadProfile(profileWallet)} disabled={loading}>
                <RefreshCw className='h-3.5 w-3.5 mr-1' /> Load
              </Button>
              {profile && (
                <Button variant='outline' size='sm' onClick={() => downloadProfile(profileWallet)}>
                  <Download className='h-3.5 w-3.5 mr-1' /> JSON
                </Button>
              )}
            </div>

            {profile && (
              <div className='space-y-4 pt-2'>
                {/* Archetype badge */}
                <div className='flex items-center gap-3'>
                  <span className='text-lg font-bold'>{profile.archetype?.replace(/_/g, ' ')}</span>
                  <span className='text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary font-mono'>
                    {profile.round_trip_accounting_method}
                  </span>
                </div>

                {/* Performance grid */}
                <div className='grid grid-cols-4 gap-3'>
                  <StatCard icon={TrendingUp} label='Win Rate (trade)' value={pct(profile.performance?.win_rate_by_trade)} />
                  <StatCard icon={TrendingUp} label='Win Rate (token)' value={pct(profile.performance?.win_rate_by_token)} />
                  <StatCard icon={BarChart3} label='Expectancy' value={sol(profile.performance?.expectancy_per_trade_sol)} />
                  <StatCard icon={BarChart3} label='Profit Factor' value={profile.performance?.profit_factor?.toFixed(2) || '—'} />
                  <StatCard icon={Target} label='Round Trips' value={profile.performance?.total_round_trips?.toString() || '0'} />
                  <StatCard icon={Target} label='Tokens Traded' value={profile.performance?.total_tokens_traded?.toString() || '0'} />
                  <StatCard icon={Clock} label='Daily Consistency' value={pct(profile.performance?.daily_pnl_consistency)} />
                  <StatCard icon={TrendingUp} label='Total PnL' value={sol(profile.performance?.total_realized_pnl_sol)} />
                </div>

                {/* Entry / Exit / Sizing / Infra */}
                <div className='grid grid-cols-2 gap-4'>
                  <ProfileSection title='Entry Behavior' icon={Zap} data={{
                    'Median Entry': secs(profile.entry_behavior?.median_entry_seconds),
                    'Avg Entry': secs(profile.entry_behavior?.avg_entry_seconds),
                    'Entries/Day': profile.entry_behavior?.entries_per_day_avg?.toFixed(1),
                  }} />
                  <ProfileSection title='Exit Behavior' icon={Clock} data={{
                    'Hold (winners)': secs(profile.exit_behavior?.avg_hold_seconds_winners),
                    'Hold (losers)': secs(profile.exit_behavior?.avg_hold_seconds_losers),
                    'Median Hold': secs(profile.exit_behavior?.median_hold_seconds),
                    'Exit Multiple (W)': profile.exit_behavior?.avg_exit_multiple_winners?.toFixed(3),
                  }} />
                  <ProfileSection title='Position Sizing' icon={BarChart3} data={{
                    'Avg Size': sol(profile.position_sizing?.avg_position_sol),
                    'Median': sol(profile.position_sizing?.median_position_sol),
                    'Min': sol(profile.position_sizing?.min_position_sol),
                    'Max': sol(profile.position_sizing?.max_position_sol),
                  }} />
                  <ProfileSection title='Infrastructure' icon={Shield} data={{
                    'Nozomi': pct(profile.infrastructure?.nozomi_rate),
                    'Jito': pct(profile.infrastructure?.jito_rate),
                    'Standard': pct(profile.infrastructure?.standard_rate),
                    'Primary': profile.infrastructure?.primary_infrastructure,
                  }} />
                </div>

                {/* Behavioral */}
                <div className='rounded-lg border p-3 space-y-2'>
                  <h4 className='text-xs font-semibold flex items-center gap-1'><Target className='h-3.5 w-3.5' /> Behavioral Profile</h4>
                  <div className='grid grid-cols-3 gap-2 text-[11px]'>
                    <div><span className='text-muted-foreground'>Add to Winner:</span> <span className='font-medium'>{pct(profile.behavioral?.add_to_winner_rate)}</span></div>
                    <div><span className='text-muted-foreground'>Add to Loser:</span> <span className='font-medium'>{pct(profile.behavioral?.add_to_loser_rate)}</span></div>
                    <div><span className='text-muted-foreground'>Partial Takes:</span> <span className='font-medium'>{pct(profile.behavioral?.partial_take_rate)}</span></div>
                    <div><span className='text-muted-foreground'>Re-entry Rate:</span> <span className='font-medium'>{pct(profile.behavioral?.reentry_after_exit_rate)}</span></div>
                    <div><span className='text-muted-foreground'>Avg Buys/Token:</span> <span className='font-medium'>{profile.behavioral?.avg_buys_per_token?.toFixed(1)}</span></div>
                    <div><span className='text-muted-foreground'>Avg Sells/Token:</span> <span className='font-medium'>{profile.behavioral?.avg_sells_per_token?.toFixed(1)}</span></div>
                    <div><span className='text-muted-foreground'>Avg Trips/Token:</span> <span className='font-medium'>{profile.behavioral?.avg_round_trips_per_token?.toFixed(1)}</span></div>
                    <div><span className='text-muted-foreground'>Multi-buy Rate:</span> <span className='font-medium'>{pct(profile.behavioral?.multi_buy_rate)}</span></div>
                    <div><span className='text-muted-foreground'>Multi-sell Rate:</span> <span className='font-medium'>{pct(profile.behavioral?.multi_sell_rate)}</span></div>
                  </div>
                </div>

                {/* Meridinate Overlap */}
                {profile.meridinate_overlap && (
                  <div className='rounded-lg border p-3 space-y-2'>
                    <h4 className='text-xs font-semibold'>Meridinate Overlap</h4>
                    <div className='grid grid-cols-3 gap-2 text-[11px]'>
                      <div><span className='text-muted-foreground'>Overlap Tokens:</span> <span className='font-medium'>{profile.meridinate_overlap.overlap_count}</span></div>
                      <div><span className='text-muted-foreground'>Bot WR on Overlap:</span> <span className='font-medium'>{pct(profile.meridinate_overlap.bot_win_rate_on_overlap)}</span></div>
                      <div><span className='text-muted-foreground'>Avg Score:</span> <span className='font-medium'>{profile.meridinate_overlap.avg_meridinate_score?.toFixed(1) || '—'}</span></div>
                    </div>
                  </div>
                )}

                {/* Entry timing distribution */}
                {profile.entry_behavior?.entry_timing_distribution && (
                  <div className='rounded-lg border p-3 space-y-2'>
                    <h4 className='text-xs font-semibold'>Entry Timing Distribution</h4>
                    <div className='space-y-1'>
                      {Object.entries(profile.entry_behavior.entry_timing_distribution).map(([bucket, rate]) => (
                        <div key={bucket} className='flex items-center gap-2 text-[11px]'>
                          <span className='w-28 text-muted-foreground'>{bucket.replace(/_/g, ' ')}</span>
                          <div className='flex-1 h-3 rounded bg-muted overflow-hidden'>
                            <div className='h-full rounded bg-primary/60' style={{ width: `${(rate as number) * 100}%` }} />
                          </div>
                          <span className='w-12 text-right font-mono'>{((rate as number) * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Comparison */}
          <div className='rounded-lg border bg-card p-4 space-y-3'>
            <h3 className='text-sm font-semibold flex items-center gap-2'>
              <GitCompare className='h-4 w-4' /> Compare Bots
            </h3>
            <div className='flex gap-2'>
              <Input placeholder='Wallet A...' value={compareA} onChange={(e) => setCompareA(e.target.value)} className='font-mono text-xs' />
              <span className='text-xs text-muted-foreground self-center'>vs</span>
              <Input placeholder='Wallet B...' value={compareB} onChange={(e) => setCompareB(e.target.value)} className='font-mono text-xs' />
              <Button variant='outline' size='sm' onClick={runComparison} disabled={loading}>Compare</Button>
            </div>

            {comparison && (
              <div className='space-y-3 pt-2'>
                <div className='flex gap-4 text-xs'>
                  <div className='flex-1 rounded border p-2'>
                    <div className='font-semibold text-primary'>A: {comparison.archetype_a?.replace(/_/g, ' ')}</div>
                    <button onClick={() => openWIR(comparison.wallet_a)} className='font-mono text-[10px] text-muted-foreground hover:text-primary hover:underline break-all'>{comparison.wallet_a}</button>
                  </div>
                  <div className='flex-1 rounded border p-2'>
                    <div className='font-semibold text-primary'>B: {comparison.archetype_b?.replace(/_/g, ' ')}</div>
                    <button onClick={() => openWIR(comparison.wallet_b)} className='font-mono text-[10px] text-muted-foreground hover:text-primary hover:underline break-all'>{comparison.wallet_b}</button>
                  </div>
                </div>

                <div className='grid grid-cols-2 gap-2 text-[11px]'>
                  <CompareRow label='Faster Entry' winner={comparison.speed?.faster} a={secs(comparison.speed?.a_median_entry_seconds)} b={secs(comparison.speed?.b_median_entry_seconds)} />
                  <CompareRow label='Higher Win Rate' winner={comparison.win_rate?.higher_trade_wr} a={pct(comparison.win_rate?.a_by_trade)} b={pct(comparison.win_rate?.b_by_trade)} />
                  <CompareRow label='Higher Expectancy' winner={comparison.expectancy?.higher_expectancy} a={sol(comparison.expectancy?.a_per_trade_sol)} b={sol(comparison.expectancy?.b_per_trade_sol)} />
                  <CompareRow label='Cuts Losses Faster' winner={comparison.hold_time?.cuts_losses_faster} a={secs(comparison.hold_time?.a_losers_avg)} b={secs(comparison.hold_time?.b_losers_avg)} />
                  <CompareRow label='More Consistent' winner={comparison.consistency?.more_consistent} a={pct(comparison.consistency?.a_daily_consistency)} b={pct(comparison.consistency?.b_daily_consistency)} />
                  <CompareRow label='More Selective' winner={comparison.selectivity?.more_selective} a={comparison.selectivity?.a_tokens_traded?.toString()} b={comparison.selectivity?.b_tokens_traded?.toString()} />
                </div>

                {comparison.token_overlap && (
                  <div className='rounded border p-2 text-[11px] space-y-1'>
                    <div className='font-semibold'>Token Overlap: {comparison.token_overlap.count} shared tokens</div>
                    <div className='flex gap-4 text-muted-foreground'>
                      <span>Both won: {comparison.token_overlap.both_won}</span>
                      <span>A won / B lost: {comparison.token_overlap.a_won_b_lost}</span>
                      <span>B won / A lost: {comparison.token_overlap.b_won_a_lost}</span>
                      <span>Both lost: {comparison.token_overlap.both_lost}</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar: probe history */}
        <div className='w-56 shrink-0'>
          <h3 className='text-xs font-semibold text-muted-foreground mb-2'>Probe History</h3>
          <div className='space-y-1'>
            {runs.map((r) => (
              <button
                key={r.id}
                onClick={() => loadProfile(r.wallet_address)}
                className='w-full text-left rounded-lg border px-3 py-2 text-xs transition-all hover:bg-muted/50'
              >
                <div className='font-mono text-[10px] text-muted-foreground break-all'>{r.wallet_address}</div>
                <div className='flex justify-between text-[10px] text-muted-foreground mt-1'>
                  <span className={cn(
                    r.status === 'completed' ? 'text-green-400' : r.status === 'failed' ? 'text-red-400' : 'text-yellow-400'
                  )}>{r.status}</span>
                  <span>{r.credits_used} credits</span>
                </div>
                <div className='text-[10px] text-muted-foreground'>
                  {r.phase} · {r.known_tokens_probed} tokens · {r.started_at}
                </div>
              </button>
            ))}
            {runs.length === 0 && (
              <p className='text-[11px] text-muted-foreground'>No probes yet</p>
            )}
          </div>
        </div>
      </div>
      <StatusBar
        tokensScanned={statusBarData.tokensScanned} tokensScannedToday={statusBarData.tokensScannedToday}
        latestAnalysis={null} latestTokenName={null}
        latestWalletsFound={null} latestApiCredits={null}
        totalApiCreditsToday={statusBarData.creditsUsedToday}
        recentOperations={statusBarData.recentOperations}
        onRefresh={statusBarData.refresh} lastUpdated={statusBarData.lastUpdated}
      />
    </div>
  );
}


function StatCard({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className='rounded-lg border p-2 space-y-1'>
      <div className='flex items-center gap-1 text-[10px] text-muted-foreground'>
        <Icon className='h-3 w-3' />{label}
      </div>
      <div className='text-sm font-semibold'>{value}</div>
    </div>
  );
}


function ProfileSection({ title, icon: Icon, data }: { title: string; icon: any; data: Record<string, any> }) {
  return (
    <div className='rounded-lg border p-3 space-y-2'>
      <h4 className='text-xs font-semibold flex items-center gap-1'><Icon className='h-3.5 w-3.5' /> {title}</h4>
      <div className='space-y-1'>
        {Object.entries(data).map(([k, v]) => (
          <div key={k} className='flex justify-between text-[11px]'>
            <span className='text-muted-foreground'>{k}</span>
            <span className='font-medium'>{v ?? '—'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


function CompareRow({ label, winner, a, b }: { label: string; winner: string; a: string; b: string }) {
  return (
    <div className='flex items-center gap-2 rounded border p-1.5'>
      <span className='text-muted-foreground w-28 shrink-0'>{label}</span>
      <span className={cn('flex-1 text-center font-medium', winner === 'a' ? 'text-green-400' : '')}>{a}</span>
      <span className={cn('flex-1 text-center font-medium', winner === 'b' ? 'text-green-400' : '')}>{b}</span>
    </div>
  );
}
