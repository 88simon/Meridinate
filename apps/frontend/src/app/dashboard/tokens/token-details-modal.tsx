'use client';

import type { TokenDetail } from '@/types/token';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import {
  formatTimestamp,
  downloadAxiomJson,
  getTokenAnalysisHistory,
  getTokenById,
  getCachedTokenDetails,
  AnalysisHistory,
  refreshWalletBalances,
  getSolscanSettings,
  buildSolscanUrl,
  SolscanSettings,
  API_BASE_URL,
  addWalletTag,
  removeWalletTag,
  getWalletTags
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Download,
  ExternalLink,
  Copy,
  History,
  Twitter,
  RefreshCw,
  Info,
  Star
} from 'lucide-react';
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { toast } from 'sonner';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WalletTags } from '@/components/wallet-tags';
import { AdditionalTagsPopover } from '@/components/additional-tags';
import { WalletTagLabels } from '@/components/wallet-tag-labels';
import { WalletTagsProvider } from '@/contexts/WalletTagsContext';

interface TokenDetailsModalProps {
  tokenId: number | null;
  open: boolean;
  onClose: () => void;
}

// Loading skeleton for the modal content
function TokenDetailsLoadingSkeleton() {
  return (
    <div className='space-y-4'>
      {/* Header skeleton */}
      <div className='flex items-center justify-between'>
        <div className='space-y-2'>
          <Skeleton className='h-8 w-48' />
          <Skeleton className='h-4 w-64' />
          <Skeleton className='h-4 w-32' />
        </div>
        <Skeleton className='h-9 w-28' />
      </div>

      {/* Info grid skeleton */}
      <div className='mt-3 grid grid-cols-4 gap-3'>
        {[...Array(4)].map((_, i) => (
          <div key={i} className='rounded-lg border p-2'>
            <Skeleton className='mb-2 h-3 w-20' />
            <Skeleton className='h-5 w-full' />
          </div>
        ))}
      </div>

      {/* Tabs skeleton */}
      <div className='mt-3'>
        <Skeleton className='mb-4 h-10 w-full' />
        <div className='rounded-md border p-4'>
          <div className='space-y-3'>
            {[...Array(5)].map((_, i) => (
              <div key={i} className='flex items-center gap-4'>
                <Skeleton className='h-4 w-8' />
                <Skeleton className='h-4 w-64' />
                <Skeleton className='h-4 w-20' />
                <Skeleton className='h-4 w-16' />
                <Skeleton className='h-4 w-24' />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function TokenDetailsModal({
  tokenId,
  open,
  onClose
}: TokenDetailsModalProps) {
  const { openWIR } = useWalletIntelligence();
  // Token data state - starts with cached data if available
  const [token, setToken] = useState<TokenDetail | null>(() =>
    tokenId ? getCachedTokenDetails(tokenId) : null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Wallet PnL data for this token
  const [walletPnl, setWalletPnl] = useState<Record<string, {
    total_pnl_usd: number;
    realized_pnl_usd: number;
    unrealized_pnl_usd: number;
    total_bought_usd: number;
    total_sold_usd: number;
    current_holdings: number;
    current_holdings_usd: number;
    status: string;
  }>>({});

  // Starred wallets (Watchlist tag = shows in Codex)
  const [starredWallets, setStarredWallets] = useState<Set<string>>(new Set());

  // Load starred status for wallets when token loads
  useEffect(() => {
    if (!token?.wallets || !open) return;
    const checkStarred = async () => {
      const starred = new Set<string>();
      // Check first 20 wallets to avoid too many API calls
      for (const w of token.wallets.slice(0, 20)) {
        try {
          const tags = await getWalletTags(w.wallet_address);
          if (tags.some((t: any) => t.tag === 'Watchlist')) {
            starred.add(w.wallet_address);
          }
        } catch {}
      }
      setStarredWallets(starred);
    };
    checkStarred();
  }, [token?.wallets, open]);

  const toggleStar = async (walletAddress: string) => {
    const isStarred = starredWallets.has(walletAddress);
    try {
      if (isStarred) {
        await removeWalletTag(walletAddress, 'Watchlist');
        setStarredWallets((prev) => { const next = new Set(prev); next.delete(walletAddress); return next; });
        toast.success('Removed from Watchlist');
      } else {
        await addWalletTag(walletAddress, 'Watchlist', false);
        setStarredWallets((prev) => new Set(prev).add(walletAddress));
        toast.success('Added to Watchlist (visible in Codex)');
      }
    } catch {
      toast.error('Failed to update Watchlist');
    }
  };

  // Fetch wallet PnL when token loads
  useEffect(() => {
    if (!tokenId || !open) return;
    fetch(`${API_BASE_URL}/api/tokens/${tokenId}/wallet-pnl`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => { if (data?.pnl) setWalletPnl(data.pnl); })
      .catch(() => {});
  }, [tokenId, open]);

  // Fetch token details when modal opens or tokenId changes
  useEffect(() => {
    if (!open || tokenId === null) {
      return;
    }

    // Check for cached data first (instant display)
    const cached = getCachedTokenDetails(tokenId);
    if (cached) {
      setToken(cached);
      setLoadError(null);
      // Still fetch fresh data in background to ensure we have the latest
      getTokenById(tokenId, { skipCache: true })
        .then(setToken)
        .catch(() => {
          // Silently fail - we already have cached data
        });
      return;
    }

    // No cache - fetch with loading state
    setIsLoading(true);
    setLoadError(null);
    getTokenById(tokenId)
      .then((data) => {
        setToken(data);
        setLoadError(null);
      })
      .catch((err) => {
        setLoadError(err.message || 'Failed to load token details');
        setToken(null);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [open, tokenId]);

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      // Small delay to prevent flicker on reopen
      const timer = setTimeout(() => {
        setToken(null);
        setLoadError(null);
        setIsLoading(false);
      }, 200);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Extract all wallet addresses for WalletTagsProvider
  const walletAddresses = useMemo(() => {
    if (!token) return [];
    return token.wallets.map((w) => w.wallet_address);
  }, [token]);

  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<AnalysisHistory | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [refreshingWallets, setRefreshingWallets] = useState<Set<string>>(
    new Set()
  );
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [solscanSettings, setSolscanSettings] = useState<SolscanSettings>({
    activity_type: 'ACTIVITY_SPL_TRANSFER',
    exclude_amount_zero: 'true',
    remove_spam: 'true',
    value: '100',
    token_address: 'So11111111111111111111111111111111111111111',
    page_size: '10'
  });

  // Virtualization state
  const currentWalletsContainerRef = useRef<HTMLDivElement>(null);
  const [currentScrollTop, setCurrentScrollTop] = useState(0);
  const [currentViewportHeight, setCurrentViewportHeight] = useState(0);

  const formatWalletTimestamp = (timestamp?: string | null) => {
    if (!timestamp) return 'Not refreshed yet';
    const iso = timestamp.replace(' ', 'T') + 'Z';
    const date = new Date(iso);
    return `Updated ${date.toLocaleString()}`;
  };

  const getWalletTrend = (
    wallet: TokenDetail['wallets'][number]
  ): 'up' | 'down' | 'flat' | 'none' => {
    const current = wallet.wallet_balance_usd;
    const previous = wallet.wallet_balance_usd_previous;
    if (current === null || current === undefined) return 'none';
    if (previous === null || previous === undefined) return 'none';
    if (current > previous) return 'up';
    if (current < previous) return 'down';
    return 'flat';
  };

  // Handle scroll for current wallets virtualization
  const handleCurrentWalletsScroll = useCallback(() => {
    if (currentWalletsContainerRef.current) {
      setCurrentScrollTop(currentWalletsContainerRef.current.scrollTop);
    }
  }, []);

  // Update viewport height on mount and resize
  useEffect(() => {
    if (currentWalletsContainerRef.current) {
      const updateHeight = () => {
        setCurrentViewportHeight(
          currentWalletsContainerRef.current?.clientHeight ?? 0
        );
      };
      updateHeight();
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    }
  }, [open]);

  // Virtualization logic for current wallets
  const { visibleCurrentWallets, currentPaddingTop, currentPaddingBottom } =
    useMemo(() => {
      if (!token?.wallets) {
        return {
          visibleCurrentWallets: [],
          currentPaddingTop: 0,
          currentPaddingBottom: 0
        };
      }

      const allWallets = token.wallets;
      const totalWallets = allWallets.length;
      const baseRowHeight = 60;
      const overscan = 5;
      const visibleCount =
        currentViewportHeight > 0
          ? Math.ceil(currentViewportHeight / Math.max(baseRowHeight, 1)) +
            overscan
          : totalWallets;
      const startIndex = Math.max(
        0,
        Math.floor(currentScrollTop / Math.max(baseRowHeight, 1)) - overscan
      );
      const endIndex = Math.min(totalWallets, startIndex + visibleCount);
      const visibleWallets = allWallets.slice(startIndex, endIndex);
      const paddingTop = startIndex * baseRowHeight;
      const paddingBottom = Math.max(
        0,
        (totalWallets - endIndex) * baseRowHeight
      );

      return {
        visibleCurrentWallets: visibleWallets,
        currentPaddingTop: paddingTop,
        currentPaddingBottom: paddingBottom
      };
    }, [token, currentScrollTop, currentViewportHeight]);

  // Fetch analysis history when modal opens
  useEffect(() => {
    if (open && token) {
      setLoadingHistory(true);
      getTokenAnalysisHistory(token.id)
        .then(setHistory)
        .catch(() => {
          setHistory(null);
        })
        .finally(() => setLoadingHistory(false));

      // Fetch Solscan settings for URL generation
      getSolscanSettings()
        .then(setSolscanSettings)
        .catch(() => {
          // Silently fail, keep default settings
        });
    }
  }, [open, token]);

  const copyAddress = (address: string) => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRefreshBalance = async (walletAddress: string) => {
    setRefreshingWallets((prev) => new Set(prev).add(walletAddress));
    try {
      const response = await refreshWalletBalances([walletAddress]);
      toast.success(
        `Refreshed balance (${response.api_credits_used} API credit${response.api_credits_used !== 1 ? 's' : ''} used)`
      );

      // Refresh the token data to show updated balance
      if (token) {
        const updatedHistory = await getTokenAnalysisHistory(token.id);
        setHistory(updatedHistory);
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to refresh balance');
    } finally {
      setRefreshingWallets((prev) => {
        const newSet = new Set(prev);
        newSet.delete(walletAddress);
        return newSet;
      });
    }
  };

  const handleRefreshAllBalances = async () => {
    if (!token) return;

    setRefreshingAll(true);
    const allWalletAddresses = token.wallets.map((w) => w.wallet_address);

    if (allWalletAddresses.length === 0) {
      toast.error('No wallets to refresh');
      setRefreshingAll(false);
      return;
    }

    toast.info(
      `Refreshing balances for ${allWalletAddresses.length} wallet(s)...`
    );

    try {
      const response = await refreshWalletBalances(allWalletAddresses);
      toast.success(
        `Refreshed ${response.successful} of ${response.total_wallets} wallet(s) (${response.api_credits_used} API credits used)`
      );

      // Refresh the token data to show updated balances
      const updatedHistory = await getTokenAnalysisHistory(token.id);
      setHistory(updatedHistory);
    } catch (error: any) {
      toast.error(error.message || 'Failed to refresh balances');
    } finally {
      setRefreshingAll(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-h-[90vh] w-[95vw] max-w-[95vw] overflow-y-auto'>
        {/* Loading state */}
        {isLoading && !token && (
          <>
            <DialogHeader>
              <DialogTitle className='text-2xl'>Loading...</DialogTitle>
              <DialogDescription className='text-muted-foreground'>
                Fetching token details...
              </DialogDescription>
            </DialogHeader>
            <TokenDetailsLoadingSkeleton />
          </>
        )}

        {/* Error state */}
        {loadError && !token && (
          <>
            <DialogHeader>
              <DialogTitle className='text-destructive text-2xl'>
                Error Loading Token
              </DialogTitle>
              <DialogDescription className='text-muted-foreground'>
                {loadError}
              </DialogDescription>
            </DialogHeader>
            <div className='flex justify-center py-8'>
              <Button variant='outline' onClick={onClose}>
                Close
              </Button>
            </div>
          </>
        )}

        {/* Token data loaded */}
        {token && (
          <WalletTagsProvider walletAddresses={walletAddresses}>
            <DialogHeader>
              <div className='flex items-center justify-between'>
                <div>
                  <DialogTitle className='text-2xl'>
                    {token.token_name || 'Unknown Token'}
                  </DialogTitle>
                  <DialogDescription className='text-muted-foreground'>
                    Full wallet analysis, tags, and history for this token.
                  </DialogDescription>
                  <p className='text-muted-foreground mt-1 text-sm'>
                    {token.token_symbol || '-'} • Early Buyer Analysis
                  </p>
                </div>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => downloadAxiomJson(token)}
                >
                  <Download className='mr-2 h-4 w-4' />
                  Axiom JSON
                </Button>
              </div>
            </DialogHeader>

            {/* Token Info Grid */}
            <div className='mt-3 grid grid-cols-5 gap-3'>
              <div className='rounded-lg border p-2'>
                <div className='text-muted-foreground mb-1 text-[11px] font-medium'>
                  Token Address
                </div>
                <div className='flex items-center gap-1'>
                  <code className='text-[10px] break-all'>
                    {token.token_address.slice(0, 16)}...
                  </code>
                  <Button
                    variant='ghost'
                    size='sm'
                    onClick={() => copyAddress(token.token_address)}
                    className='h-5 w-5 p-0'
                  >
                    {copied ? 'Copied!' : <Copy className='h-3 w-3' />}
                  </Button>
                </div>
                <a
                  href={`https://gmgn.ai/sol/token/${token.token_address}?min=0.1&isInputValue=true`}
                  target='_blank'
                  rel='noopener noreferrer'
                  className='text-primary mt-1 flex items-center text-[10px] hover:underline'
                >
                  View on GMGN <ExternalLink className='ml-1 h-2.5 w-2.5' />
                </a>
              </div>

              <div className='rounded-lg border p-2'>
                <div className='text-muted-foreground mb-1 text-[11px] font-medium'>
                  Acronym
                </div>
                <Badge variant='secondary' className='font-mono text-sm'>
                  {token.acronym}
                </Badge>
              </div>

              <div className='rounded-lg border p-2'>
                <div className='text-muted-foreground mb-1 text-[11px] font-medium'>
                  Wallets Found
                </div>
                <div className='text-lg font-bold'>{token.wallets_found}</div>
              </div>

              <div className='rounded-lg border p-2'>
                <div className='text-muted-foreground mb-1 text-[11px] font-medium'>
                  First Filtered Buy
                </div>
                <div className='text-xs'>
                  {formatTimestamp(token.first_buy_timestamp)}
                </div>
              </div>

              <div className='rounded-lg border p-2'>
                <div className='text-muted-foreground mb-1 text-[11px] font-medium'>
                  Analyzed
                </div>
                <div className='text-xs'>
                  {formatTimestamp(token.analysis_timestamp)}
                </div>
              </div>
            </div>

            {/* Creation Timeline */}
            {(() => {
              const events = token.creation_events_json
                ? (typeof token.creation_events_json === 'string'
                  ? JSON.parse(token.creation_events_json)
                  : token.creation_events_json)
                : [];
              if (events.length === 0 && !token.deployer_address) return null;
              return (
                <div className='rounded-lg border p-3'>
                  <div className='text-xs font-medium mb-2'>Token Creation Timeline</div>
                  <div className='space-y-1.5'>
                    {events.map((event: { type: string; timestamp: string; wallet: string; sol_amount?: number; usd_amount?: number; token_amount?: number; signature?: string }, idx: number) => (
                      <div key={idx} className='flex items-center gap-2 text-[11px]'>
                        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                          event.type === 'CREATE' ? 'bg-purple-500' :
                          event.type === 'ADD_LIQUIDITY' ? 'bg-blue-500' :
                          'bg-green-500'
                        }`} />
                        <span className='text-muted-foreground w-20 shrink-0'>
                          {event.type === 'CREATE' ? 'Created' :
                           event.type === 'ADD_LIQUIDITY' ? 'LP Added' :
                           'First Buy'}
                        </span>
                        <span className='text-muted-foreground w-28 shrink-0'>
                          {new Date(event.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                        <span className='font-mono text-[10px] truncate'>
                          {event.wallet?.slice(0, 8)}...{event.wallet?.slice(-4)}
                        </span>
                        {event.type === 'CREATE' && (
                          <span className='rounded bg-purple-500/20 px-1.5 py-0.5 text-[9px] text-purple-400'>Deployer</span>
                        )}
                        {event.sol_amount && event.sol_amount > 0 && (
                          <span className='text-muted-foreground'>
                            {event.sol_amount.toFixed(2)} SOL
                          </span>
                        )}
                        {event.usd_amount && event.usd_amount > 0 && (
                          <span className='text-muted-foreground'>
                            ~${event.usd_amount.toFixed(0)}
                          </span>
                        )}
                      </div>
                    ))}
                    {events.length === 0 && token.deployer_address && (
                      <div className='flex items-center gap-2 text-[11px]'>
                        <span className='h-1.5 w-1.5 rounded-full shrink-0 bg-purple-500' />
                        <span className='text-muted-foreground'>Deployer:</span>
                        <span className='font-mono text-[10px]'>
                          {token.deployer_address.slice(0, 8)}...{token.deployer_address.slice(-4)}
                        </span>
                        <span className='rounded bg-purple-500/20 px-1.5 py-0.5 text-[9px] text-purple-400'>Deployer</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Analytics Signals */}
            {(() => {
              const hasAnySignal = token.holder_velocity != null || token.mc_volatility != null ||
                token.smart_money_flow || token.avg_hold_hours != null || token.deployer_is_top_holder != null ||
                token.webhook_detected_at != null;
              if (!hasAnySignal) return null;

              const smartFlow = token.smart_money_flow
                ? (typeof token.smart_money_flow === 'string' ? JSON.parse(token.smart_money_flow) : token.smart_money_flow)
                : null;

              return (
                <div className='rounded-lg border p-3'>
                  <div className='text-xs font-medium mb-2'>Analytics Signals</div>
                  <div className='space-y-1.5 text-[11px]'>
                    {token.holder_velocity != null && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Holder Concentration Velocity</span>
                        <span className={token.holder_velocity > 5 ? 'text-red-400' : token.holder_velocity < -5 ? 'text-green-400' : ''}>
                          {token.holder_velocity > 0 ? '+' : ''}{token.holder_velocity.toFixed(1)}%/hr
                        </span>
                      </div>
                    )}
                    {token.deployer_is_top_holder != null && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Deployer Still Top Holder</span>
                        <span className={token.deployer_is_top_holder ? 'text-amber-400' : 'text-green-400'}>
                          {token.deployer_is_top_holder ? 'Yes' : 'No'}
                        </span>
                      </div>
                    )}
                    {token.early_buyer_holder_overlap != null && token.early_buyer_holder_overlap > 0 && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Early Buyer / Top Holder Overlap</span>
                        <span className={token.early_buyer_holder_overlap > 3 ? 'text-red-400' : ''}>
                          {token.early_buyer_holder_overlap} wallets
                        </span>
                      </div>
                    )}
                    {token.fresh_wallet_pct != null && token.fresh_wallet_pct > 0 && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Fresh Wallet %</span>
                        <span className={token.fresh_wallet_pct > 50 ? 'text-red-400' : ''}>
                          {token.fresh_wallet_pct.toFixed(0)}%
                        </span>
                      </div>
                    )}
                    {token.mc_volatility != null && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>MC Volatility</span>
                        <span className={token.mc_volatility > 50 ? 'text-amber-400' : ''}>
                          {token.mc_volatility.toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {token.mc_recovery_count != null && token.mc_recovery_count > 0 && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>MC Recovery Count</span>
                        <span className='text-green-400'>{token.mc_recovery_count}x recovered</span>
                      </div>
                    )}
                    {smartFlow && (smartFlow.smart_buying > 0 || smartFlow.smart_selling > 0 || smartFlow.smart_holding > 0) && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Smart Money Flow</span>
                        <span className={
                          smartFlow.flow_direction === 'bullish' ? 'text-green-400' :
                          smartFlow.flow_direction === 'bearish' ? 'text-red-400' : 'text-muted-foreground'
                        }>
                          {smartFlow.smart_buying || 0} buying · {smartFlow.smart_selling || 0} selling · {smartFlow.smart_holding || 0} holding
                        </span>
                      </div>
                    )}
                    {token.avg_hold_hours != null && token.avg_hold_hours > 0 && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Avg Hold Duration</span>
                        <span>{token.avg_hold_hours < 2 ? `${(token.avg_hold_hours * 60).toFixed(0)}m` : `${token.avg_hold_hours.toFixed(1)}h`}</span>
                      </div>
                    )}
                    {token.webhook_detected_at && (
                      <>
                        <div className='border-t border-border my-1.5' />
                        <div className='flex justify-between'>
                          <span className='text-muted-foreground'>Webhook First Detected</span>
                          <span className='text-emerald-400'>
                            {new Date(token.webhook_detected_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                        {token.webhook_conviction_score != null && (
                          <div className='flex justify-between'>
                            <span className='text-muted-foreground'>Birth Conviction Score</span>
                            <span className={
                              token.webhook_conviction_score >= 70 ? 'text-green-400' :
                              token.webhook_conviction_score >= 40 ? 'text-yellow-400' : 'text-red-400'
                            }>
                              {token.webhook_conviction_score}/100
                            </span>
                          </div>
                        )}
                        {token.time_to_migration_minutes != null && (
                          <div className='flex justify-between'>
                            <span className='text-muted-foreground'>Time to Migration</span>
                            <span>
                              {token.time_to_migration_minutes < 60
                                ? `${token.time_to_migration_minutes.toFixed(1)} min`
                                : `${(token.time_to_migration_minutes / 60).toFixed(1)} hrs`}
                            </span>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Tabs for Current Analysis and History */}
            <Tabs defaultValue='current' className='mt-3'>
              <TabsList className='grid w-full grid-cols-2'>
                <TabsTrigger value='current'>Latest Analysis</TabsTrigger>
                <TabsTrigger value='history'>
                  <History className='mr-2 h-4 w-4' />
                  History ({history?.total_runs || 0} runs)
                </TabsTrigger>
              </TabsList>

              {/* Current Analysis Tab */}
              <TabsContent value='current'>
                <div
                  ref={currentWalletsContainerRef}
                  onScroll={handleCurrentWalletsScroll}
                  className='mt-4 max-h-[500px] overflow-auto rounded-md border'
                >
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className='w-[60px]'>Rank</TableHead>
                        <TableHead>Wallet Address</TableHead>
                        <TableHead className='text-right'>
                          <div className='flex items-center justify-end gap-2'>
                            <span>Balance (USD)</span>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant='ghost'
                                    size='sm'
                                    className='h-5 w-5 p-0'
                                  >
                                    <Info className='h-3 w-3' />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className='text-xs'>
                                    Refreshing a single wallet balance costs 1
                                    API credit
                                  </p>
                                  <p className='text-xs'>
                                    Refreshing all {token.wallets.length}{' '}
                                    wallet(s) costs {token.wallets.length} API
                                    credits
                                  </p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-6 w-6 p-0'
                              onClick={handleRefreshAllBalances}
                              disabled={refreshingAll}
                              title='Refresh all balances'
                            >
                              <RefreshCw
                                className={`h-3 w-3 ${refreshingAll ? 'animate-spin' : ''}`}
                              />
                            </Button>
                          </div>
                        </TableHead>
                        <TableHead className='text-right'>
                          <div className='flex items-center justify-end gap-1'>
                            <span>Token uPnL/PnL</span>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-5 w-5 p-0'
                              onClick={async () => {
                                if (!tokenId) return;
                                toast.info('Computing PnL for all wallets...');
                                try {
                                  const res = await fetch(`${API_BASE_URL}/api/tokens/${tokenId}/compute-wallet-pnl`, { method: 'POST' });
                                  if (res.ok) {
                                    const data = await res.json();
                                    setWalletPnl(data.pnl);
                                    toast.success(`PnL computed for ${data.wallets_computed} wallets (${data.credits_used} credits)`);
                                  }
                                } catch { toast.error('Failed to compute PnL'); }
                              }}
                              title='Compute/refresh uPnL and PnL for all wallets'
                            >
                              <RefreshCw className='h-3 w-3' />
                            </Button>
                          </div>
                        </TableHead>
                        <TableHead className='text-right'>Tags</TableHead>
                        <TableHead>First Buy Time</TableHead>
                        <TableHead className='text-right'>
                          Amount (USD)
                        </TableHead>
                        <TableHead className='text-center'>Txns</TableHead>
                        <TableHead className='text-right'>Avg Buy</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {token.wallets.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={9}
                            className='text-muted-foreground py-12 text-center'
                          >
                            No wallets found
                          </TableCell>
                        </TableRow>
                      ) : (
                        <>
                          {currentPaddingTop > 0 && (
                            <TableRow aria-hidden='true'>
                              <TableCell
                                colSpan={9}
                                className='p-0'
                                style={{ height: currentPaddingTop }}
                              />
                            </TableRow>
                          )}
                          {visibleCurrentWallets.map((wallet) => {
                            const index = token.wallets.findIndex(
                              (w) => w.id === wallet.id
                            );
                            return (
                              <TableRow key={wallet.id}>
                                <TableCell className='text-primary text-xs font-semibold'>
                                  #{index + 1}
                                </TableCell>
                                <TableCell className='font-mono text-xs'>
                                  <div className='flex flex-col gap-0.5'>
                                    <div className='flex items-center gap-2'>
                                      <span
                                        className='cursor-pointer hover:text-blue-400 transition-colors'
                                        title='Click for Wallet Intelligence Report'
                                        onClick={() => openWIR(wallet.wallet_address)}
                                      >
                                        {wallet.wallet_address}
                                      </span>
                                      <a
                                        href={`https://twitter.com/search?q=${encodeURIComponent(wallet.wallet_address)}`}
                                        target='_blank'
                                        rel='noopener noreferrer'
                                        title='Search on Twitter/X'
                                      >
                                        <Button
                                          variant='ghost'
                                          size='sm'
                                          className='h-6 w-6 p-0'
                                        >
                                          <Twitter className='h-3 w-3' />
                                        </Button>
                                      </a>
                                      <Button
                                        variant='ghost'
                                        size='sm'
                                        className='h-6 w-6 p-0'
                                        onClick={() =>
                                          copyAddress(wallet.wallet_address)
                                        }
                                      >
                                        <Copy className='h-3 w-3' />
                                      </Button>
                                      <Button
                                        variant='ghost'
                                        size='sm'
                                        className='h-6 w-6 p-0'
                                        onClick={() => toggleStar(wallet.wallet_address)}
                                        title={starredWallets.has(wallet.wallet_address) ? 'Remove from Watchlist' : 'Add to Watchlist'}
                                      >
                                        <Star className={`h-3 w-3 ${starredWallets.has(wallet.wallet_address) ? 'fill-yellow-400 text-yellow-400' : ''}`} />
                                      </Button>
                                    </div>
                                    <WalletTagLabels
                                      walletAddress={wallet.wallet_address}
                                    />
                                  </div>
                                </TableCell>
                                <TableCell className='text-right font-mono text-xs'>
                                  <div className='flex flex-col items-end gap-1'>
                                    <div className='flex items-center gap-1'>
                                      {(() => {
                                        const trend = getWalletTrend(wallet);
                                        const current =
                                          wallet.wallet_balance_usd;
                                        const formatted =
                                          current !== null &&
                                          current !== undefined
                                            ? `$${Math.round(current).toLocaleString()}`
                                            : 'N/A';
                                        if (trend === 'up') {
                                          return (
                                            <span className='flex items-center gap-1 text-green-600'>
                                              <span>▲</span>
                                              <span>{formatted}</span>
                                            </span>
                                          );
                                        }
                                        if (trend === 'down') {
                                          return (
                                            <span className='flex items-center gap-1 text-red-600'>
                                              <span>▼</span>
                                              <span>{formatted}</span>
                                            </span>
                                          );
                                        }
                                        return <span>{formatted}</span>;
                                      })()}
                                      <Button
                                        variant='ghost'
                                        size='sm'
                                        className='h-6 w-6 p-0'
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleRefreshBalance(
                                            wallet.wallet_address
                                          );
                                        }}
                                        disabled={
                                          refreshingWallets.has(
                                            wallet.wallet_address
                                          ) || refreshingAll
                                        }
                                        title='Refresh balance - 1 API credit'
                                      >
                                        <RefreshCw
                                          className={`h-3 w-3 ${refreshingWallets.has(wallet.wallet_address) ? 'animate-spin' : ''}`}
                                        />
                                      </Button>
                                    </div>
                                    <div className='text-muted-foreground text-[11px]'>
                                      {formatWalletTimestamp(
                                        wallet.wallet_balance_updated_at as
                                          | string
                                          | null
                                      )}
                                    </div>
                                  </div>
                                </TableCell>
                                <TableCell className='text-right'>
                                  {(() => {
                                    const pnl = walletPnl[wallet.wallet_address];
                                    if (!pnl) return <span className='text-muted-foreground text-xs'>—</span>;
                                    const val = pnl.total_pnl_usd;
                                    const isHolding = pnl.status === 'holding';
                                    const color = val > 0 ? 'text-green-400' : val < 0 ? 'text-red-400' : 'text-muted-foreground';
                                    const label = isHolding ? 'uPnL' : pnl.status === 'exited' ? 'Exited' : 'PnL';
                                    return (
                                      <TooltipProvider>
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <div className='flex flex-col items-end'>
                                              <span className={`font-mono text-xs font-medium ${color}`}>
                                                {val >= 0 ? '+' : ''}${Math.abs(val).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                              </span>
                                              <span className={`text-[9px] ${isHolding ? 'text-blue-400' : 'text-muted-foreground'}`}>
                                                {label}{isHolding && pnl.current_holdings_usd ? ` ($${pnl.current_holdings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })} held)` : ''}
                                              </span>
                                            </div>
                                          </TooltipTrigger>
                                          <TooltipContent>
                                            <div className='space-y-0.5 text-xs'>
                                              <p>Spent: ${pnl.total_bought_usd?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>
                                              {isHolding && <p>Holdings Value: ${pnl.current_holdings_usd?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>}
                                              {pnl.unrealized_pnl_usd !== 0 && <p>Unrealized: ${pnl.unrealized_pnl_usd?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>}
                                              {pnl.realized_pnl_usd !== 0 && <p>Realized: ${pnl.realized_pnl_usd?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>}
                                              <p className='text-muted-foreground italic'>{isHolding ? 'Still holding tokens' : 'No longer holds this token'}</p>
                                            </div>
                                          </TooltipContent>
                                        </Tooltip>
                                      </TooltipProvider>
                                    );
                                  })()}
                                </TableCell>
                                <TableCell className='text-right'>
                                  <div className='flex justify-end gap-2'>
                                    <WalletTags
                                      walletAddress={wallet.wallet_address}
                                    />
                                    <AdditionalTagsPopover
                                      walletId={wallet.id}
                                      walletAddress={wallet.wallet_address}
                                    />
                                    <a
                                      href={buildSolscanUrl(
                                        wallet.wallet_address,
                                        solscanSettings
                                      )}
                                      target='_blank'
                                      rel='noopener noreferrer'
                                    >
                                      <Button variant='outline' size='sm'>
                                        <ExternalLink className='h-4 w-4' />
                                      </Button>
                                    </a>
                                  </div>
                                </TableCell>
                                <TableCell className='text-xs'>
                                  {formatTimestamp(wallet.first_buy_timestamp)}
                                </TableCell>
                                <TableCell className='text-right text-xs'>
                                  {wallet.total_usd
                                    ? `$${Math.round(wallet.total_usd)}`
                                    : 'N/A'}
                                </TableCell>
                                <TableCell className='text-center text-xs'>
                                  {wallet.transaction_count || 1}
                                </TableCell>
                                <TableCell className='text-right text-xs'>
                                  {wallet.average_buy_usd
                                    ? `$${Math.round(wallet.average_buy_usd)}`
                                    : 'N/A'}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                          {currentPaddingBottom > 0 && (
                            <TableRow aria-hidden='true'>
                              <TableCell
                                colSpan={9}
                                className='p-0'
                                style={{ height: currentPaddingBottom }}
                              />
                            </TableRow>
                          )}
                        </>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              {/* History Tab */}
              <TabsContent value='history'>
                {loadingHistory ? (
                  <div className='text-muted-foreground py-12 text-center'>
                    Loading analysis history...
                  </div>
                ) : !history || history.runs.length === 0 ? (
                  <div className='text-muted-foreground py-12 text-center'>
                    No analysis history available
                  </div>
                ) : (
                  <div className='mt-4 space-y-6'>
                    {history.runs.map((run, runIndex) => {
                      // Calculate cumulative wallet offset based on previous runs
                      const walletOffset = history.runs
                        .slice(runIndex + 1)
                        .reduce(
                          (sum, prevRun) => sum + prevRun.wallets_found,
                          0
                        );
                      const startWallet = walletOffset + 1;
                      const endWallet = walletOffset + run.wallets_found;
                      const analysisNumber = history.runs.length - runIndex;

                      return (
                        <div key={run.id} className='rounded-lg border p-2'>
                          <div className='mb-2 flex items-center justify-between'>
                            <div>
                              <h4 className='text-xs font-semibold'>
                                Analysis #{analysisNumber} (Wallets{' '}
                                {startWallet}-{endWallet})
                                {runIndex === 0 && (
                                  <Badge
                                    variant='secondary'
                                    className='ml-1 text-[10px]'
                                  >
                                    Latest
                                  </Badge>
                                )}
                              </h4>
                              <p className='text-muted-foreground text-[10px]'>
                                {formatTimestamp(run.analysis_timestamp)}
                              </p>
                            </div>
                            <div className='text-right text-xs'>
                              <div className='font-semibold'>
                                {run.wallets_found} wallets
                              </div>
                              <div className='text-muted-foreground text-[10px]'>
                                {run.credits_used} credits
                              </div>
                            </div>
                          </div>

                          <div className='rounded-md border'>
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead className='w-[60px]'>
                                    Rank
                                  </TableHead>
                                  <TableHead>Wallet Address</TableHead>
                                  <TableHead className='text-right'>
                                    <div className='flex items-center justify-end gap-2'>
                                      <span>Balance (USD)</span>
                                      <TooltipProvider>
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <Button
                                              variant='ghost'
                                              size='sm'
                                              className='h-4 w-4 p-0'
                                            >
                                              <Info className='h-2.5 w-2.5' />
                                            </Button>
                                          </TooltipTrigger>
                                          <TooltipContent>
                                            <p className='text-xs'>
                                              Refreshing a single wallet balance
                                              costs 1 API credit
                                            </p>
                                            <p className='text-xs'>
                                              Refreshing all{' '}
                                              {run.wallets.length} wallet(s)
                                              costs {run.wallets.length} API
                                              credits
                                            </p>
                                          </TooltipContent>
                                        </Tooltip>
                                      </TooltipProvider>
                                      <Button
                                        variant='ghost'
                                        size='sm'
                                        className='h-5 w-5 p-0'
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleRefreshAllBalances();
                                        }}
                                        disabled={refreshingAll}
                                        title='Refresh all balances'
                                      >
                                        <RefreshCw
                                          className={`h-2.5 w-2.5 ${refreshingAll ? 'animate-spin' : ''}`}
                                        />
                                      </Button>
                                    </div>
                                  </TableHead>
                                  <TableHead className='text-right'>
                                    Token uPnL/PnL
                                  </TableHead>
                                  <TableHead className='text-right'>
                                    Tags
                                  </TableHead>
                                  <TableHead>First Buy Time</TableHead>
                                  <TableHead className='text-right'>
                                    Amount (USD)
                                  </TableHead>
                                  <TableHead className='text-center'>
                                    Txns
                                  </TableHead>
                                  <TableHead className='text-right'>
                                    Avg Buy
                                  </TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {run.wallets.length === 0 ? (
                                  <TableRow>
                                    <TableCell
                                      colSpan={9}
                                      className='text-muted-foreground py-8 text-center text-sm'
                                    >
                                      No wallets in this run
                                    </TableCell>
                                  </TableRow>
                                ) : (
                                  run.wallets.map((wallet, index) => (
                                    <TableRow key={wallet.id}>
                                      <TableCell className='text-primary text-[11px] font-semibold'>
                                        #{walletOffset + index + 1}
                                      </TableCell>
                                      <TableCell className='font-mono text-[11px]'>
                                        <div className='flex flex-col gap-0.5'>
                                          <div className='flex items-center gap-1'>
                                            <span
                                              className='cursor-pointer hover:text-blue-400 transition-colors'
                                              title='Click for Wallet Intelligence Report'
                                              onClick={() => openWIR(wallet.wallet_address)}
                                            >
                                              {wallet.wallet_address}
                                            </span>
                                            <a
                                              href={`https://twitter.com/search?q=${encodeURIComponent(wallet.wallet_address)}`}
                                              target='_blank'
                                              rel='noopener noreferrer'
                                              title='Search on Twitter/X'
                                            >
                                              <Button
                                                variant='ghost'
                                                size='sm'
                                                className='h-5 w-5 p-0'
                                              >
                                                <Twitter className='h-2.5 w-2.5' />
                                              </Button>
                                            </a>
                                            <Button
                                              variant='ghost'
                                              size='sm'
                                              className='h-5 w-5 p-0'
                                              onClick={() =>
                                                copyAddress(
                                                  wallet.wallet_address
                                                )
                                              }
                                            >
                                              <Copy className='h-2.5 w-2.5' />
                                            </Button>
                                          </div>
                                          <WalletTagLabels
                                            walletAddress={
                                              wallet.wallet_address
                                            }
                                          />
                                        </div>
                                      </TableCell>
                                      <TableCell className='text-right font-mono text-[11px]'>
                                        <div className='flex flex-col items-end gap-1'>
                                          <div className='flex items-center gap-1'>
                                            {(() => {
                                              const trend =
                                                getWalletTrend(wallet);
                                              const current =
                                                wallet.wallet_balance_usd;
                                              const formatted =
                                                current !== null &&
                                                current !== undefined
                                                  ? `$${Math.round(current).toLocaleString()}`
                                                  : 'N/A';
                                              if (trend === 'up') {
                                                return (
                                                  <span className='flex items-center gap-1 text-green-600'>
                                                    <span>▲</span>
                                                    <span>{formatted}</span>
                                                  </span>
                                                );
                                              }
                                              if (trend === 'down') {
                                                return (
                                                  <span className='flex items-center gap-1 text-red-600'>
                                                    <span>▼</span>
                                                    <span>{formatted}</span>
                                                  </span>
                                                );
                                              }
                                              return <span>{formatted}</span>;
                                            })()}
                                          </div>
                                          <div className='text-muted-foreground text-[10px]'>
                                            {formatWalletTimestamp(
                                              wallet.wallet_balance_updated_at as
                                                | string
                                                | null
                                            )}
                                          </div>
                                          <Button
                                            variant='ghost'
                                            size='sm'
                                            className='h-5 w-5 p-0'
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              handleRefreshBalance(
                                                wallet.wallet_address
                                              );
                                            }}
                                            disabled={
                                              refreshingWallets.has(
                                                wallet.wallet_address
                                              ) || refreshingAll
                                            }
                                            title='Refresh balance - 1 API credit'
                                          >
                                            <RefreshCw
                                              className={`h-2.5 w-2.5 ${refreshingWallets.has(wallet.wallet_address) ? 'animate-spin' : ''}`}
                                            />
                                          </Button>
                                        </div>
                                      </TableCell>
                                      <TableCell className='text-right'>
                                        {(() => {
                                          const pnl = walletPnl[wallet.wallet_address];
                                          if (!pnl) return <span className='text-muted-foreground text-[10px]'>—</span>;
                                          const val = pnl.total_pnl_usd;
                                          const isHolding = pnl.status === 'holding';
                                          const color = val > 0 ? 'text-green-400' : val < 0 ? 'text-red-400' : 'text-muted-foreground';
                                          return (
                                            <div className='flex flex-col items-end'>
                                              <span className={`font-mono text-[10px] font-medium ${color}`}>{val >= 0 ? '+' : ''}${Math.abs(val).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                                              <span className={`text-[8px] ${isHolding ? 'text-blue-400' : 'text-muted-foreground'}`}>{isHolding ? 'uPnL' : 'Exited'}</span>
                                            </div>
                                          );
                                        })()}
                                      </TableCell>
                                      <TableCell className='text-right'>
                                        <div className='flex justify-end gap-1'>
                                          <WalletTags
                                            walletAddress={
                                              wallet.wallet_address
                                            }
                                          />
                                          <AdditionalTagsPopover
                                            walletId={wallet.id}
                                            walletAddress={
                                              wallet.wallet_address
                                            }
                                            compact
                                          />
                                          <a
                                            href={buildSolscanUrl(
                                              wallet.wallet_address,
                                              solscanSettings
                                            )}
                                            target='_blank'
                                            rel='noopener noreferrer'
                                          >
                                            <Button variant='outline' size='sm'>
                                              <ExternalLink className='h-3 w-3' />
                                            </Button>
                                          </a>
                                        </div>
                                      </TableCell>
                                      <TableCell className='text-[11px]'>
                                        {formatTimestamp(
                                          wallet.first_buy_timestamp
                                        )}
                                      </TableCell>
                                      <TableCell className='text-right text-[11px]'>
                                        {wallet.total_usd
                                          ? `$${Math.round(wallet.total_usd)}`
                                          : 'N/A'}
                                      </TableCell>
                                      <TableCell className='text-center text-[11px]'>
                                        {wallet.transaction_count || 1}
                                      </TableCell>
                                      <TableCell className='text-right text-[11px]'>
                                        {wallet.average_buy_usd
                                          ? `$${Math.round(wallet.average_buy_usd)}`
                                          : 'N/A'}
                                      </TableCell>
                                    </TableRow>
                                  ))
                                )}
                              </TableBody>
                            </Table>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </WalletTagsProvider>
        )}
      </DialogContent>
    </Dialog>
  );
}
