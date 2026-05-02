'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/lib/api';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { StatusBar } from '@/components/status-bar';
import { Button } from '@/components/ui/button';
import { TokenAddressCell } from '@/components/token-address-cell';
import { toast } from 'sonner';
import { Search, X } from 'lucide-react';
import { StarButton } from '@/components/star-button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

interface TokenScore {
  id: number;
  token_address: string;
  token_name: string | null;
  token_symbol: string | null;
  dex_id: string | null;
  is_cashback: boolean | null;
  market_cap_usd: number | null;
  market_cap_usd_current: number | null;
  market_cap_ath: number | null;
  liquidity_usd: number | null;
  analysis_timestamp: string | null;
  score_momentum: number | null;
  score_smart_money: number | null;
  score_risk: number | null;
  score_composite: number | null;
  mint_authority_revoked: boolean | null;
  freeze_authority_active: boolean | null;
  holder_top1_pct: number | null;
  holder_top10_pct: number | null;
  holder_count_latest: number | null;
  wallets_found: number;
  verdict: string | null;
  win_multiplier: string | null;
  loss_tier: string | null;
  score_updated_at: string | null;
  holder_velocity: number | null;
  mc_volatility: number | null;
  mc_recovery_count: number | null;
  smart_money_flow: string | null;
  deployer_is_top_holder: boolean | null;
  deployer_win_rate: number | null;
  deployer_tokens_deployed: number;
  fresh_wallet_pct: number | null;
  fresh_at_deploy_count: number | null;
  fresh_at_deploy_total: number | null;
  controlled_supply_score: number | null;
  fresh_supply_pct: number | null;
  bundle_cluster_count: number | null;
  bundle_cluster_size: number | null;
  stealth_holder_count: number | null;
  stealth_holder_pct: number | null;
  has_meteora_pool: boolean | null;
  meteora_pool_address: string | null;
  meteora_creator_linked: boolean | null;
  meteora_link_type: string | null;
  hours_since_ath: number | null;
  aggregate_realized_pnl: number;
  real_pnl_wallets: number;
  market_cap_usd_previous: number | null;
  credits_used: number | null;
  last_analysis_credits: number | null;
  mc_direction: string;
  mc_change_pct: number;
  meteora_lp_activity_json: string | null;
  clobr_score: number | null;
  rug_label: string | null;
  rug_score: number | null;
}

interface LeaderboardResponse {
  tokens: TokenScore[];
  total: number;
  is_search: boolean;
  weights: { momentum: number; smart_money: number; risk: number };
}

// Score color helper
function scoreColor(score: number | null): string {
  if (score === null || score === undefined) return 'text-muted-foreground';
  if (score >= 70) return 'text-green-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-red-400';
}

// CLOBr score color helper (different thresholds from regular scores)
function clobrColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-muted-foreground';
  if (score >= 60) return 'text-green-400';
  if (score >= 30) return 'text-yellow-400';
  return 'text-red-400';
}

// Rug score color helper (inverted: higher = worse)
function rugScoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-muted-foreground';
  if (score >= 60) return 'text-red-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-green-400';
}

function scoreBg(score: number | null): string {
  if (score === null || score === undefined) return 'bg-muted';
  if (score >= 70) return 'bg-green-500/20';
  if (score >= 40) return 'bg-yellow-500/20';
  return 'bg-red-500/20';
}

// Sortable header button
interface SortHeaderProps {
  field: string;
  sortBy: string;
  sortDir: 'asc' | 'desc';
  onSort: (field: string) => void;
  children: React.ReactNode;
}

function SortHeader({ field, sortBy, sortDir, onSort, children }: SortHeaderProps) {
  return (
    <button onClick={() => onSort(field)} className='hover:text-primary inline-flex items-center gap-1 transition-colors'>
      {children}
      {sortBy === field && <span className='text-[10px]'>{sortDir === 'asc' ? '▲' : '▼'}</span>}
    </button>
  );
}

// Tooltip wrapper for headers
function HeaderTooltip({ label, tip }: { label: string; tip: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className='cursor-help border-b border-dotted border-current'>{label}</span>
        </TooltipTrigger>
        <TooltipContent className='max-w-[250px]'>
          <p className='text-xs'>{tip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

const RUG_LABEL_OPTIONS = [
  { label: 'FAKE', value: 'fake' as const, cls: 'bg-red-500/20 text-red-400 hover:bg-red-500/30' },
  { label: 'REAL', value: 'real' as const, cls: 'bg-green-500/20 text-green-400 hover:bg-green-500/30' },
  { label: 'UNSURE', value: 'unsure' as const, cls: 'bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30' },
  { label: 'Clear', value: null, cls: 'text-muted-foreground hover:bg-muted' },
];

function RugLabelCell({ token, onUpdate }: { token: { id: number; rug_label: string | null }; onUpdate: (val: string | null) => void }) {
  const [open, setOpen] = useState(false);

  const handleSelect = async (value: string | null) => {
    setOpen(false);
    try {
      const res = await fetch(`${API_BASE_URL}/api/tokens/${token.id}/rug-label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: value }),
      });
      if (res.ok) {
        onUpdate(value);
        toast.success(`Label ${value ? `set to ${value}` : 'cleared'}`, { duration: 1500 });
      } else { toast.error('Failed to update label'); }
    } catch { toast.error('Failed to update label'); }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={`inline-block rounded text-[9px] px-1.5 py-0.5 font-medium transition-colors ${
            token.rug_label === 'fake' ? 'bg-red-500/20 text-red-400' :
            token.rug_label === 'real' ? 'bg-green-500/20 text-green-400' :
            token.rug_label === 'unsure' ? 'bg-yellow-500/20 text-yellow-400' :
            'text-muted-foreground hover:bg-muted'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {token.rug_label === 'fake' ? 'FAKE' :
           token.rug_label === 'real' ? 'REAL' :
           token.rug_label === 'unsure' ? 'UNSURE' : '—'}
        </button>
      </PopoverTrigger>
      <PopoverContent className='w-auto p-1.5 flex flex-col gap-1' align='center' side='left'
        onClick={(e) => e.stopPropagation()}>
        {RUG_LABEL_OPTIONS.map((opt) => (
          <button
            key={opt.label}
            className={`rounded px-3 py-1 text-[10px] font-medium transition-colors ${opt.cls}`}
            onClick={() => handleSelect(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

export default function TokenLeaderboardPage() {
  const router = useRouter();
  const statusBarData = useStatusBarData();
  const { openTIP } = useTokenIntelligence();
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [sortBy, setSortBy] = useState('score_composite');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Search + pagination
  const [searchInput, setSearchInput] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [page, setPage] = useState(0);
  const perPage = 100;
  const [statusFilter, setStatusFilter] = useState('');

  // Adjustable weights
  const [wMomentum, setWMomentum] = useState(0.4);
  const [wSmart, setWSmart] = useState(0.35);
  const [wRisk, setWRisk] = useState(0.25);
  const [showWeights, setShowWeights] = useState(false);

  // Debounce search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setActiveSearch(searchInput.trim());
      setPage(0);
    }, 400);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [searchInput]);

  const fetchData = useCallback(async (showToast = false) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: String(perPage),
        offset: String(page * perPage),
        w_momentum: String(wMomentum),
        w_smart: String(wSmart),
        w_risk: String(wRisk),
      });
      if (activeSearch) params.set('search', activeSearch);
      if (statusFilter) params.set('status', statusFilter);

      const res = await fetch(`${API_BASE_URL}/api/token-leaderboard?${params}`);
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLastRefreshedAt(new Date());
        if (showToast) {
          toast.success('Token leaderboard refreshed', {
            description: `${json.tokens?.length ?? 0} tokens loaded`,
            duration: 2000,
          });
        }
      } else if (showToast) {
        toast.error('Failed to refresh leaderboard');
      }
    } catch {
      console.error('Failed to fetch token leaderboard');
      if (showToast) toast.error('Failed to refresh leaderboard');
    } finally {
      setLoading(false);
    }
  }, [sortBy, sortDir, wMomentum, wSmart, wRisk, activeSearch, page, statusFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh when MC tracker or scan completes
  useEffect(() => {
    const handler = () => fetchData();
    window.addEventListener('meridinate:mc-refresh-complete', handler);
    window.addEventListener('meridinate:scan-complete', handler);
    return () => {
      window.removeEventListener('meridinate:mc-refresh-complete', handler);
      window.removeEventListener('meridinate:scan-complete', handler);
    };
  }, [fetchData]);

  const handleSort = (field: string) => {
    if (sortBy === field) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortBy(field); setSortDir('desc'); }
  };

  const formatMC = (v: number | null) => {
    if (!v) return '—';
    if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
    return `$${v.toFixed(0)}`;
  };

  return (
    <TooltipProvider>
      <div className='w-full space-y-4 px-4 py-6'>
        {/* Header */}
        <div className='flex items-center justify-between'>
          <div>
            <h1 className='text-2xl font-bold'>Token Leaderboard</h1>
            <p className='text-muted-foreground text-sm'>
              {data?.is_search
                ? `${data.total} tokens matching "${activeSearch}"`
                : `Showing ${Math.min(page * perPage + 1, data?.total ?? 0)}–${Math.min((page + 1) * perPage, data?.total ?? 0)} of ${data?.total ?? '...'} tokens`}
              {lastRefreshedAt && (
                <span className='ml-2 text-[10px] opacity-60'>
                  · {lastRefreshedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              )}
            </p>
          </div>
          <div className='flex items-center gap-2'>
            <Button variant='outline' size='sm' onClick={() => setShowWeights(!showWeights)}>
              {showWeights ? 'Hide Weights' : 'Adjust Weights'}
            </Button>
            <Button variant='outline' size='sm' onClick={() => fetchData(true)} disabled={loading}>
              Refresh
            </Button>
          </div>
        </div>

        {/* Weight Adjusters */}
        {showWeights && (
          <div className='rounded-lg border p-4'>
            <h3 className='mb-3 text-sm font-semibold'>Score Weights</h3>
            <p className='text-muted-foreground mb-3 text-xs'>
              Adjust how much each factor contributes to the composite score. Weights should sum to 1.0.
            </p>
            <div className='grid grid-cols-3 gap-4'>
              <div className='space-y-1'>
                <label className='text-xs font-medium'>Momentum ({(wMomentum * 100).toFixed(0)}%)</label>
                <input type='range' min='0' max='100' value={wMomentum * 100}
                  onChange={(e) => setWMomentum(parseInt(e.target.value) / 100)}
                  className='w-full' />
                <p className='text-muted-foreground text-[10px]'>Current price performance & trajectory</p>
              </div>
              <div className='space-y-1'>
                <label className='text-xs font-medium'>Smart Money ({(wSmart * 100).toFixed(0)}%)</label>
                <input type='range' min='0' max='100' value={wSmart * 100}
                  onChange={(e) => setWSmart(parseInt(e.target.value) / 100)}
                  className='w-full' />
                <p className='text-muted-foreground text-[10px]'>Quality of early bidder wallets</p>
              </div>
              <div className='space-y-1'>
                <label className='text-xs font-medium'>Risk ({(wRisk * 100).toFixed(0)}%)</label>
                <input type='range' min='0' max='100' value={wRisk * 100}
                  onChange={(e) => setWRisk(parseInt(e.target.value) / 100)}
                  className='w-full' />
                <p className='text-muted-foreground text-[10px]'>Token safety (mint auth, holder concentration)</p>
              </div>
            </div>
            <div className='mt-2 text-right'>
              <span className={`text-xs ${Math.abs(wMomentum + wSmart + wRisk - 1) < 0.01 ? 'text-green-400' : 'text-red-400'}`}>
                Total: {((wMomentum + wSmart + wRisk) * 100).toFixed(0)}%
                {Math.abs(wMomentum + wSmart + wRisk - 1) >= 0.01 && ' (should be 100%)'}
              </span>
            </div>
          </div>
        )}

        {/* Search + Status Filter */}
        <div className='flex items-center gap-3'>
          <div className='relative flex-1 max-w-md'>
            <Search className='absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground' />
            <input
              type='text'
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder='Search by token address, name, or symbol...'
              className='bg-background focus:ring-primary h-9 w-full rounded-md border pl-9 pr-8 text-sm focus:outline-none focus:ring-2'
            />
            {searchInput && (
              <button onClick={() => { setSearchInput(''); setActiveSearch(''); }}
                className='absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground'>
                <X className='h-3.5 w-3.5' />
              </button>
            )}
          </div>
          <Button
            variant={statusFilter === 'polled' ? 'default' : 'outline'}
            size='sm'
            onClick={() => { setStatusFilter(statusFilter === 'polled' ? '' : 'polled'); setPage(0); }}
          >
            {statusFilter === 'polled' ? 'Showing Active' : 'Active Only'}
          </Button>
        </div>

        {/* Table */}
        <div className='rounded-lg border'>

          {/* Pagination — Top */}
          {(data?.total ?? 0) > perPage && (
            <div className='flex items-center justify-between border-b px-4 py-2'>
              <p className='text-[11px] text-muted-foreground'>
                Page {page + 1} of {Math.ceil((data?.total ?? 0) / perPage)} · {data?.total} tokens
              </p>
              <div className='flex items-center gap-2'>
                <Button variant='outline' size='sm' className='h-7 text-xs' disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button variant='outline' size='sm' className='h-7 text-xs' disabled={(page + 1) * perPage >= (data?.total ?? 0)} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          )}
          <div className='overflow-x-auto'>
            <table className='w-full text-sm'>
              <thead className='bg-muted/50'>
                <tr className='border-b'>
                  <th className='px-2 py-2 text-left text-xs font-medium w-8'>#</th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>Token</th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>Address</th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='score_composite'>
                      <HeaderTooltip label='Score' tip='Composite score: weighted average of Momentum, Smart Money, and inverted Risk. Higher = better overall opportunity.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='score_momentum'>
                      <HeaderTooltip label='Momentum' tip='How well is the token performing right now? Based on MC growth since scan, ATH proximity, and liquidity health. 0-100.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='score_smart_money'>
                      <HeaderTooltip label='Smart $' tip='How many "smart money" wallets bought this token early? Counts wallets tagged as Consistent Winners, Snipers, Diversified, High SOL Balance. 0-100.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='score_risk'>
                      <HeaderTooltip label='Risk' tip='How risky is this token? Factors: mint authority (can creator print tokens?), freeze authority, holder concentration, liquidity ratio. 0-100, lower = safer.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='clobr_score'>
                      <HeaderTooltip label='CLOBr' tip='Central Limit Order Book readiness score (0-100). Measures how ready a token is for CLOB trading based on liquidity depth, spread, and order flow patterns.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='market_cap_usd_current'>
                      <HeaderTooltip label='MC' tip='Current market cap from latest DexScreener refresh.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='ATH' tip='All-time high market cap. Estimated from 5-minute price changes and PumpFun data.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='liquidity_usd'>
                      <HeaderTooltip label='Liquidity' tip='Total USD liquidity in the primary trading pool.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-center text-xs font-medium'>
                    <HeaderTooltip label='Wallets' tip='Number of early buyer wallets found during analysis.' />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>
                    <HeaderTooltip label='Safety' tip='Mint Authority: can the creator print more tokens? Freeze Authority: can the creator freeze transfers? Revoked mint + no freeze = safest.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='Top Holder' tip='Percentage of total supply held by the largest single holder. Lower = more distributed = healthier.' />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>
                    <HeaderTooltip label='Fees' tip='PumpFun fee type. Cashback = fees go to traders. Creator Fee = fees go to developer.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='Deployer' tip='Deployer win rate: what % of this deployer&#39;s previous tokens got verified-win verdicts. Higher = more trustworthy deployer.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='Fresh %' tip='Percentage of early buyers that were fresh wallets (created within 7 days of buying). Higher = more suspicious.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='Fresh@Deploy' tip='Fresh wallets that entered within 60 seconds of token creation. Format: fresh/total early entries. Strong rug signal when high.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='Supply Ctrl' tip='Controlled Supply Score (0-100). Combines: fresh wallets near deploy, cluster overlap with fresh wallets, and % of supply held by fresh wallets. Higher = more likely coordinated supply control.' />
                  </th>
                  <th className='px-2 py-2 text-center text-xs font-medium'>
                    <HeaderTooltip label='Bundled' tip='Same-second buy clustering. Format: clusters/largest. First number = how many times 3+ wallets bought at the exact same second. Second number = most wallets in a single cluster. Example: 11/6 means 11 separate cluster events, worst one had 6 wallets buying simultaneously.' />
                  </th>
                  <th className='px-2 py-2 text-center text-xs font-medium'>
                    <HeaderTooltip label='Stealth' tip='Stealth holders: top holders that made suspiciously small buys. Holds 1%+ supply but spent &lt;$200 buying, or holds 10x more than their buy amount suggests. Indicates hidden supply control.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='Since ATH' tip='Time since the token&#39;s all-time high market cap. At ATH = 0h. Tokens past their peak show how long ago they peaked.' />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <HeaderTooltip label='PnL' tip='Aggregate realized PnL from ALL wallets with real swap data on this token. Based on actual Helius transaction data, not estimates.' />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>
                    <HeaderTooltip label='Signals' tip='Analytics signals: holder velocity (concentration change), MC volatility, smart money flow direction, deployer holding status.' />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>Verdict</th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader sortBy={sortBy} sortDir={sortDir} onSort={handleSort} field='rug_score'>
                      <HeaderTooltip label='Rug' tip='Rug probability score (0-100). Based on volume/liquidity ratio, transaction density, holder patterns, and other on-chain signals. Higher = more likely rug.' />
                    </SortHeader>
                  </th>
                  <th className='px-2 py-2 text-center text-xs font-medium'>Label</th>
                </tr>
              </thead>
              <tbody>
                {loading && !data ? (
                  <tr><td colSpan={27} className='text-muted-foreground py-12 text-center'>Loading...</td></tr>
                ) : !data?.tokens?.length ? (
                  <tr><td colSpan={27} className='text-muted-foreground py-12 text-center'>
                    No scored tokens yet. Scores compute automatically during MC refresh cycles.
                  </td></tr>
                ) : (
                  data.tokens.map((token, i) => (
                    <tr key={token.id}
                      className='hover:bg-blue-500/10 cursor-pointer border-b'
                      onClick={() => openTIP(token)}
                    >
                      <td className='px-2 py-2 text-xs text-muted-foreground'>{page * perPage + i + 1}</td>
                      <td className='px-2 py-2'>
                        <div className='flex items-center gap-1'>
                          <StarButton type='token' address={token.token_address} />
                          <span className='font-medium text-sm'>{token.token_symbol || token.token_name || '—'}</span>
                        </div>
                        <div className='text-muted-foreground text-[10px]'>
                          {token.token_name}
                          {token.analysis_timestamp && (
                            <span className='ml-1.5 opacity-60'>
                              · {new Date(token.analysis_timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}{' '}
                              {new Date(token.analysis_timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                              {' '}({(() => {
                                const age = (Date.now() - new Date(token.analysis_timestamp).getTime()) / 3600000;
                                if (age < 1) return `${Math.round(age * 60)}m ago`;
                                if (age < 24) return `${Math.round(age)}h ago`;
                                if (age < 168) return `${Math.round(age / 24)}d ago`;
                                return `${Math.round(age / 168)}w ago`;
                              })()})
                            </span>
                          )}
                        </div>
                      </td>
                      <td className='px-2 py-2'>
                        <TokenAddressCell address={token.token_address} compact showTwitter={false} />
                      </td>
                      <td className='px-2 py-2 text-right'>
                        <span className={`rounded px-2 py-0.5 text-sm font-bold ${scoreBg(token.score_composite)} ${scoreColor(token.score_composite)}`}>
                          {token.score_composite?.toFixed(0) ?? '—'}
                        </span>
                      </td>
                      <td className={`px-2 py-2 text-right font-mono text-xs ${scoreColor(token.score_momentum)}`}>
                        {token.score_momentum?.toFixed(0) ?? '—'}
                      </td>
                      <td className={`px-2 py-2 text-right font-mono text-xs ${scoreColor(token.score_smart_money)}`}>
                        {token.score_smart_money?.toFixed(0) ?? '—'}
                      </td>
                      <td className={`px-2 py-2 text-right font-mono text-xs ${token.score_risk !== null && token.score_risk !== undefined ? (token.score_risk <= 30 ? 'text-green-400' : token.score_risk <= 60 ? 'text-yellow-400' : 'text-red-400') : 'text-muted-foreground'}`}>
                        {token.score_risk?.toFixed(0) ?? '—'}
                      </td>
                      <td className={`px-2 py-2 text-right font-mono text-xs ${clobrColor(token.clobr_score)}`}>
                        {token.clobr_score != null ? token.clobr_score : '—'}
                      </td>
                      <td className='px-2 py-2 text-right text-xs'>
                        <div>
                          <span className='font-medium'>{formatMC(token.market_cap_usd_current)}</span>
                          {token.mc_direction === 'up' && <span className='text-green-400 ml-0.5'>▲</span>}
                          {token.mc_direction === 'down' && <span className='text-red-400 ml-0.5'>▼</span>}
                          {token.mc_change_pct !== 0 && (
                            <span className={`ml-0.5 text-[9px] ${token.mc_change_pct > 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {token.mc_change_pct > 0 ? '+' : ''}{token.mc_change_pct}%
                            </span>
                          )}
                        </div>
                        {token.market_cap_usd && token.market_cap_usd !== token.market_cap_usd_current && (
                          <div className='text-[9px] text-muted-foreground'>at scan: {formatMC(token.market_cap_usd)}</div>
                        )}
                      </td>
                      <td className='px-2 py-2 text-right text-xs'>{formatMC(token.market_cap_ath)}</td>
                      <td className='px-2 py-2 text-right text-xs'>{formatMC(token.liquidity_usd)}</td>
                      <td className='px-2 py-2 text-center text-xs'>{token.wallets_found}</td>
                      <td className='px-2 py-2 text-xs'>
                        <div className='flex gap-1'>
                          {token.mint_authority_revoked === true && (
                            <span className='rounded bg-green-500/20 px-1 py-0.5 text-[9px] text-green-400'>Mint Revoked</span>
                          )}
                          {token.mint_authority_revoked === false && (
                            <span className='rounded bg-red-500/20 px-1 py-0.5 text-[9px] text-red-400'>Mint Active</span>
                          )}
                          {token.freeze_authority_active && (
                            <span className='rounded bg-red-500/20 px-1 py-0.5 text-[9px] text-red-400'>Freeze</span>
                          )}
                        </div>
                      </td>
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.holder_top1_pct ? `${token.holder_top1_pct.toFixed(1)}%` : '—'}
                      </td>
                      <td className='px-2 py-2 text-xs'>
                        {token.is_cashback === true ? (
                          <span className='rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-400'>Cashback</span>
                        ) : token.is_cashback === false ? (
                          <span className='rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-400'>Creator</span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Deployer Win Rate */}
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.deployer_win_rate !== null ? (
                          <span className={token.deployer_win_rate >= 50 ? 'text-green-400' : token.deployer_win_rate > 0 ? 'text-yellow-400' : 'text-red-400'}>
                            {token.deployer_win_rate}%
                            <span className='text-muted-foreground ml-0.5 text-[9px]'>({token.deployer_tokens_deployed})</span>
                          </span>
                        ) : <span className='text-muted-foreground text-[10px]'>New</span>}
                      </td>
                      {/* Fresh Wallet % */}
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.fresh_wallet_pct != null && token.fresh_wallet_pct > 0 ? (
                          <span className={token.fresh_wallet_pct > 50 ? 'text-red-400' : token.fresh_wallet_pct > 30 ? 'text-yellow-400' : 'text-muted-foreground'}>
                            {token.fresh_wallet_pct.toFixed(0)}%
                          </span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Fresh at Deploy */}
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.fresh_at_deploy_total != null && token.fresh_at_deploy_total > 0 ? (
                          <span className={
                            token.fresh_at_deploy_count != null && token.fresh_at_deploy_count > 0
                              ? (token.fresh_at_deploy_count / token.fresh_at_deploy_total > 0.5 ? 'text-red-400 font-medium' : 'text-orange-400')
                              : 'text-muted-foreground'
                          }>
                            {token.fresh_at_deploy_count ?? 0}/{token.fresh_at_deploy_total}
                          </span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Controlled Supply Score */}
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.controlled_supply_score != null && token.controlled_supply_score > 0 ? (
                          <span className={
                            token.controlled_supply_score >= 50 ? 'text-red-400 font-medium' :
                            token.controlled_supply_score >= 25 ? 'text-orange-400' :
                            'text-yellow-400'
                          }>
                            {token.controlled_supply_score.toFixed(0)}
                            {token.fresh_supply_pct != null && token.fresh_supply_pct > 0 && (
                              <span className='text-muted-foreground ml-0.5 text-[9px]'>({token.fresh_supply_pct.toFixed(0)}% supply)</span>
                            )}
                          </span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Bundle Clusters */}
                      <td className='px-2 py-2 text-center text-xs'>
                        {token.bundle_cluster_count != null && token.bundle_cluster_count > 0 ? (
                          <span className={
                            token.bundle_cluster_size != null && token.bundle_cluster_size >= 5 ? 'text-red-400 font-bold' :
                            'text-orange-400 font-medium'
                          }>
                            {token.bundle_cluster_count}/{token.bundle_cluster_size}
                          </span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Stealth Holders */}
                      <td className='px-2 py-2 text-center text-xs'>
                        {token.stealth_holder_count != null && token.stealth_holder_count > 0 ? (
                          <span className={
                            token.stealth_holder_pct != null && token.stealth_holder_pct >= 10 ? 'text-red-400 font-bold' :
                            'text-orange-400'
                          }>
                            {token.stealth_holder_count}
                            {token.stealth_holder_pct != null && token.stealth_holder_pct > 0 && (
                              <span className='text-muted-foreground ml-0.5 text-[9px]'>({token.stealth_holder_pct.toFixed(0)}%)</span>
                            )}
                          </span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Time Since ATH */}
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.hours_since_ath != null ? (
                          <span className={token.hours_since_ath < 1 ? 'text-green-400 font-medium' : token.hours_since_ath < 24 ? 'text-yellow-400' : 'text-muted-foreground'}>
                            {token.hours_since_ath < 1 ? 'At ATH' :
                             token.hours_since_ath < 24 ? `${token.hours_since_ath.toFixed(0)}h ago` :
                             `${(token.hours_since_ath / 24).toFixed(0)}d ago`}
                          </span>
                        ) : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Aggregate Real PnL */}
                      <td className='px-2 py-2 text-right text-xs'>
                        {token.real_pnl_wallets > 0 && token.aggregate_realized_pnl != null ? (
                          <span className={token.aggregate_realized_pnl > 0 ? 'text-green-400' : token.aggregate_realized_pnl < 0 ? 'text-red-400' : 'text-muted-foreground'}>
                            {token.aggregate_realized_pnl > 0 ? '+' : ''}${Math.abs(token.aggregate_realized_pnl) >= 1000
                              ? `${(token.aggregate_realized_pnl / 1000).toFixed(1)}k`
                              : token.aggregate_realized_pnl.toFixed(0)}
                            <span className='text-muted-foreground ml-0.5 text-[9px]'>({token.real_pnl_wallets} wallets)</span>
                          </span>
                        ) : <span className='text-muted-foreground text-[10px]'>No data</span>}
                      </td>
                      {/* Signals */}
                      <td className='px-2 py-2'>
                        <div className='flex flex-wrap gap-1'>
                          {token.holder_velocity != null && Math.abs(token.holder_velocity) > 3 && (
                            <span className={`rounded px-1 py-0.5 text-[9px] ${token.holder_velocity > 0 ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>
                              {token.holder_velocity > 0 ? '↑' : '↓'} Concentration
                            </span>
                          )}
                          {token.mc_volatility != null && token.mc_volatility > 40 && (
                            <span className='rounded bg-amber-500/20 px-1 py-0.5 text-[9px] text-amber-400'>
                              High Volatility
                            </span>
                          )}
                          {token.mc_recovery_count != null && token.mc_recovery_count > 0 && (
                            <span className='rounded bg-green-500/20 px-1 py-0.5 text-[9px] text-green-400'>
                              {token.mc_recovery_count}x Recovery
                            </span>
                          )}
                          {(() => {
                            if (!token.smart_money_flow) return null;
                            try {
                              const flow = typeof token.smart_money_flow === 'string' ? JSON.parse(token.smart_money_flow) : token.smart_money_flow;
                              if (flow.flow_direction === 'bullish') return <span className='rounded bg-green-500/20 px-1 py-0.5 text-[9px] text-green-400'>Smart Bullish</span>;
                              if (flow.flow_direction === 'bearish') return <span className='rounded bg-red-500/20 px-1 py-0.5 text-[9px] text-red-400'>Smart Bearish</span>;
                            } catch { /* ignore */ }
                            return null;
                          })()}
                          {token.deployer_is_top_holder === true && (
                            <span className='rounded bg-amber-500/20 px-1 py-0.5 text-[9px] text-amber-400'>
                              Deployer Holding
                            </span>
                          )}
                          {token.has_meteora_pool === true && (
                            <span className={`rounded px-1 py-0.5 text-[9px] font-medium ${
                              token.meteora_creator_linked
                                ? 'bg-red-600/20 text-red-400'
                                : 'bg-purple-500/20 text-purple-400'
                            }`}>
                              {token.meteora_creator_linked ? 'Meteora Stealth Sell' : 'Meteora LP'}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className='px-2 py-2 text-xs'>
                        {token.verdict === 'verified-win' ? (() => {
                          const mult = token.win_multiplier?.replace('win:', '').toUpperCase();
                          const multNum = parseInt(mult || '0');
                          const isBigWin = multNum >= 25;
                          return (
                            <span className={`inline-block rounded px-1.5 py-0.5 font-bold ${
                              isBigWin
                                ? 'animate-shimmer bg-[length:200%_100%] bg-gradient-to-r from-yellow-600/30 via-amber-300/50 to-yellow-600/30 text-yellow-200'
                                : multNum >= 10
                                  ? 'bg-amber-500/20 text-amber-400'
                                  : 'text-green-400'
                            }`}>
                              WIN{mult ? ` ${mult}` : ''}
                            </span>
                          );
                        })() : token.verdict === 'verified-loss' ? (() => {
                          const tier = token.loss_tier;
                          const label = tier === 'loss:rug' ? 'RUG PULL'
                            : tier === 'loss:90' ? 'LOSS 90%+'
                            : tier === 'loss:70' ? 'LOSS 70%+'
                            : tier === 'loss:dead' ? 'DEAD'
                            : tier === 'loss:stale' ? 'STALE'
                            : 'LOSS';
                          const color = tier === 'loss:rug' ? 'text-red-500 font-bold'
                            : tier === 'loss:dead' ? 'text-red-500'
                            : tier === 'loss:90' ? 'text-red-400'
                            : tier === 'loss:70' ? 'text-orange-400'
                            : tier === 'loss:stale' ? 'text-muted-foreground'
                            : 'text-red-400';
                          return <span className={`font-medium ${color}`}>{label}</span>;
                        })() : <span className='text-muted-foreground'>—</span>}
                      </td>
                      {/* Rug Score */}
                      <td className={`px-2 py-2 text-right font-mono text-xs ${rugScoreColor(token.rug_score)}`}>
                        {token.rug_score != null ? token.rug_score : '—'}
                      </td>
                      {/* Rug Label */}
                      <td className='px-2 py-2 text-center text-xs'>
                        <RugLabelCell token={token} onUpdate={(val) => {
                          token.rug_label = val;
                          setData(data ? { ...data, tokens: [...data.tokens] } : data);
                        }} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination — Bottom */}
          {(data?.total ?? 0) > perPage && (
            <div className='flex items-center justify-between border-t px-4 py-2'>
              <p className='text-[11px] text-muted-foreground'>
                Page {page + 1} of {Math.ceil((data?.total ?? 0) / perPage)}
              </p>
              <div className='flex items-center gap-2'>
                <Button variant='outline' size='sm' className='h-7 text-xs' disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button variant='outline' size='sm' className='h-7 text-xs' disabled={(page + 1) * perPage >= (data?.total ?? 0)} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      </div>
      <StatusBar
        tokensScanned={statusBarData.tokensScanned}
        tokensScannedToday={statusBarData.tokensScannedToday}
        latestAnalysis={statusBarData.latestAnalysis?.analysis_timestamp || null}
        latestTokenName={statusBarData.latestAnalysis?.token_name || null}
        latestWalletsFound={statusBarData.latestAnalysis?.wallets_found ?? null}
        latestApiCredits={statusBarData.latestAnalysis?.credits_used ?? null}
        totalApiCreditsToday={statusBarData.creditsUsedToday}
        recentOperations={statusBarData.recentOperations}
        onRefresh={statusBarData.refresh}
        lastUpdated={statusBarData.lastUpdated}
      />
    </TooltipProvider>
  );
}
