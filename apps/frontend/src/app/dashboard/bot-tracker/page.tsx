'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { API_BASE_URL } from '@/lib/api';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { StatusBar } from '@/components/status-bar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Radio, Play, Square, Plus, X, Eye, RefreshCw, Wifi, WifiOff,
  AlertTriangle, Flame, Users, TrendingUp, Copy, Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { useTokenIntelligence } from '@/contexts/token-intelligence-context';

// Lazy load heavy RTTF components
const RealtimeTokenFeed = dynamic(
  () => import('@/components/realtime-token-feed').then((mod) => ({ default: mod.RealtimeTokenFeed })),
  { ssr: false }
);
const ConvictionAccuracy = dynamic(
  () => import('@/components/conviction-accuracy').then((mod) => ({ default: mod.ConvictionAccuracy })),
  { ssr: false }
);

// ============================================================================
// Types
// ============================================================================
interface Target { id: number; wallet_address: string; label: string; added_at: string; active: number; }
interface Trade { wallet_address: string; token_address: string; token_name: string | null; direction: string; sol_amount: number; token_amount: number; timestamp: string; timestamp_unix: number; signature: string; tip_type: string | null; entry_seconds_after_creation: number | null; }
interface ShadowStatus { connected: boolean; trades_captured: number; wallets_tracked: number; last_trade_at: string | null; reconnect_count: number; started_at: string | null; tracked_wallets: string[]; feed_size: number; }

// ============================================================================
// Main Page
// ============================================================================
export default function CommandCenterPage() {
  const { openWIR } = useWalletIntelligence();
  const { openTIP } = useTokenIntelligence();

  // Token addresses on this page only carry the mint, not the analyzed_tokens id.
  // This helper resolves address → id via /api/tokens/by-address and opens the TIP.
  // Falls back to a toast if the token isn't in our analyzed set yet.
  const openTokenByAddress = useCallback(async (address: string) => {
    if (!address) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/tokens/by-address/${address}`);
      if (res.ok) {
        const data = await res.json();
        if (data?.id) { openTIP({ id: data.id }); return; }
      }
      toast.info('Token not yet analyzed — no Token Intelligence available');
    } catch {
      toast.error('Failed to open token details');
    }
  }, [openTIP]);

  // Shadow state
  const [status, setStatus] = useState<ShadowStatus | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [feed, setFeed] = useState<Trade[]>([]);
  const [filterWallet, setFilterWallet] = useState<string | null>(null);

  // Dashboard panels
  const [positions, setPositions] = useState<any>({ positions: [], by_wallet: {} });
  const [tokenHeat, setTokenHeat] = useState<any[]>([]);
  const [signals, setSignals] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [convergences, setConvergences] = useState<any[]>([]);


  // Add wallet
  const [newWallet, setNewWallet] = useState('');
  const [newLabel, setNewLabel] = useState('');

  // Bottom panel toggle
  const [showBottomPanel, setShowBottomPanel] = useState<'accuracy' | 'signals' | 'none'>('none');

  // Labels (memoized to avoid recreation on every 3s poll re-render)
  const labelMap = useMemo(() => {
    const map: Record<string, string> = {};
    targets.forEach(t => { if (t.label) map[t.wallet_address] = t.label; });
    return map;
  }, [targets]);
  const label = useCallback((addr: string) => labelMap[addr] || addr, [labelMap]);
  const statusBarData = useStatusBarData();
  const isConnected = status?.connected ?? false;

  // ---- Loaders ----
  const loadStatus = useCallback(async () => { try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/status`); if (r.ok) setStatus(await r.json()); } catch {} }, []);
  const loadTargets = useCallback(async () => { try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/targets`); if (r.ok) { const d = await r.json(); setTargets(d.targets || []); } } catch {} }, []);
  const loadFeed = useCallback(async () => {
    try {
      const p = new URLSearchParams({ limit: '100' });
      if (filterWallet) p.set('wallet', filterWallet);
      const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/feed?${p}`);
      if (r.ok) {
        const d = await r.json();
        // Defensive client cap — even if the API ever returns more rows, never
        // hold more than 100 trades in memory or render more than 100 <tr> nodes.
        const trades = (d.trades || []).slice(0, 100);
        setFeed(trades);
      }
    } catch {}
  }, [filterWallet]);
  const loadPositions = useCallback(async () => { try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/open-positions`); if (r.ok) setPositions(await r.json()); } catch {} }, []);
  const loadTokenHeat = useCallback(async () => { try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/token-heat?minutes=60`); if (r.ok) { const d = await r.json(); setTokenHeat(d.tokens || []); } } catch {} }, []);
  const loadSignals = useCallback(async () => {
    const w = filterWallet || targets.find(t => t.active)?.wallet_address;
    if (!w) return;
    try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/signal-wallets/${w}?min_appearances=2`); if (r.ok) setSignals(await r.json()); } catch {}
  }, [filterWallet, targets]);
  const loadAlerts = useCallback(async () => { try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/alerts?limit=15`); if (r.ok) { const d = await r.json(); setAlerts(d.alerts || []); } } catch {} }, []);
  const loadConvergences = useCallback(async () => { try { const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/convergences?limit=10`); if (r.ok) { const d = await r.json(); setConvergences(d.convergences || []); } } catch {} }, []);

  // ---- Polling ----
  useEffect(() => { loadStatus(); loadTargets(); }, []);
  useEffect(() => {
    const fast = setInterval(() => { if (!document.hidden) { loadStatus(); loadFeed(); } }, 3000);
    const med = setInterval(() => { if (!document.hidden) { loadPositions(); loadAlerts(); loadTokenHeat(); } }, 10000);
    const slow = setInterval(() => { if (!document.hidden) { loadSignals(); loadConvergences(); } }, 30000);
    loadFeed(); loadPositions(); loadAlerts(); loadTokenHeat(); loadSignals(); loadConvergences();
    return () => { clearInterval(fast); clearInterval(med); clearInterval(slow); };
  }, [loadFeed, loadPositions, loadAlerts, loadTokenHeat, loadSignals, loadConvergences]);

  // ---- Actions ----
  const startListener = async () => { await fetch(`${API_BASE_URL}/api/wallet-shadow/start`, { method: 'POST' }); toast.success('Shadow listener started'); loadStatus(); };
  const stopListener = async () => { await fetch(`${API_BASE_URL}/api/wallet-shadow/stop`, { method: 'POST' }); toast.info('Shadow listener stopped'); loadStatus(); };
  const addWallet = async () => {
    if (!newWallet.trim()) return;
    const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/track?wallet=${newWallet.trim()}&label=${encodeURIComponent(newLabel.trim())}`, { method: 'POST' });
    if (r.ok) { const d = await r.json(); toast.success(d.message); setNewWallet(''); setNewLabel(''); loadTargets(); loadStatus(); }
  };
  const removeWallet = async (addr: string) => { await fetch(`${API_BASE_URL}/api/wallet-shadow/untrack?wallet=${addr}`, { method: 'POST' }); toast.info('Stopped tracking'); loadTargets(); loadStatus(); };

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <div className='w-full h-[calc(100vh-3rem)] flex flex-col px-4 py-3 gap-2 overflow-hidden'>

      {/* ===== TOP BAR ===== */}
      <div className='flex items-center justify-between shrink-0'>
        <div className='flex items-center gap-3'>
          <h1 className='text-lg font-bold flex items-center gap-2'><Radio className='h-5 w-5' /> Command Center</h1>
          <div className='flex items-center gap-3 text-xs'>
            {isConnected ? (
              <span className='flex items-center gap-1 text-green-400'><span className='h-2 w-2 rounded-full bg-green-400 animate-pulse' /> Shadow Live · {status?.trades_captured || 0} trades</span>
            ) : (
              <span className='flex items-center gap-1 text-muted-foreground'><WifiOff className='h-3 w-3' /> Shadow Off</span>
            )}
          </div>
        </div>
        <div className='flex items-center gap-2'>
          {isConnected ? (
            <Button variant='outline' size='sm' onClick={stopListener} className='gap-1 text-xs h-7'><Square className='h-3 w-3' /> Stop Shadow</Button>
          ) : (
            <Button size='sm' onClick={startListener} className='gap-1 text-xs h-7'><Play className='h-3 w-3' /> Start Shadow</Button>
          )}
          {/* Bottom panel toggles */}
          <div className='flex gap-1 ml-2 border-l pl-2'>
            <button onClick={() => setShowBottomPanel(showBottomPanel === 'accuracy' ? 'none' : 'accuracy')}
              className={cn('text-[10px] px-2 py-1 rounded', showBottomPanel === 'accuracy' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground')}>
              Accuracy
            </button>
            <button onClick={() => setShowBottomPanel(showBottomPanel === 'signals' ? 'none' : 'signals')}
              className={cn('text-[10px] px-2 py-1 rounded', showBottomPanel === 'signals' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground')}>
              Signals
            </button>
          </div>
        </div>
      </div>

      {/* ===== MAIN: SPLIT FEED + INTELLIGENCE + MANAGEMENT ===== */}
      <div className='flex gap-2 flex-1 min-h-0'>

        {/* ===== LEFT: RTTF TOKEN FEED ===== */}
        <div className='flex-1 min-w-0 flex flex-col overflow-hidden rounded-lg border bg-card'>
          <div className='border-b px-3 py-1.5 flex items-center justify-between shrink-0'>
            <span className='text-[11px] font-semibold flex items-center gap-1'><Zap className='h-3.5 w-3.5 text-yellow-400' /> Token Births (RTTF)</span>
            <Button variant='ghost' size='sm' className='h-6 text-[10px]' onClick={async () => {
              try { await fetch(`${API_BASE_URL}/api/ingest/run-scan`, { method: 'POST' }); toast.success('Scan started'); } catch { toast.error('Failed'); }
            }}>Run Scan</Button>
          </div>
          <div className='flex-1 overflow-y-auto'>
            <RealtimeTokenFeed />
          </div>
        </div>

        {/* ===== CENTER: BOT TRADE FEED ===== */}
        <div className='flex-1 min-w-0 flex flex-col'>
          {/* Filter tabs */}
          <div className='flex items-center gap-1 shrink-0 mb-1'>
            <button onClick={() => setFilterWallet(null)}
              className={cn('text-[10px] px-2 py-0.5 rounded', !filterWallet ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground')}>All</button>
            {targets.filter(t => t.active).map(t => (
              <button key={t.wallet_address} onClick={() => setFilterWallet(t.wallet_address)}
                className={cn('text-[10px] px-2 py-0.5 rounded', filterWallet === t.wallet_address ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground')}>
                {t.label || t.wallet_address}
              </button>
            ))}
          </div>
          {/* Feed */}
          <div className='rounded-lg border bg-card flex-1 overflow-hidden flex flex-col'>
            <div className='border-b px-3 py-1.5 flex items-center justify-between shrink-0'>
              <span className='text-[11px] font-semibold flex items-center gap-1'><Radio className='h-3.5 w-3.5 text-green-400' /> Bot Trades</span>
              {status?.last_trade_at && <span className='text-[10px] text-muted-foreground'>Last: {status.last_trade_at}</span>}
            </div>
            <div className='flex-1 overflow-y-auto'>
              {feed.length > 0 ? (
                <table className='w-full text-[11px]'>
                  <thead className='sticky top-0 bg-card border-b z-10'>
                    <tr className='text-muted-foreground'>
                      <th className='text-left px-2 py-1 font-medium w-16'>Time</th>
                      <th className='text-left px-2 py-1 font-medium'>Wallet</th>
                      <th className='text-center px-2 py-1 font-medium w-10'>Side</th>
                      <th className='text-left px-2 py-1 font-medium'>Token</th>
                      <th className='text-right px-2 py-1 font-medium w-16'>SOL</th>
                      <th className='text-right px-2 py-1 font-medium w-12'>Speed</th>
                      <th className='text-center px-2 py-1 font-medium w-12'>Infra</th>
                    </tr>
                  </thead>
                  <tbody>
                    {feed.map((t, i) => {
                      const time = t.timestamp ? new Date(t.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : '—';
                      const isLarge = t.direction === 'buy' && t.sol_amount > 2;
                      return (
                        <tr key={`${t.signature}-${i}`} className={cn('border-b border-muted/20 hover:bg-muted/20', isLarge && 'bg-yellow-500/5')}>
                          <td className='px-2 py-1 text-muted-foreground font-mono'>{time}</td>
                          <td className='px-2 py-1'>
                            <button onClick={() => openWIR(t.wallet_address)} className='text-primary hover:underline text-[10px]'>{label(t.wallet_address)}</button>
                          </td>
                          <td className='px-2 py-1 text-center'>
                            <span className={cn('px-1 py-0.5 rounded text-[9px] font-bold',
                              t.direction === 'buy' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400')}>
                              {t.direction === 'buy' ? 'BUY' : 'SELL'}
                            </span>
                          </td>
                          <td className='px-2 py-1'>
                            <button onClick={() => openTokenByAddress(t.token_address)} className='text-muted-foreground hover:text-primary hover:underline font-mono text-[10px]'>
                              {t.token_name || t.token_address}
                            </button>
                          </td>
                          <td className='px-2 py-1 text-right font-mono font-medium'>{t.sol_amount.toFixed(4)}</td>
                          <td className='px-2 py-1 text-right text-muted-foreground'>
                            {t.entry_seconds_after_creation != null ? `${t.entry_seconds_after_creation.toFixed(0)}s` : '—'}
                          </td>
                          <td className='px-2 py-1 text-center'>
                            {t.tip_type && (
                              <span className={cn('text-[8px] px-1 py-0.5 rounded font-bold',
                                t.tip_type === 'nozomi' ? 'bg-purple-500/20 text-purple-400' : 'bg-orange-500/20 text-orange-400')}>
                                {t.tip_type.toUpperCase()}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className='flex items-center justify-center h-full text-muted-foreground text-xs'>
                  {isConnected ? 'Listening for trades...' : 'Start shadow to see trades.'}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ===== RIGHT: INTELLIGENCE + MANAGEMENT ===== */}
        <div className='w-56 shrink-0 flex flex-col gap-2 overflow-y-auto'>

          {/* Open Positions */}
          <Panel title='Positions' icon={TrendingUp}>
            {Object.keys(positions.by_wallet || {}).length > 0 ? (
              <div className='space-y-1'>
                {Object.entries(positions.by_wallet as Record<string, any>).map(([addr, stats]) => (
                  <div key={addr} className='flex justify-between text-[10px]'>
                    <button onClick={() => openWIR(addr)} className='text-primary hover:underline'>{label(addr)}</button>
                    <span className='text-muted-foreground'>{stats.open_positions}p · {stats.total_sol_deployed.toFixed(1)} SOL</span>
                  </div>
                ))}
              </div>
            ) : <Empty>No open positions</Empty>}
          </Panel>

          {/* Token Heat */}
          <Panel title='Token Heat' icon={Flame}>
            {tokenHeat.length > 0 ? (
              <div className='space-y-1'>
                {tokenHeat.slice(0, 6).map((t: any) => (
                  <div key={t.token_address} className='flex items-center justify-between gap-2 text-[10px]'>
                    <button onClick={() => openTokenByAddress(t.token_address)} className='text-muted-foreground hover:text-primary truncate'>
                      {t.token_name || t.token_address}
                    </button>
                    <span
                      className='px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400 text-[9px] font-medium shrink-0 whitespace-nowrap'
                      title='Number of YOUR tracked wallets that touched this token in the last hour'
                    >
                      {t.unique_wallets} wallet{t.unique_wallets === 1 ? '' : 's'}
                    </span>
                  </div>
                ))}
              </div>
            ) : <Empty>No activity</Empty>}
          </Panel>

          {/* Alerts */}
          <Panel title='Alerts' icon={AlertTriangle}>
            {alerts.length > 0 ? (
              <div className='space-y-1'>
                {alerts.slice(0, 6).map((a: any, i: number) => (
                  <div key={i} className={cn('rounded border p-1 text-[10px]',
                    a.type === 'sizing_anomaly' ? 'border-yellow-500/30' : 'border-blue-500/30')}>
                    <div className='flex items-center gap-1'>
                      {a.type === 'sizing_anomaly' ? <AlertTriangle className='h-2.5 w-2.5 text-yellow-400 shrink-0' /> : <Copy className='h-2.5 w-2.5 text-blue-400 shrink-0' />}
                      <span className='truncate'>{a.detail}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : <Empty>No alerts</Empty>}
          </Panel>

          {/* Convergence */}
          {convergences.length > 0 && (
            <Panel title='Convergence' icon={Users}>
              <div className='space-y-1'>
                {convergences.slice(0, 4).map((c: any) => (
                  <div key={c.id} className='flex items-center justify-between gap-2 text-[10px]'>
                    <button onClick={() => openTokenByAddress(c.token_address)} className='text-primary hover:underline truncate'>{c.token_name || c.token_address}</button>
                    <span
                      className='px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400 text-[9px] font-medium shrink-0 whitespace-nowrap'
                      title='Number of your tracked wallets that bought this token within the convergence window'
                    >
                      {c.wallet_count} buyer{c.wallet_count === 1 ? '' : 's'}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Track wallet */}
          <div className='rounded-lg border bg-card p-2 space-y-1 shrink-0'>
            <span className='text-[10px] font-semibold'>Track Wallet</span>
            <Input placeholder='Address...' value={newWallet} onChange={e => setNewWallet(e.target.value)} className='font-mono text-[10px] h-6' />
            <div className='flex gap-1'>
              <Input placeholder='Label...' value={newLabel} onChange={e => setNewLabel(e.target.value)} className='text-[10px] h-6 flex-1' />
              <Button size='sm' onClick={addWallet} className='h-6 px-2 text-[10px]'><Plus className='h-3 w-3' /></Button>
            </div>
          </div>

          {/* Tracked wallets */}
          <div className='space-y-1'>
            {targets.filter(t => t.active).map(t => (
              <TrackedWalletCard key={t.wallet_address} target={t} openWIR={openWIR}
                onFilter={() => setFilterWallet(t.wallet_address)} onRemove={() => removeWallet(t.wallet_address)} onRenamed={loadTargets} />
            ))}
          </div>

        </div>
      </div>

      {/* ===== BOTTOM PANEL (toggleable) ===== */}
      {showBottomPanel !== 'none' && (
        <div className='shrink-0 h-64 overflow-y-auto'>
          {showBottomPanel === 'accuracy' && <ConvictionAccuracy />}
          {showBottomPanel === 'signals' && signals?.signal_wallets?.length ? (
            <div className='rounded-lg border bg-card p-3 space-y-2'>
              <h3 className='text-xs font-semibold'>Signal Wallets — {signals.tokens_analyzed} tokens analyzed</h3>
              <div className='grid grid-cols-3 gap-2'>
                {signals.signal_wallets.map((sw: any) => (
                  <div key={sw.preceding_wallet} className='rounded border p-2 text-[10px] space-y-1'>
                    <div className='flex justify-between'>
                      <button onClick={() => openWIR(sw.preceding_wallet)} className='font-mono text-primary hover:underline break-all text-left'>{sw.preceding_wallet}</button>
                      <span className='text-green-400 font-bold shrink-0 ml-1'>{sw.times_preceded}x</span>
                    </div>
                    <div className='text-[9px] text-muted-foreground'>{sw.unique_tokens} tokens · avg {sw.avg_seconds_before}s before · ~{sw.avg_sol} SOL</div>
                  </div>
                ))}
              </div>
            </div>
          ) : showBottomPanel === 'signals' ? (
            <div className='rounded-lg border bg-card p-3 text-xs text-muted-foreground'>Collecting signal wallet data...</div>
          ) : null}
        </div>
      )}
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

// ============================================================================
// Sub-components
// ============================================================================

function Panel({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className='rounded-lg border bg-card p-2 space-y-1'>
      <div className='flex items-center gap-1 text-[11px] font-semibold'><Icon className='h-3.5 w-3.5 text-muted-foreground' /> {title}</div>
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className='text-[10px] text-muted-foreground py-1 text-center'>{children}</p>;
}

function TrackedWalletCard({ target, openWIR, onFilter, onRemove, onRenamed }: {
  target: Target; openWIR: (a: string) => void; onFilter: () => void; onRemove: () => void; onRenamed: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(target.label || '');
  const saveLabel = async () => {
    const r = await fetch(`${API_BASE_URL}/api/wallet-shadow/rename?wallet=${target.wallet_address}&label=${encodeURIComponent(editLabel.trim())}`, { method: 'POST' });
    if (r.ok) { toast.success(`Renamed to "${editLabel.trim()}"`); setEditing(false); onRenamed(); }
  };
  return (
    <div className='rounded border border-green-500/20 bg-green-500/5 px-2 py-1 text-[10px]'>
      <div className='flex justify-between'>
        {editing ? (
          <div className='flex gap-1 flex-1 mr-1'>
            <Input value={editLabel} onChange={e => setEditLabel(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') saveLabel(); if (e.key === 'Escape') setEditing(false); }}
              className='h-5 text-[10px] px-1 flex-1' autoFocus />
            <button onClick={saveLabel} className='text-green-400 text-[10px] font-bold'>OK</button>
          </div>
        ) : (
          <button onClick={() => { setEditLabel(target.label || ''); setEditing(true); }} className='font-medium hover:text-primary' title='Click to rename'>
            {target.label || 'Unnamed'}
          </button>
        )}
        {!editing && (
          <div className='flex gap-1'>
            <button onClick={() => openWIR(target.wallet_address)}><Eye className='h-3 w-3 text-muted-foreground hover:text-primary' /></button>
            <button onClick={onRemove}><X className='h-3 w-3 text-muted-foreground hover:text-red-400' /></button>
          </div>
        )}
      </div>
      <button onClick={onFilter} className='font-mono text-[9px] text-muted-foreground hover:text-primary break-all text-left'>{target.wallet_address}</button>
    </div>
  );
}
