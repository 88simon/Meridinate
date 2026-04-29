'use client';

import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { TokenAddressCell } from '@/components/token-address-cell';

const RealtimeHistoryPanel = dynamic(
  () => import('@/components/realtime-history-panel').then((mod) => ({ default: mod.RealtimeHistoryPanel })),
  { ssr: false }
);
const LifecyclePanel = dynamic(
  () => import('@/components/lifecycle-panel').then((mod) => ({ default: mod.LifecyclePanel })),
  { ssr: false }
);
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface DetectedToken {
  token_address: string;
  deployer_address: string | null;
  detected_at: string;
  conviction_score: number;
  deployer_score: number;
  safety_score: number;
  social_proof_score: number;
  deployer_token_count: number;
  deployer_win_rate: number | null;
  deployer_tags: string[];
  initial_sol: number;
  mint_authority_revoked: boolean | null;
  freeze_authority_active: boolean | null;
  smart_wallets_buying: number;
  smart_wallet_names: string[];
  total_buyers: number;
  // Crime coin detection
  crime_risk_score: number;
  buys_in_first_3_blocks: number;
  fresh_buyer_pct: number;
  buyers_sharing_funder: number;
  deployer_linked_to_buyer: boolean;
  buy_amount_uniformity: number;
  watch_window_complete: boolean;
  status: 'high_conviction' | 'watching' | 'weak' | 'rejected';
  rejection_reason: string | null;
  mc_at_30s: number;
  token_name: string | null;
  token_symbol: string | null;
}

interface RealtimeStats {
  running: boolean;
  total_detected: number;
  total_rejected: number;
  total_high_conviction: number;
  feed_size: number;
  last_event_at: string | null;
}

interface FeedResponse {
  running: boolean;
  total_in_feed: number;
  stats: RealtimeStats;
  tokens: DetectedToken[];
}

function scoreColor(score: number): string {
  if (score >= 70) return 'text-green-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-red-400';
}

function scoreBg(score: number): string {
  if (score >= 70) return 'bg-green-500/20';
  if (score >= 40) return 'bg-yellow-500/20';
  return 'bg-red-500/20';
}

function timeAgo(isoStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

export function RealtimeTokenFeed() {
  const [feed, setFeed] = useState<FeedResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [lifecycleAddress, setLifecycleAddress] = useState<string | null>(null);

  const fetchFeed = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/ingest/realtime/feed?limit=50`);
      if (res.ok) {
        setFeed(await res.json());
      }
    } catch {
      // Silent fail — feed is non-critical
    }
  }, []);

  // Poll feed — 5s when running, 60s when stopped
  const isRunning = feed?.running ?? false;
  useEffect(() => {
    fetchFeed();
    const interval = setInterval(fetchFeed, isRunning ? 5000 : 60000);
    return () => clearInterval(interval);
  }, [fetchFeed, isRunning]);


  const toggleListener = async () => {
    setToggling(true);
    try {
      const endpoint = feed?.running
        ? `${API_BASE_URL}/api/ingest/realtime/stop`
        : `${API_BASE_URL}/api/ingest/realtime/start`;
      const res = await fetch(endpoint, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        toast.success(
          feed?.running
            ? 'Real-time detection stopped'
            : 'Real-time detection started'
        );
        window.dispatchEvent(new Event('meridinate:settings-changed'));
        fetchFeed();
      }
    } catch {
      toast.error('Failed to toggle real-time detection');
    } finally {
      setToggling(false);
    }
  };

  const stats = feed?.stats;
  const tokens = feed?.tokens ?? [];

  return (
    <TooltipProvider delayDuration={200}>
      <div className={cn(
        'rounded-lg border transition-colors',
        isRunning ? 'border-red-500/50 shadow-[0_0_10px_rgba(239,68,68,0.1)]' : ''
      )}>
        {/* Header */}
        <div className={cn(
          'flex items-center justify-between border-b px-4 py-2.5',
          isRunning ? 'border-red-500/30' : ''
        )}>
          <div className='flex items-center gap-3'>
            <div className='flex items-center gap-2'>
              <span className={cn(
                'h-2 w-2 rounded-full',
                isRunning ? 'bg-red-500 animate-pulse' : 'bg-muted-foreground/30'
              )} />
              <span className='text-sm font-semibold'>Real-Time Token Feed</span>
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className='text-muted-foreground text-[10px] cursor-help border-b border-dotted border-muted-foreground/30'>
                  {isRunning
                    ? 'Streaming PumpFun creations — showing noteworthy tokens only'
                    : 'Paused — toggle to start real-time detection'}
                </span>
              </TooltipTrigger>
              <TooltipContent side='bottom' className='max-w-sm'>
                <div className='space-y-2 text-xs'>
                  <p className='font-medium'>What makes a token &quot;noteworthy&quot;?</p>
                  <p className='text-muted-foreground'>
                    A token appears here if ANY of these are true:
                  </p>
                  <ul className='text-muted-foreground space-y-1 list-disc pl-4'>
                    <li>Deployer has launched other tokens in our database (known deployer)</li>
                    <li>Deployer has wallet tags (Deployer, Serial Deployer, Winning/Rug Deployer, etc.)</li>
                    <li>Conviction score ≥ 65 (requires known deployer with positive history)</li>
                    <li>Known bad actor (shown as REJECTED)</li>
                  </ul>
                  <p className='text-muted-foreground'>
                    Unknown deployers (no history in our system) are silently skipped.
                    As you analyze more tokens via DexScreener, your deployer database grows
                    and more tokens become visible here.
                  </p>
                  <div className='border-t border-border pt-1.5'>
                    <p className='font-medium'>After detection (watch window):</p>
                    <p className='text-muted-foreground'>
                      Each token is monitored for {'{'}settings watch window{'}'} seconds.
                      Crime coin analysis runs on early buy patterns.
                      At window close, DexScreener MC is checked against your minimum threshold.
                      Final status: HIGH CONVICTION (organic + MC above threshold),
                      WEAK (organic but low MC), WATCHING (mixed signals), or REJECTED (crime pattern).
                    </p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </div>
          <div className='flex items-center gap-3'>
            {stats && isRunning && (
              <div className='flex items-center gap-3 text-[10px] text-muted-foreground'>
                <span>{stats.total_detected} scanned</span>
                <span>{stats.feed_size} noteworthy</span>
                <span className='text-green-400'>{stats.total_high_conviction} high conviction</span>
                <span className='text-red-400'>{stats.total_rejected} rejected</span>
                {(stats as any).total_crime_coins > 0 && (
                  <span className='text-orange-400'>{(stats as any).total_crime_coins} crime coins</span>
                )}
              </div>
            )}
            <Button
              variant='outline'
              size='sm'
              className='h-7 text-xs'
              onClick={() => setHistoryOpen(true)}
            >
              History
            </Button>
            <Button
              variant={isRunning ? 'destructive' : 'outline'}
              size='sm'
              className={cn(
                'h-7 text-xs',
                isRunning && 'animate-pulse'
              )}
              onClick={toggleListener}
              disabled={toggling}
            >
              {toggling ? '...' : isRunning ? '● LIVE — Stop' : '⚡ Start Real-Time'}
            </Button>
          </div>
        </div>

        {/* Feed Content */}
        {isRunning && tokens.length > 0 && (
          <div className='max-h-[300px] overflow-y-auto'>
            {tokens.map((token) => (
              <div
                key={token.token_address}
                className={cn(
                  'flex items-center gap-3 border-b px-4 py-2 hover:bg-blue-500/10 transition-colors cursor-pointer',
                  token.status === 'rejected' && 'opacity-40'
                )}
                onClick={() => setLifecycleAddress(token.token_address)}
              >
                {/* Score Badge */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className={cn(
                      'flex h-10 w-14 shrink-0 items-center justify-center rounded-lg text-sm font-bold',
                      scoreBg(token.conviction_score),
                      scoreColor(token.conviction_score)
                    )}>
                      {token.conviction_score}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent side='right' className='max-w-xs'>
                    <div className='space-y-1 text-xs'>
                      <div className='flex justify-between gap-4'>
                        <span>Deployer Score</span>
                        <span>{token.deployer_score}/40</span>
                      </div>
                      <div className='flex justify-between gap-4'>
                        <span>Safety Score</span>
                        <span>{token.safety_score}/30</span>
                      </div>
                      <div className='flex justify-between gap-4'>
                        <span>Social Proof</span>
                        <span>{token.social_proof_score}/30</span>
                      </div>
                    </div>
                  </TooltipContent>
                </Tooltip>

                {/* Token Info */}
                <div className='min-w-0 flex-1'>
                  <div className='flex items-center gap-2'>
                    <span className='text-sm font-medium truncate'>
                      {token.token_symbol || token.token_name || token.token_address.slice(0, 12) + '...'}
                    </span>
                    <span className='text-muted-foreground text-[10px]'>
                      {timeAgo(token.detected_at)}
                    </span>
                    {token.status === 'rejected' && (
                      <span className='rounded bg-red-500/20 px-1.5 py-0.5 text-[9px] text-red-400'>
                        REJECTED
                      </span>
                    )}
                    {token.status === 'high_conviction' && (
                      <span className='rounded bg-green-500/20 px-1.5 py-0.5 text-[9px] text-green-400'>
                        HIGH CONVICTION
                      </span>
                    )}
                    {token.status === 'weak' && (
                      <span className='rounded bg-zinc-500/20 px-1.5 py-0.5 text-[9px] text-zinc-400'>
                        WEAK
                      </span>
                    )}
                    {token.mc_at_30s > 0 && (
                      <span className='text-muted-foreground text-[9px]'>
                        MC: ${token.mc_at_30s >= 1000 ? `${(token.mc_at_30s / 1000).toFixed(1)}k` : token.mc_at_30s.toFixed(0)}
                      </span>
                    )}
                  </div>
                  <div className='flex items-center gap-2 text-[10px] text-muted-foreground'>
                    <TokenAddressCell address={token.token_address} compact showTwitter={false} />
                  </div>
                </div>

                {/* Deployer Info */}
                <div className='shrink-0 text-right'>
                  <div className='text-[10px]'>
                    {token.deployer_address ? (
                      <span className='font-mono text-muted-foreground'>
                        Deployer: {token.deployer_address.slice(0, 8)}...
                      </span>
                    ) : (
                      <span className='text-muted-foreground'>Unknown deployer</span>
                    )}
                  </div>
                  <div className='flex items-center justify-end gap-1.5 text-[10px]'>
                    {token.deployer_token_count > 0 && (
                      <span className='text-muted-foreground'>
                        {token.deployer_token_count} tokens
                      </span>
                    )}
                    {token.deployer_win_rate !== null && (
                      <span className={token.deployer_win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                        {(token.deployer_win_rate * 100).toFixed(0)}% win rate
                      </span>
                    )}
                    {token.initial_sol > 0 && (
                      <span className='text-muted-foreground'>
                        {token.initial_sol.toFixed(2)} SOL
                      </span>
                    )}
                  </div>
                  {token.deployer_tags.length > 0 && (
                    <div className='flex justify-end gap-1 mt-0.5'>
                      {token.deployer_tags.slice(0, 3).map((tag) => (
                        <span
                          key={tag}
                          className={cn(
                            'rounded px-1 py-0.5 text-[8px]',
                            tag.includes('Rug') ? 'bg-red-500/20 text-red-400' :
                            tag.includes('Winning') ? 'bg-green-500/20 text-green-400' :
                            tag.includes('Serial') ? 'bg-fuchsia-500/20 text-fuchsia-400' :
                            'bg-purple-500/20 text-purple-400'
                          )}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Crime coin indicators + rejection reason */}
                <div className='flex flex-col items-end gap-0.5 shrink-0'>
                  {token.watch_window_complete && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className={cn(
                          'rounded px-1.5 py-0.5 text-[9px] font-medium',
                          token.crime_risk_score >= 70 ? 'bg-orange-500/20 text-orange-400' :
                          token.crime_risk_score < 30 ? 'bg-green-500/20 text-green-400' :
                          'bg-yellow-500/20 text-yellow-400'
                        )}>
                          {token.crime_risk_score >= 70 ? '🚨 CRIME' :
                           token.crime_risk_score < 30 ? '✅ ORGANIC' :
                           '⚠️ UNCERTAIN'} {token.crime_risk_score}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side='left' className='max-w-xs'>
                        <div className='space-y-1 text-xs'>
                          <p className='font-medium'>Crime Coin Analysis (60s window)</p>
                          <div className='space-y-0.5 text-muted-foreground'>
                            <div>Buys in first 3 blocks: {token.buys_in_first_3_blocks}</div>
                            <div>Fresh buyer %: {token.fresh_buyer_pct.toFixed(0)}%</div>
                            <div>Buyers sharing funder: {token.buyers_sharing_funder}</div>
                            <div>Deployer linked to buyer: {token.deployer_linked_to_buyer ? 'Yes ⚠️' : 'No'}</div>
                            <div>Buy uniformity: {token.buy_amount_uniformity < 0.1 ? 'Very uniform ⚠️' : 'Varied'}</div>
                            <div>Total buyers (60s): {token.total_buyers}</div>
                            {token.smart_wallets_buying > 0 && (
                              <div className='text-green-400'>Smart wallets buying: {token.smart_wallets_buying}</div>
                            )}
                          </div>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  )}
                  {!token.watch_window_complete && token.status !== 'rejected' && (
                    <span className='text-[9px] text-muted-foreground animate-pulse'>
                      analyzing...
                    </span>
                  )}
                  {token.rejection_reason && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className='text-red-400 text-[10px] cursor-help'>Why?</span>
                      </TooltipTrigger>
                      <TooltipContent>{token.rejection_reason}</TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty states */}
        {isRunning && tokens.length === 0 && (
          <div className='py-8 text-center text-muted-foreground text-sm'>
            Scanning all new PumpFun tokens... Waiting for one with a known deployer or notable signal.
            <br />
            <span className='text-[10px]'>Most tokens are filtered out. Only noteworthy ones appear here.</span>
          </div>
        )}
        {!isRunning && (
          <div className='py-6 text-center text-muted-foreground text-sm'>
            Real-time detection is paused. Click &quot;Start Real-Time&quot; to begin.
          </div>
        )}
      </div>
      <RealtimeHistoryPanel open={historyOpen} onClose={() => setHistoryOpen(false)} />
      <LifecyclePanel
        open={!!lifecycleAddress}
        onClose={() => setLifecycleAddress(null)}
        tokenAddress={lifecycleAddress}
      />
    </TooltipProvider>
  );
}
