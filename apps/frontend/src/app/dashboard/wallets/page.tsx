'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import { API_BASE_URL, FunderCluster } from '@/lib/api';
import type { ClusterData } from '@/components/funding-tree-panel';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { Button } from '@/components/ui/button';
import { StatusBar } from '@/components/status-bar';
import { toast } from 'sonner';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { getTagStyle } from '@/lib/wallet-tags';
import { cn } from '@/lib/utils';
import { Search, X, SlidersHorizontal, ChevronDown, Star } from 'lucide-react';
import { StarButton } from '@/components/star-button';

const DeployerPanel = dynamic(
  () =>
    import('@/components/deployer-panel').then((mod) => ({
      default: mod.DeployerPanel
    })),
  { ssr: false }
);

const FundingTreePanel = dynamic(
  () =>
    import('@/components/funding-tree-panel').then((mod) => ({
      default: mod.FundingTreePanel
    })),
  { ssr: false }
);

// ============================================================================
// Types
// ============================================================================

interface WalletRow {
  wallet_address: string;
  rank: number;
  is_archive: boolean;
  total_pnl_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
  pnl_1d_usd: number;
  pnl_7d_usd: number;
  pnl_30d_usd: number;
  tokens_traded: number;
  tokens_won: number;
  tokens_lost: number;
  win_rate: number;
  best_trade_pnl: number;
  best_trade_token: string | null;
  worst_trade_pnl: number;
  worst_trade_token: string | null;
  tags: string[];
  wallet_balance_usd: number | null;
  avg_entry_seconds: number | null;
  wallet_created_at: string | null;
  avg_hold_hours_7d: number | null;
  tiers: Record<string, number>;
  tier_score: number;
  home_runs: number;
  rugs: number;
  // Funding-chain terminal — null until backfill runs.
  // terminal_name is the labeled CEX/protocol (e.g. "Coinbase 12") if known.
  // terminal_address is the deepest funder we reached (always populated post-trace).
  // terminal_type is "exchange", "protocol", or null/unknown.
  terminal_address: string | null;
  terminal_name: string | null;
  terminal_type: string | null;
}

interface LeaderboardResponse {
  wallets: WalletRow[];
  total: number;
  is_search: boolean;
}

type SortField =
  | 'total_pnl_usd'
  | 'realized_pnl_usd'
  | 'unrealized_pnl_usd'
  | 'pnl_1d_usd'
  | 'pnl_7d_usd'
  | 'pnl_30d_usd'
  | 'win_rate'
  | 'tokens_traded'
  | 'best_trade_pnl'
  | 'avg_entry_seconds'
  | 'wallet_balance_usd'
  | 'avg_hold_hours_7d'
  | 'tier_score';

// Most useful tags for filtering
const TAG_FILTER_OPTIONS = [
  'Consistent Winner', 'Consistent Loser', 'Sniper', 'Lightning Buyer',
  'High SOL Balance', 'Cluster', 'Insider', 'KOL', 'Watchlist',
  'Winning Deployer', 'Rug Deployer', 'Fresh at Entry (<24h)', 'Sniper Bot',
  'Automated (Nozomi)', 'Bundled (Jito)',
];

// Win/loss tier filter options (separate from wallet tags — these filter by token tier history)
const TIER_FILTER_OPTIONS = [
  'win:100x', 'win:50x', 'win:25x', 'win:10x', 'win:5x', 'win:3x',
  'loss:rug', 'loss:90', 'loss:70', 'loss:dead', 'loss:stale',
];

const TIER_DISPLAY: Record<string, { label: string; color: string }> = {
  'win:100x': { label: '100x', color: 'text-yellow-300' },
  'win:50x':  { label: '50x',  color: 'text-yellow-300' },
  'win:25x':  { label: '25x',  color: 'text-yellow-300' },
  'win:10x':  { label: '10x',  color: 'text-amber-400' },
  'win:5x':   { label: '5x',   color: 'text-green-400' },
  'win:3x':   { label: '3x',   color: 'text-green-500' },
  'loss:rug':   { label: 'RUG',   color: 'text-red-500' },
  'loss:90':    { label: '90%',   color: 'text-red-400' },
  'loss:70':    { label: '70%',   color: 'text-orange-400' },
  'loss:dead':  { label: 'DEAD',  color: 'text-red-500' },
  'loss:stale': { label: 'STALE', color: 'text-muted-foreground' },
};

function getTierStyle(tier: string): { bg: string; text: string } {
  if (tier === 'win:100x' || tier === 'win:50x') return { bg: 'bg-yellow-500/20', text: 'text-yellow-300' };
  if (tier === 'win:25x') return { bg: 'bg-yellow-500/20', text: 'text-yellow-300' };
  if (tier === 'win:10x') return { bg: 'bg-amber-500/20', text: 'text-amber-400' };
  if (tier === 'win:5x') return { bg: 'bg-green-500/20', text: 'text-green-400' };
  if (tier === 'win:3x') return { bg: 'bg-green-600/20', text: 'text-green-500' };
  if (tier === 'loss:rug') return { bg: 'bg-red-600/20', text: 'text-red-500' };
  if (tier === 'loss:90') return { bg: 'bg-red-500/20', text: 'text-red-400' };
  if (tier === 'loss:70') return { bg: 'bg-orange-500/20', text: 'text-orange-400' };
  if (tier === 'loss:dead') return { bg: 'bg-red-600/20', text: 'text-red-500' };
  if (tier === 'loss:stale') return { bg: 'bg-zinc-500/20', text: 'text-zinc-400' };
  return { bg: 'bg-muted', text: 'text-muted-foreground' };
}

// ============================================================================
// Helpers
// ============================================================================

function formatPnl(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const sign = value >= 0 ? '+' : '-';
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pnlColor(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-green-400' : 'text-red-400';
}

function formatEntryTime(seconds: number | null): string {
  if (seconds === null) return '—';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatWalletAge(dateStr: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(typeof dateStr === 'number' ? dateStr * 1000 : dateStr);
    if (isNaN(d.getTime())) return '—';
    const days = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
    if (days < 1) return '<1d';
    if (days < 7) return `${days}d`;
    if (days < 30) return `${Math.floor(days / 7)}w`;
    if (days < 365) return `${Math.floor(days / 30)}mo`;
    return `${(days / 365).toFixed(1)}y`;
  } catch {
    return '—';
  }
}

function formatBalance(value: number | null): string {
  if (value === null || value === undefined) return '—';
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  return `$${value.toFixed(0)}`;
}

function formatHoldTime(hours: number | null): string {
  if (hours === null || hours === undefined) return '—';
  if (hours < 1) return `${(hours * 60).toFixed(0)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

// ============================================================================
// Component
// ============================================================================

interface SortHeaderProps {
  field: SortField;
  label: string;
  sortBy: SortField;
  sortDir: 'asc' | 'desc';
  onSort: (field: SortField) => void;
}

const SortHeader = ({ field, label, sortBy, sortDir, onSort }: SortHeaderProps) => (
  <button
    onClick={() => onSort(field)}
    className='hover:text-primary flex items-center gap-1 transition-colors'
  >
    <span>{label}</span>
    {sortBy === field && (
      <span className='text-[10px]'>{sortDir === 'asc' ? '▲' : '▼'}</span>
    )}
  </button>
);

export default function WalletLeaderboardPage() {
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<SortField>('total_pnl_usd');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(0);
  const perPage = 100;

  // Search: debounced server-side search
  const [searchInput, setSearchInput] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Faceted filters
  const [includeTags, setIncludeTags] = useState<Set<string>>(new Set());
  const [excludeTags, setExcludeTags] = useState<Set<string>>(new Set());
  const [includeTiers, setIncludeTiers] = useState<Set<string>>(new Set());
  const [excludeTiers, setExcludeTiers] = useState<Set<string>>(new Set());
  const [holdTimeFilter, setHoldTimeFilter] = useState<string>('any'); // 'any' | '<1h' | '1-4h' | '4-24h' | '>24h'
  const [minHomeRuns, setMinHomeRuns] = useState<number>(0);
  const [showFilters, setShowFilters] = useState(false);
  const [starredOnly, setStarredOnly] = useState(false);

  // Panels
  const [clusterPanelData, setClusterPanelData] = useState<ClusterData | null>(null);
  const [deployerPanelAddress, setDeployerPanelAddress] = useState<string | null>(null);
  const { openWIR } = useWalletIntelligence();
  const [clusterCache, setClusterCache] = useState<{
    fundedBy: Record<string, { funder: string; funderName: string | null; funderType: string | null }>;
    clusters: FunderCluster[];
  } | null>(null);

  const statusBarData = useStatusBarData({
    pollInterval: 30000
  });

  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  // Debounce search input
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setActiveSearch(searchInput.trim());
      setPage(0);
    }, 400);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [searchInput]);

  const fetchLeaderboard = useCallback(async (showToast = false) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        sort_by: sortBy,
        sort_dir: sortDir,
        limit: String(perPage),
        offset: String(page * perPage),
      });
      if (activeSearch) params.set('search', activeSearch);
      if (includeTags.size > 0) params.set('tags', Array.from(includeTags).join(','));
      if (excludeTags.size > 0) params.set('exclude_tags', Array.from(excludeTags).join(','));
      if (includeTiers.size > 0) params.set('include_tiers', Array.from(includeTiers).join(','));
      if (excludeTiers.size > 0) params.set('exclude_tiers', Array.from(excludeTiers).join(','));
      if (minHomeRuns > 0) params.set('min_home_runs', String(minHomeRuns));
      if (holdTimeFilter !== 'any') params.set('hold_time', holdTimeFilter);
      if (starredOnly) params.set('starred_only', 'true');

      const res = await fetch(`${API_BASE_URL}/api/leaderboard?${params}`);
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLastRefreshedAt(new Date());
        if (showToast) {
          toast.success('Wallet leaderboard refreshed', {
            description: `${json.wallets?.length ?? 0} wallets loaded`,
            duration: 2000,
          });
        }
      } else if (showToast) {
        toast.error('Failed to refresh leaderboard');
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard:', err);
      if (showToast) toast.error('Failed to refresh leaderboard');
    } finally {
      setLoading(false);
    }
  }, [sortBy, sortDir, activeSearch, includeTags, excludeTags, includeTiers, excludeTiers, minHomeRuns, holdTimeFilter, starredOnly, page]);

  useEffect(() => {
    fetchLeaderboard();
    fetch(`${API_BASE_URL}/wallets/cached-intel`)
      .then((r) => r.ok ? r.json() : null)
      .then((intel) => {
        if (intel) setClusterCache({ fundedBy: intel.fundedBy, clusters: intel.clusters });
      })
      .catch(() => {});
  }, [fetchLeaderboard]);

  // Auto-refresh when position checks or MC refresh completes
  useEffect(() => {
    const handler = () => fetchLeaderboard();
    window.addEventListener('meridinate:position-check-complete', handler);
    window.addEventListener('meridinate:mc-refresh-complete', handler);
    return () => {
      window.removeEventListener('meridinate:position-check-complete', handler);
      window.removeEventListener('meridinate:mc-refresh-complete', handler);
    };
  }, [fetchLeaderboard]);

  // Funding-chain terminal backfill — runs once per page render. For wallets
  // missing terminal_address, POST a batch to /api/wallets/funding-terminal/batch
  // which traces them via Helius and persists. Cap at 25/render to avoid huge
  // credit bursts on the first page load. Already-cached wallets are free.
  useEffect(() => {
    if (!data?.wallets) return;
    const missing = data.wallets
      .filter((w) => !w.terminal_address)
      .map((w) => w.wallet_address)
      .slice(0, 25);
    if (missing.length === 0) return;

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/wallets/funding-terminal/batch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wallet_addresses: missing, max_hops: 3 }),
        });
        if (!res.ok || cancelled) return;
        const json = await res.json();
        const terminals: Record<string, { terminal_address: string | null; terminal_name: string | null; terminal_type: string | null }> = json.terminals || {};
        // Merge terminal info into the current state without refetching the whole page.
        setData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            wallets: prev.wallets.map((w) => {
              const t = terminals[w.wallet_address];
              if (!t) return w;
              return {
                ...w,
                terminal_address: t.terminal_address ?? w.terminal_address,
                terminal_name: t.terminal_name ?? w.terminal_name,
                terminal_type: t.terminal_type ?? w.terminal_type,
              };
            }),
          };
        });
      } catch { /* silent — column shows "—" until next render */ }
    })();
    return () => { cancelled = true; };
  }, [data?.wallets]);

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortDir(field === 'avg_entry_seconds' ? 'asc' : 'desc');
    }
    setPage(0);
  };

  const clearAllFilters = () => {
    setIncludeTags(new Set());
    setExcludeTags(new Set());
    setIncludeTiers(new Set());
    setExcludeTiers(new Set());
    setHoldTimeFilter('any');
    setMinHomeRuns(0);
    setStarredOnly(false);
    setPage(0);
  };

  const hasFilters = includeTags.size > 0 || excludeTags.size > 0 || includeTiers.size > 0 || excludeTiers.size > 0 || holdTimeFilter !== 'any' || minHomeRuns > 0 || starredOnly;
  const activeFilterCount = includeTags.size + excludeTags.size + includeTiers.size + excludeTiers.size + (holdTimeFilter !== 'any' ? 1 : 0) + (minHomeRuns > 0 ? 1 : 0);

  // Toggle helpers for checkboxes
  const toggleIncludeTag = (tag: string) => {
    setIncludeTags((prev) => { const n = new Set(prev); if (n.has(tag)) n.delete(tag); else n.add(tag); return n; });
    setExcludeTags((prev) => { const n = new Set(prev); n.delete(tag); return n; });
  };
  const toggleExcludeTag = (tag: string) => {
    setExcludeTags((prev) => { const n = new Set(prev); if (n.has(tag)) n.delete(tag); else n.add(tag); return n; });
    setIncludeTags((prev) => { const n = new Set(prev); n.delete(tag); return n; });
  };
  const toggleIncludeTier = (tier: string) => {
    setIncludeTiers((prev) => { const n = new Set(prev); if (n.has(tier)) n.delete(tier); else n.add(tier); return n; });
    setExcludeTiers((prev) => { const n = new Set(prev); n.delete(tier); return n; });
  };
  const toggleExcludeTier = (tier: string) => {
    setExcludeTiers((prev) => { const n = new Set(prev); if (n.has(tier)) n.delete(tier); else n.add(tier); return n; });
    setIncludeTiers((prev) => { const n = new Set(prev); n.delete(tier); return n; });
  };

  // All filtering is server-side — no client-side filtering needed
  const wallets = data?.wallets ?? [];

  const colCount = 17;

  return (
    <TooltipProvider>
      <div>
        {/* Tag Reference moved to global sidebar panel */}

        <div className='space-y-4 p-6'>

        {/* Page Header */}
        <div className='flex items-center justify-between'>
          <div>
            <h1 className='text-2xl font-bold'>Wallet Leaderboard</h1>
            <p className='text-muted-foreground text-sm'>
              {(() => {
                const total = data?.total ?? 0;
                const start = page * perPage + 1;
                const end = Math.min(start + wallets.length - 1, total);
                if (data?.is_search) return `${total} wallets matching "${activeSearch}"`;
                if (hasFilters) return `Showing ${start}–${end} of ${total} filtered wallets`;
                return `Showing ${start}–${end} of ${total} recurring wallets`;
              })()}
              {lastRefreshedAt && (
                <span className='ml-2 text-[10px] opacity-60'>
                  · {lastRefreshedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              )}
            </p>
          </div>
          <Button
            variant='outline'
            size='sm'
            onClick={() => fetchLeaderboard(true)}
            disabled={loading}
          >
            Refresh
          </Button>
        </div>

        {/* Search + Faceted Filters */}
        <div className='space-y-2'>
          {/* Search bar + filter toggle */}
          <div className='flex items-center gap-2'>
            <div className='relative flex-1 max-w-md'>
              <Search className='absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground' />
              <input
                type='text'
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder='Search wallet address across entire database...'
                className='bg-background focus:ring-primary h-9 w-full rounded-md border pl-9 pr-8 text-sm focus:outline-none focus:ring-2'
              />
              {searchInput && (
                <button
                  onClick={() => { setSearchInput(''); setActiveSearch(''); }}
                  className='absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground'
                >
                  <X className='h-3.5 w-3.5' />
                </button>
              )}
            </div>
            <Button
              variant={showFilters ? 'default' : 'outline'}
              size='sm'
              onClick={() => setShowFilters(!showFilters)}
              className='gap-1.5'
            >
              <SlidersHorizontal className='h-3.5 w-3.5' />
              Filters
              {activeFilterCount > 0 && (
                <span className='rounded-full bg-primary-foreground/20 px-1.5 text-[10px] font-bold'>
                  {activeFilterCount}
                </span>
              )}
            </Button>
            <Button
              variant={starredOnly ? 'default' : 'outline'}
              size='sm'
              onClick={() => { setStarredOnly(!starredOnly); setPage(0); }}
              className='gap-1'
            >
              <Star className={cn('h-3.5 w-3.5', starredOnly && 'fill-yellow-400 text-yellow-400')} />
              Starred
            </Button>
            {hasFilters && (
              <button
                onClick={clearAllFilters}
                className='text-[11px] text-muted-foreground hover:text-foreground'
              >
                Clear all
              </button>
            )}
          </div>

          {/* Faceted filter panel */}
          {showFilters && (
            <div className='rounded-lg border bg-card p-4'>
              <div className='grid grid-cols-4 gap-6'>

                {/* Column 1: Must Have Tags */}
                <div>
                  <h4 className='text-[10px] font-semibold uppercase text-muted-foreground mb-2 flex items-center gap-1'>
                    <ChevronDown className='h-3 w-3' />
                    Must Have Tags
                    {includeTags.size > 0 && <span className='text-green-400 ml-auto'>{includeTags.size}</span>}
                  </h4>
                  <div className='space-y-0.5 max-h-[220px] overflow-y-auto'>
                    {TAG_FILTER_OPTIONS.map((tag) => (
                      <label key={tag} className='flex items-center gap-2 cursor-pointer hover:bg-muted/50 rounded px-1.5 py-0.5'>
                        <input type='checkbox' className='h-3 w-3 rounded accent-green-500'
                          checked={includeTags.has(tag)} onChange={() => toggleIncludeTag(tag)} />
                        <span className={`text-[11px] ${includeTags.has(tag) ? 'text-green-400 font-medium' : 'text-muted-foreground'}`}>{tag}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Column 2: Exclude Tags */}
                <div>
                  <h4 className='text-[10px] font-semibold uppercase text-muted-foreground mb-2 flex items-center gap-1'>
                    <ChevronDown className='h-3 w-3' />
                    Exclude Tags
                    {excludeTags.size > 0 && <span className='text-red-400 ml-auto'>{excludeTags.size}</span>}
                  </h4>
                  <div className='space-y-0.5 max-h-[220px] overflow-y-auto'>
                    {TAG_FILTER_OPTIONS.map((tag) => (
                      <label key={tag} className='flex items-center gap-2 cursor-pointer hover:bg-muted/50 rounded px-1.5 py-0.5'>
                        <input type='checkbox' className='h-3 w-3 rounded accent-red-500'
                          checked={excludeTags.has(tag)} onChange={() => toggleExcludeTag(tag)} />
                        <span className={`text-[11px] ${excludeTags.has(tag) ? 'text-red-400 line-through' : 'text-muted-foreground'}`}>{tag}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Column 3: Token Outcomes */}
                <div>
                  <h4 className='text-[10px] font-semibold uppercase text-muted-foreground mb-2 flex items-center gap-1'>
                    <ChevronDown className='h-3 w-3' />
                    Token Outcomes
                    {(includeTiers.size + excludeTiers.size) > 0 && <span className='text-amber-400 ml-auto'>{includeTiers.size + excludeTiers.size}</span>}
                  </h4>
                  <p className='text-[9px] text-muted-foreground mb-1'>Require:</p>
                  <div className='space-y-0.5 mb-2'>
                    {TIER_FILTER_OPTIONS.map((tier) => {
                      const display = TIER_DISPLAY[tier];
                      const style = getTierStyle(tier);
                      return (
                        <label key={`inc-${tier}`} className='flex items-center gap-2 cursor-pointer hover:bg-muted/50 rounded px-1.5 py-0.5'>
                          <input type='checkbox' className='h-3 w-3 rounded accent-green-500'
                            checked={includeTiers.has(tier)} onChange={() => toggleIncludeTier(tier)} />
                          <span className={`text-[11px] font-medium ${includeTiers.has(tier) ? style.text : 'text-muted-foreground'}`}>{display?.label ?? tier}</span>
                        </label>
                      );
                    })}
                  </div>
                  <p className='text-[9px] text-muted-foreground mb-1'>Exclude:</p>
                  <div className='space-y-0.5'>
                    {TIER_FILTER_OPTIONS.map((tier) => {
                      const display = TIER_DISPLAY[tier];
                      return (
                        <label key={`exc-${tier}`} className='flex items-center gap-2 cursor-pointer hover:bg-muted/50 rounded px-1.5 py-0.5'>
                          <input type='checkbox' className='h-3 w-3 rounded accent-red-500'
                            checked={excludeTiers.has(tier)} onChange={() => toggleExcludeTier(tier)} />
                          <span className={`text-[11px] ${excludeTiers.has(tier) ? 'text-red-400 line-through' : 'text-muted-foreground'}`}>{display?.label ?? tier}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                {/* Column 4: Performance */}
                <div>
                  <h4 className='text-[10px] font-semibold uppercase text-muted-foreground mb-2 flex items-center gap-1'>
                    <ChevronDown className='h-3 w-3' />
                    Performance
                    {(holdTimeFilter !== 'any' || minHomeRuns > 0) && <span className='text-blue-400 ml-auto'>!</span>}
                  </h4>
                  <p className='text-[9px] text-muted-foreground mb-1'>7D Avg Hold Time:</p>
                  <div className='space-y-0.5 mb-3'>
                    {[
                      { value: 'any', label: 'Any' },
                      { value: '<1h', label: 'Under 1 hour' },
                      { value: '1-4h', label: '1 – 4 hours' },
                      { value: '4-24h', label: '4 – 24 hours' },
                      { value: '>24h', label: 'Over 24 hours' },
                    ].map((opt) => (
                      <label key={opt.value} className='flex items-center gap-2 cursor-pointer hover:bg-muted/50 rounded px-1.5 py-0.5'>
                        <input type='radio' name='holdTime' className='h-3 w-3 accent-blue-500'
                          checked={holdTimeFilter === opt.value} onChange={() => setHoldTimeFilter(opt.value)} />
                        <span className={`text-[11px] ${holdTimeFilter === opt.value && opt.value !== 'any' ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>{opt.label}</span>
                      </label>
                    ))}
                  </div>
                  <p className='text-[9px] text-muted-foreground mb-1'>Min Home Runs (10x+):</p>
                  <div className='flex items-center gap-2'>
                    <input type='range' min={0} max={10} value={minHomeRuns}
                      onChange={(e) => setMinHomeRuns(parseInt(e.target.value))}
                      className='flex-1 h-1.5 accent-green-500' />
                    <span className={`text-xs font-mono w-5 text-center ${minHomeRuns > 0 ? 'text-green-400 font-bold' : 'text-muted-foreground'}`}>{minHomeRuns}</span>
                  </div>
                </div>

              </div>

              {/* Active filter summary */}
              {hasFilters && (
                <div className='mt-3 pt-3 border-t text-[10px] text-muted-foreground'>
                  {includeTags.size > 0 && (
                    <span>Must have: {Array.from(includeTags).map((t, i) => (
                      <span key={t}>{i > 0 && ' + '}<span className='text-green-400'>{t}</span></span>
                    ))}</span>
                  )}
                  {excludeTags.size > 0 && (
                    <span>{includeTags.size > 0 && ' · '}Excluding: {Array.from(excludeTags).map((t, i) => (
                      <span key={t}>{i > 0 && ', '}<span className='text-red-400'>{t}</span></span>
                    ))}</span>
                  )}
                  {includeTiers.size > 0 && (
                    <span>{(includeTags.size > 0 || excludeTags.size > 0) && ' · '}Tiers: {Array.from(includeTiers).map((t, i) => (
                      <span key={t}>{i > 0 && ' + '}<span className='text-green-400'>{TIER_DISPLAY[t]?.label ?? t}</span></span>
                    ))}</span>
                  )}
                  {excludeTiers.size > 0 && (
                    <span>{(includeTags.size > 0 || excludeTags.size > 0 || includeTiers.size > 0) && ' · '}No: {Array.from(excludeTiers).map((t, i) => (
                      <span key={t}>{i > 0 && ', '}<span className='text-red-400'>{TIER_DISPLAY[t]?.label ?? t}</span></span>
                    ))}</span>
                  )}
                  {holdTimeFilter !== 'any' && (
                    <span>{(includeTags.size > 0 || excludeTags.size > 0 || includeTiers.size > 0 || excludeTiers.size > 0) && ' · '}Hold: <span className='text-blue-400'>{holdTimeFilter}</span></span>
                  )}
                  {minHomeRuns > 0 && (
                    <span>{activeFilterCount > 1 && ' · '}Min HR: <span className='text-green-400'>{minHomeRuns}+</span></span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Leaderboard Table */}
        <div className='rounded-lg border'>

          {/* Pagination — Top */}
          {(data?.total ?? 0) > perPage && (
            <div className='flex items-center justify-between border-b px-4 py-2'>
              <p className='text-[11px] text-muted-foreground'>
                Page {page + 1} of {Math.ceil((data?.total ?? 0) / perPage)} · {data?.total} wallets
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
                  <th className='px-2 py-2 text-left text-xs font-medium w-10'>#</th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>Wallet</th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>Tags</th>
                  <th className='px-2 py-2 text-center text-xs font-medium'>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span><SortHeader field='tier_score' label='Home Runs / Rugs' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} /></span>
                      </TooltipTrigger>
                      <TooltipContent className='max-w-xs'>
                        Home Runs = tokens that hit 10x+ ATH. Rugs = rug pulls + dead tokens. Sorted by weighted score: 100x=100pts, 50x=50, 25x=25, 10x=10, 5x=5, 3x=3. Losses: rug=-5, dead=-4, 90%=-3, 70%=-2, stale=-1.
                      </TooltipContent>
                    </Tooltip>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='wallet_balance_usd' label='Balance' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span><SortHeader field='avg_entry_seconds' label='Avg Entry' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} /></span>
                      </TooltipTrigger>
                      <TooltipContent>Average seconds after token creation when this wallet buys. Lower = faster.</TooltipContent>
                    </Tooltip>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <Tooltip>
                      <TooltipTrigger asChild><span>Age</span></TooltipTrigger>
                      <TooltipContent>Wallet age based on first funding transaction.</TooltipContent>
                    </Tooltip>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span><SortHeader field='avg_hold_hours_7d' label='7D Hold' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} /></span>
                      </TooltipTrigger>
                      <TooltipContent>Average hold time for positions exited in the last 7 days.</TooltipContent>
                    </Tooltip>
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='total_pnl_usd' label='Total PnL' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='realized_pnl_usd' label='Realized' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='pnl_1d_usd' label='1D' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='pnl_7d_usd' label='7D' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='pnl_30d_usd' label='30D' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>
                    <SortHeader field='win_rate' label='Win Rate' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium'>
                    <SortHeader field='tokens_traded' label='Tokens' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-right text-xs font-medium'>
                    <SortHeader field='best_trade_pnl' label='Best Trade' sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  </th>
                  <th className='px-2 py-2 text-left text-xs font-medium' title='Terminal of the wallet funding chain. Exchange names like "Coinbase 12" indicate a CEX off-ramp; raw addresses indicate an opaque source.'>
                    Funded By
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading && !data ? (
                  <tr>
                    <td colSpan={colCount} className='text-muted-foreground py-12 text-center'>
                      Loading leaderboard...
                    </td>
                  </tr>
                ) : wallets.length === 0 ? (
                  <tr>
                    <td colSpan={colCount} className='text-muted-foreground py-12 text-center'>
                      {activeSearch
                        ? 'No wallets match your search.'
                        : hasFilters
                          ? 'No wallets match the current filters.'
                          : 'No recurring wallets yet. Wallets appearing in 2+ scanned tokens will show here.'}
                    </td>
                  </tr>
                ) : (
                  wallets.map((wallet) => (
                    <tr
                      key={wallet.wallet_address}
                      className={`hover:bg-blue-500/10 cursor-pointer border-b transition-colors ${
                        wallet.is_archive ? 'opacity-70' : ''
                      }`}
                      onClick={() => openWIR(wallet.wallet_address)}
                    >
                      {/* Rank */}
                      <td className='px-2 py-2 text-xs text-muted-foreground'>
                        {wallet.is_archive ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className='rounded bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground'>
                                ARC
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>This wallet is outside the top 100 leaderboard. Ranked #{wallet.rank} overall.</TooltipContent>
                          </Tooltip>
                        ) : (
                          wallet.rank
                        )}
                      </td>
                      {/* Wallet */}
                      <td className='px-2 py-2'>
                        <div className='flex items-center gap-1'>
                          <StarButton type='wallet' address={wallet.wallet_address} />
                          <code className='text-[11px] font-mono'>{wallet.wallet_address}</code>
                        </div>
                      </td>
                      {/* Tags */}
                      <td className='px-2 py-2'>
                        <div className='flex flex-wrap gap-1'>
                          {(wallet.tags || []).filter(Boolean).slice(0, 3).map((tag: string) => {
                            const trimmed = tag.trim();
                            const style = getTagStyle(trimmed);
                            const isCluster = trimmed === 'Cluster' && clusterCache;
                            const isDeployer = trimmed.includes('Deployer');
                            const cluster = isCluster
                              ? (() => {
                                  const fb = clusterCache!.fundedBy[wallet.wallet_address];
                                  if (!fb) return null;
                                  return clusterCache!.clusters.find(
                                    (c) => c.funder === fb.funder && c.wallets.length > 1
                                  );
                                })()
                              : null;
                            const isClickable = cluster || isDeployer;
                            return (
                              <span
                                key={tag}
                                className={`rounded px-1.5 py-0.5 text-[10px] ${style.bg} ${style.text} ${isClickable ? 'cursor-pointer hover:brightness-125' : ''}`}
                                onClick={isClickable ? (e) => {
                                  e.stopPropagation();
                                  if (cluster) {
                                    setClusterPanelData({
                                      funder: cluster.funder,
                                      funder_name: cluster.funder_name,
                                      funder_type: cluster.funder_type,
                                      wallets: cluster.wallets,
                                    });
                                  } else if (isDeployer) {
                                    setDeployerPanelAddress(wallet.wallet_address);
                                  }
                                } : undefined}
                              >
                                {cluster ? `Cluster (${cluster.wallets.length})` : trimmed}
                              </span>
                            );
                          })}
                        </div>
                      </td>
                      {/* Home Runs / Rugs */}
                      <td className='px-2 py-2 text-center text-xs'>
                        <div className='flex items-center justify-center gap-0.5'>
                          <span className={`font-bold ${wallet.home_runs > 0 ? 'text-green-400' : 'text-muted-foreground'}`}>
                            {wallet.home_runs}
                          </span>
                          <span className='text-muted-foreground/50'>/</span>
                          <span className={`font-bold ${wallet.rugs > 0 ? 'text-red-400' : 'text-muted-foreground'}`}>
                            {wallet.rugs}
                          </span>
                        </div>
                      </td>
                      {/* Balance */}
                      <td className='px-2 py-2 text-right font-mono text-xs'>
                        {formatBalance(wallet.wallet_balance_usd)}
                      </td>
                      {/* Avg Entry */}
                      <td className={`px-2 py-2 text-right text-xs ${
                        wallet.avg_entry_seconds !== null && wallet.avg_entry_seconds < 30 ? 'text-sky-400' :
                        wallet.avg_entry_seconds !== null && wallet.avg_entry_seconds < 60 ? 'text-yellow-400' : ''
                      }`}>
                        {formatEntryTime(wallet.avg_entry_seconds)}
                      </td>
                      {/* Age */}
                      <td className='px-2 py-2 text-right text-xs text-muted-foreground'>
                        {formatWalletAge(wallet.wallet_created_at)}
                      </td>
                      {/* 7D Hold */}
                      <td className={`px-2 py-2 text-right text-xs ${
                        wallet.avg_hold_hours_7d !== null && wallet.avg_hold_hours_7d < 1 ? 'text-orange-400' :
                        wallet.avg_hold_hours_7d !== null && wallet.avg_hold_hours_7d < 4 ? 'text-yellow-400' : ''
                      }`}>
                        {formatHoldTime(wallet.avg_hold_hours_7d)}
                      </td>
                      {/* Total PnL */}
                      <td className={`px-2 py-2 text-right font-mono text-xs font-semibold ${pnlColor(wallet.total_pnl_usd)}`}>
                        {formatPnl(wallet.total_pnl_usd)}
                      </td>
                      {/* Realized */}
                      <td className={`px-2 py-2 text-right font-mono text-xs ${pnlColor(wallet.realized_pnl_usd)}`}>
                        {formatPnl(wallet.realized_pnl_usd)}
                      </td>
                      {/* 1D */}
                      <td className={`px-2 py-2 text-right font-mono text-xs ${pnlColor(wallet.pnl_1d_usd)}`}>
                        {formatPnl(wallet.pnl_1d_usd)}
                      </td>
                      {/* 7D */}
                      <td className={`px-2 py-2 text-right font-mono text-xs ${pnlColor(wallet.pnl_7d_usd)}`}>
                        {formatPnl(wallet.pnl_7d_usd)}
                      </td>
                      {/* 30D */}
                      <td className={`px-2 py-2 text-right font-mono text-xs ${pnlColor(wallet.pnl_30d_usd)}`}>
                        {formatPnl(wallet.pnl_30d_usd)}
                      </td>
                      {/* Win Rate */}
                      <td className='px-2 py-2 text-xs'>
                        {wallet.win_rate !== null ? `${(wallet.win_rate * 100).toFixed(0)}%` : '—'}
                        <span className='text-muted-foreground ml-1'>({wallet.tokens_won}/{wallet.tokens_traded})</span>
                      </td>
                      {/* Tokens */}
                      <td className='px-2 py-2 text-xs'>{wallet.tokens_traded}</td>
                      {/* Best Trade */}
                      <td className='px-2 py-2 text-right'>
                        <div className='text-xs'>
                          <span className={pnlColor(wallet.best_trade_pnl)}>{formatPnl(wallet.best_trade_pnl)}</span>
                          {wallet.best_trade_token && <span className='text-muted-foreground ml-1 text-[10px]'>{wallet.best_trade_token}</span>}
                        </div>
                      </td>
                      {/* Funded By — terminal of the funding chain.
                          - Labeled exchange/protocol → show the name in cyan
                          - Opaque terminal wallet → show the full address (per Simon's preference)
                          - Not yet traced → "—" placeholder; backfill batch refreshes this. */}
                      <td className='px-2 py-2 text-left text-[11px]'>
                        {wallet.terminal_name ? (
                          <span
                            className={cn(
                              'font-medium',
                              wallet.terminal_type === 'exchange' ? 'text-cyan-400' :
                              wallet.terminal_type === 'protocol' ? 'text-purple-400' :
                              'text-foreground'
                            )}
                            title={`${wallet.terminal_type || 'labeled'} · ${wallet.terminal_address || ''}`}
                          >
                            {wallet.terminal_name}
                          </span>
                        ) : wallet.terminal_address ? (
                          <code className='font-mono text-[10px] text-muted-foreground break-all' title='Opaque terminal — chain ended at an unlabeled wallet'>
                            {wallet.terminal_address}
                          </code>
                        ) : (
                          <span className='text-muted-foreground/50' title='Not yet traced — backfill in progress'>—</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {(data?.total ?? 0) > perPage && (
            <div className='flex items-center justify-between border-t px-4 py-2'>
              <p className='text-[11px] text-muted-foreground'>
                Page {page + 1} of {Math.ceil((data?.total ?? 0) / perPage)}
              </p>
              <div className='flex items-center gap-2'>
                <Button
                  variant='outline'
                  size='sm'
                  className='h-7 text-xs'
                  disabled={page === 0}
                  onClick={() => setPage(page - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant='outline'
                  size='sm'
                  className='h-7 text-xs'
                  disabled={(page + 1) * perPage >= (data?.total ?? 0)}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Status Bar */}
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
        {/* Funding Tree Panel */}
        <FundingTreePanel
          open={!!clusterPanelData}
          onClose={() => setClusterPanelData(null)}
          cluster={clusterPanelData}
        />
        {/* Deployer Panel */}
        <DeployerPanel
          open={!!deployerPanelAddress}
          onClose={() => setDeployerPanelAddress(null)}
          deployerAddress={deployerPanelAddress}
        />
      </div>{/* end Main Content */}
      </div>{/* end flex wrapper */}
    </TooltipProvider>
  );
}
