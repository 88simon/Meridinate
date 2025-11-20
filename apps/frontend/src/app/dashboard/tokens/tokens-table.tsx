'use client';

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getFilteredRowModel,
  useReactTable
} from '@tanstack/react-table';
import type { Row } from '@tanstack/react-table';
import {
  Token,
  TokenDetail,
  formatTimestamp,
  downloadAxiomJson,
  getTokenById,
  refreshMarketCaps,
  getApiSettings,
  AnalysisSettings,
  API_BASE_URL
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Eye,
  Download,
  Trash2,
  Search,
  Copy,
  Info,
  RefreshCw,
  Twitter
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
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
  useState,
  useMemo,
  useEffect,
  useCallback,
  memo,
  useRef,
  startTransition
} from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useCodex } from '@/contexts/codex-context';
import { cn } from '@/lib/utils';

// Lazy-load the token details modal to reduce initial JS bundle size
const TokenDetailsModal = dynamic(
  () => import('./token-details-modal').then((mod) => ({
    default: mod.TokenDetailsModal
  })),
  { ssr: false }
);

const MemoizedTableRow = memo(
  ({
    row,
    isSelected,
    handleRowClick,
    handleRowHover,
    isCompactMode
  }: {
    row: Row<Token>;
    isSelected: boolean;
    handleRowClick: (id: number, event: React.MouseEvent) => void;
    handleRowHover: (id: number) => void;
    isCompactMode: boolean;
  }) => (
    <tr
      className={cn(
        'cursor-pointer border-b transition-all duration-200 ease-out',
        'hover:shadow-[0_1px_3px_rgba(0,0,0,0.05)]',
        isSelected && [
          'bg-primary/20',
          'shadow-[inset_0_0_0_2px_rgba(59,130,246,0.3),0_0_10px_rgba(59,130,246,0.2)]',
          'hover:bg-primary/25',
          'hover:shadow-[inset_0_0_0_2px_rgba(59,130,246,0.4),0_0_15px_rgba(59,130,246,0.3)]',
          'active:bg-primary/30'
        ],
        !isSelected && [
          'hover:bg-muted/50',
          'active:bg-muted/70'
        ]
      )}
      onClick={(e) => handleRowClick(row.original.id, e)}
      onMouseEnter={() => handleRowHover(row.original.id)}
    >
      {row.getVisibleCells().map((cell) => (
        <TableCell
          key={cell.id}
          className={cn(
            'transition-all duration-200',
            isCompactMode ? 'px-2 py-2' : 'px-3 py-3'
          )}
        >
          {flexRender(cell.column.columnDef.cell, cell.getContext())}
        </TableCell>
      ))}
    </tr>
  ),
  (prev, next) =>
    prev.isSelected === next.isSelected &&
    prev.row.original === next.row.original &&
    prev.row.id === next.row.id &&
    prev.isCompactMode === next.isCompactMode
);
MemoizedTableRow.displayName = 'MemoizedTableRow';

// Memoized market cap cell to avoid recalculating formatting
const MarketCapCell = memo(
  ({
    token,
    isRefreshing,
    isCompact,
    onRefresh
  }: {
    token: Token;
    isRefreshing: boolean;
    isCompact: boolean;
    onRefresh: (e: React.MouseEvent) => void;
  }) => {
    const marketCapOriginal = token.market_cap_usd;
    const marketCapCurrent = token.market_cap_usd_current;
    const marketCapPrevious = token.market_cap_usd_previous;
    const marketCapUpdatedAt = token.market_cap_updated_at;
    const marketCapAth = token.market_cap_ath;
    const marketCapAthTimestamp = token.market_cap_ath_timestamp;

    // Determine comparison baseline: only use Previous (from last refresh)
    const comparisonBase = marketCapPrevious;
    const hasComparison = comparisonBase && marketCapCurrent;

    // Check if current is at ATH (all-time high)
    const isAtAth =
      marketCapAth && marketCapCurrent && marketCapCurrent >= marketCapAth;

    // Format market cap (e.g., $1.2M, $340K, $5.6B)
    const formatMarketCap = useCallback((value: number): string => {
      if (value >= 1_000_000_000) {
        return `$${(value / 1_000_000_000).toFixed(2)}B`;
      } else if (value >= 1_000_000) {
        return `$${(value / 1_000_000).toFixed(2)}M`;
      } else if (value >= 1_000) {
        return `$${(value / 1_000).toFixed(1)}K`;
      }
      return `$${value.toFixed(2)}`;
    }, []);

    // Format time since last refresh
    const formatTimeSinceRefresh = useCallback((timestamp: string): string => {
      // SQLite timestamp format: "YYYY-MM-DD HH:MM:SS"
      // Convert to ISO format by replacing space with T and adding Z for UTC
      const isoTimestamp = timestamp.replace(' ', 'T') + 'Z';
      const date = new Date(isoTimestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      let timeAgo = '';
      if (diffDays > 0) {
        timeAgo = `${diffDays}d ${diffHours % 24}h`;
      } else if (diffHours > 0) {
        timeAgo = `${diffHours}h ${diffMins % 60}m`;
      } else {
        timeAgo = `${diffMins}m`;
      }

      const dateStr = date.toLocaleString('en-US', {
        month: '2-digit',
        day: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });

      return `${dateStr}, ${timeAgo} from last refresh`;
    }, []);

    // No market cap data at all
    if (
      (!marketCapOriginal || marketCapOriginal === 0) &&
      (!marketCapCurrent || marketCapCurrent === 0)
    ) {
      return (
        <div className='flex items-center gap-1'>
          <div
            className={cn(
              'text-muted-foreground',
              isCompact ? 'text-xs' : 'text-sm'
            )}
          >
            -
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant='ghost'
                  size='sm'
                  className='h-5 w-5 p-0'
                  onClick={onRefresh}
                  disabled={isRefreshing}
                >
                  <RefreshCw
                    className={cn('h-1 w-1', isRefreshing && 'animate-spin')}
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Refresh market cap</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      );
    }

    // Display both original and current market caps
    return (
      <div className='flex flex-col gap-0.5'>
        {/* Original Market Cap from Analysis */}
        {marketCapOriginal && marketCapOriginal > 0 && (
          <div className='flex items-center gap-1'>
            <div
              className={cn(
                'text-muted-foreground',
                isCompact ? 'text-[9px]' : 'text-[10px]'
              )}
            >
              At Analysis:
            </div>
            <div
              className={cn(
                'font-medium tabular-nums',
                isCompact ? 'text-xs' : 'text-sm'
              )}
            >
              {formatMarketCap(marketCapOriginal)}
            </div>
          </div>
        )}

        {/* Current/Refreshed Market Cap */}
        {marketCapCurrent && marketCapCurrent > 0 && (
          <div className='flex items-center gap-1'>
            <div
              className={cn(
                'text-muted-foreground',
                isCompact ? 'text-[9px]' : 'text-[10px]'
              )}
            >
              Current:
            </div>
            <div
              className={cn(
                'font-semibold tabular-nums flex items-center gap-0.5',
                isCompact ? 'text-xs' : 'text-sm',
                (hasComparison && marketCapCurrent > comparisonBase!) || isAtAth
                  ? 'text-green-600'
                  : hasComparison && marketCapCurrent < comparisonBase!
                    ? 'text-red-600'
                    : 'text-muted-foreground'
              )}
            >
              {((hasComparison && marketCapCurrent > comparisonBase!) ||
                isAtAth) && <span>▲</span>}
              {hasComparison && marketCapCurrent < comparisonBase! && (
                <span>▼</span>
              )}
              {formatMarketCap(marketCapCurrent)}
            </div>
            {marketCapUpdatedAt && (
              <div
                className={cn(
                  'text-muted-foreground',
                  isCompact ? 'text-[9px]' : 'text-[10px]'
                )}
              >
                ({formatTimeSinceRefresh(marketCapUpdatedAt)})
              </div>
            )}
          </div>
        )}

        {/* Highest Market Cap Observed */}
        {marketCapAth && marketCapAth > 0 && (
          <div className='flex items-center gap-1'>
            <div className='flex items-center gap-0.5'>
              <div
                className={cn(
                  'text-muted-foreground',
                  isCompact ? 'text-[9px]' : 'text-[10px]'
                )}
              >
                Highest:
              </div>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className='text-muted-foreground h-3 w-3 cursor-help' />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className='max-w-xs text-xs'>
                      Highest market cap observed through our scans.
                      <br />
                      Not the true all-time high (requires historical data).
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <div
              className={cn(
                'font-semibold text-blue-600 tabular-nums',
                isCompact ? 'text-xs' : 'text-sm'
              )}
            >
              {formatMarketCap(marketCapAth)}
            </div>
            {marketCapAthTimestamp && (
              <div
                className={cn(
                  'text-muted-foreground',
                  isCompact ? 'text-[9px]' : 'text-[10px]'
                )}
              >
                ({formatTimestamp(marketCapAthTimestamp)})
              </div>
            )}
          </div>
        )}

        {/* Refresh Icon */}
        <div className='flex items-center gap-1'>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant='ghost'
                  size='sm'
                  className='h-4 w-4 p-0'
                  onClick={onRefresh}
                  disabled={isRefreshing}
                >
                  <RefreshCw
                    className={cn('h-1 w-1', isRefreshing && 'animate-spin')}
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Refresh market cap</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    );
  },
  (prev, next) =>
    prev.token.id === next.token.id &&
    prev.token.market_cap_usd === next.token.market_cap_usd &&
    prev.token.market_cap_usd_current === next.token.market_cap_usd_current &&
    prev.token.market_cap_usd_previous === next.token.market_cap_usd_previous &&
    prev.token.market_cap_updated_at === next.token.market_cap_updated_at &&
    prev.token.market_cap_ath === next.token.market_cap_ath &&
    prev.token.market_cap_ath_timestamp === next.token.market_cap_ath_timestamp &&
    prev.isRefreshing === next.isRefreshing &&
    prev.isCompact === next.isCompact
);
MarketCapCell.displayName = 'MarketCapCell';

// Memoized actions cell to avoid recreating callbacks
const ActionsCell = memo(
  ({
    isCompact,
    onViewDetails,
    onDownload,
    onDelete
  }: {
    isCompact: boolean;
    onViewDetails: () => void;
    onDownload: () => void;
    onDelete: () => void;
  }) => {
    const btnSize = isCompact ? 'h-7 w-7' : 'h-8 w-8';
    const iconSize = isCompact ? 'h-3 w-3' : 'h-4 w-4';

    return (
      <div className={cn('flex', isCompact ? 'gap-1' : 'gap-2')}>
        <Button
          variant='outline'
          size='sm'
          className={cn('p-0', btnSize)}
          onClick={onViewDetails}
        >
          <Eye className={iconSize} />
        </Button>
        <Button
          variant='outline'
          size='sm'
          className={cn('p-0', btnSize)}
          onClick={onDownload}
        >
          <Download className={iconSize} />
        </Button>
        <Button
          variant='destructive'
          size='sm'
          className={cn('p-0', btnSize)}
          onClick={onDelete}
        >
          <Trash2 className={iconSize} />
        </Button>
      </div>
    );
  },
  (prev, next) => prev.isCompact === next.isCompact
);
ActionsCell.displayName = 'ActionsCell';

const createColumns = (
  handleViewDetails: (id: number) => void,
  handleDelete: (id: number) => void,
  handleRefreshMarketCap: (id: number) => Promise<void>,
  handleRefreshAllMarketCaps: () => Promise<void>,
  refreshingMarketCaps: Set<number>,
  refreshingAll: boolean,
  isCompact: boolean = false,
  apiSettings: AnalysisSettings | null = null
): ColumnDef<Token>[] => [
  {
    accessorKey: 'token_name',
    header: 'Token',
    cell: ({ row }) => {
      const name = row.original.token_name || 'Unknown';
      const symbol = row.original.token_symbol || '-';
      return (
        <div className='min-w-[120px]'>
          <div className={cn('font-medium', isCompact ? 'text-xs' : 'text-sm')}>
            {name}
          </div>
          <div
            className={cn(
              'text-muted-foreground',
              isCompact ? 'text-[10px]' : 'text-xs'
            )}
          >
            {symbol}
          </div>
        </div>
      );
    }
  },
  {
    accessorKey: 'market_cap_usd',
    header: () => (
      <div className='flex items-center gap-1'>
        <span>Market Cap</span>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant='ghost'
                size='sm'
                className='h-5 w-5 p-0'
                onClick={(e) => {
                  e.stopPropagation();
                  handleRefreshAllMarketCaps();
                }}
                disabled={refreshingAll}
              >
                <RefreshCw
                  className={cn('h-1 w-1', refreshingAll && 'animate-spin')}
                />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Refresh all visible market caps</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    ),
    cell: ({ row }) => (
      <MarketCapCell
        token={row.original}
        isRefreshing={refreshingMarketCaps.has(row.original.id)}
        isCompact={isCompact}
        onRefresh={(e) => {
          e.stopPropagation();
          handleRefreshMarketCap(row.original.id);
        }}
      />
    )
  },
  {
    accessorKey: 'token_address',
    header: 'Address',
    cell: ({ row }) => {
      const address = row.getValue('token_address') as string;
      return (
        <div className='flex items-center gap-1'>
          <a
            href={`https://solscan.io/token/${address}`}
            target='_blank'
            rel='noopener noreferrer'
            className={cn(
              'text-primary font-mono break-all hover:underline',
              isCompact ? 'text-[9px]' : 'text-[10px]'
            )}
          >
            {address}
          </a>
          <a
            href={`https://twitter.com/search?q=${encodeURIComponent(address)}`}
            target='_blank'
            rel='noopener noreferrer'
            title='Search on Twitter/X'
          >
            <Button
              variant='ghost'
              size='sm'
              className={cn(
                'flex-shrink-0 p-0',
                isCompact ? 'h-5 w-5' : 'h-6 w-6'
              )}
            >
              <Twitter className={cn(isCompact ? 'h-2.5 w-2.5' : 'h-3 w-3')} />
            </Button>
          </a>
          <Button
            variant='ghost'
            size='sm'
            className={cn(
              'flex-shrink-0 p-0',
              isCompact ? 'h-5 w-5' : 'h-6 w-6'
            )}
            onClick={() => {
              navigator.clipboard.writeText(address);
              toast.success('Address copied to clipboard');
            }}
          >
            <Copy className={cn(isCompact ? 'h-2.5 w-2.5' : 'h-3 w-3')} />
          </Button>
        </div>
      );
    }
  },
  {
    id: 'actions',
    header: 'Actions',
    cell: ({ row }) => {
      const token = row.original;
      return (
        <ActionsCell
          isCompact={isCompact}
          onViewDetails={() => handleViewDetails(token.id)}
          onDownload={() => downloadAxiomJson(token as any)}
          onDelete={() => {
            if (
              window.confirm(
                `Delete token "${token.token_name || 'Unknown'}"?`
              )
            ) {
              handleDelete(token.id);
            }
          }}
        />
      );
    }
  },
  {
    accessorKey: 'wallets_found',
    header: () => (
      <div className='flex items-center justify-center gap-1'>
        <span>Wallets</span>
        <TooltipProvider delayDuration={100}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className='text-muted-foreground h-3 w-3 cursor-help' />
            </TooltipTrigger>
            <TooltipContent className='max-w-xs'>
              <p className='text-xs'>
                Total wallets found in the first{' '}
                {apiSettings?.transactionLimit ?? 500} transactions that spent
                ≥${apiSettings?.minUsdFilter ?? 50}. Top{' '}
                {apiSettings?.walletCount ?? 10} earliest stored.
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    ),
    cell: ({ row }) => (
      <div className='text-center'>
        <Badge
          variant='outline'
          className={cn(
            isCompact ? 'px-1.5 py-0 text-[10px]' : 'px-2 py-0.5 text-xs'
          )}
        >
          {row.getValue('wallets_found')}
        </Badge>
      </div>
    )
  },
  {
    accessorKey: 'first_buy_timestamp',
    header: 'First Filtered Buy',
    cell: ({ row }) => {
      const timestamp = row.getValue('first_buy_timestamp') as string;
      return (
        <div
          className={cn(
            'text-muted-foreground',
            isCompact ? 'text-[10px]' : 'text-xs'
          )}
        >
          {formatTimestamp(timestamp)}
        </div>
      );
    }
  },
  {
    accessorKey: 'last_analysis_credits',
    header: isCompact ? 'Latest Credits' : 'Credits Used For Latest Report',
    cell: ({ row }) => (
      <div
        className={cn(
          'font-semibold text-green-600',
          isCompact ? 'text-xs' : 'text-sm'
        )}
      >
        {row.getValue('last_analysis_credits') || 0}
      </div>
    )
  },
  {
    accessorKey: 'credits_used',
    header: isCompact ? 'Total Credits' : 'Cumulative Credits Used',
    cell: ({ row }) => (
      <div
        className={cn(
          'font-semibold text-orange-500',
          isCompact ? 'text-xs' : 'text-sm'
        )}
      >
        {row.getValue('credits_used') || 0}
      </div>
    )
  }
];

interface TokensTableProps {
  tokens: Token[];
  onDelete?: (tokenId: number) => void;
}

export function TokensTable({ tokens, onDelete }: TokensTableProps) {
  const router = useRouter();
  const { isCodexOpen } = useCodex();
  const [selectedToken, setSelectedToken] = useState<TokenDetail | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [globalFilter, setGlobalFilter] = useState('');
  const [isCompactMode, setIsCompactMode] = useState(isCodexOpen);
  const [selectedTokenIds, setSelectedTokenIds] = useState<Set<number>>(
    new Set()
  );
  const [refreshingMarketCaps, setRefreshingMarketCaps] = useState<Set<number>>(
    new Set()
  );
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [apiSettings, setApiSettings] = useState<AnalysisSettings | null>(null);
  const tableContainerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  // Local state for optimistic market cap updates
  const [marketCapUpdates, setMarketCapUpdates] = useState<
    Map<
      number,
      {
        market_cap_usd_current: number | null;
        market_cap_usd_previous: number | null;
        market_cap_updated_at: string | null;
        market_cap_ath: number | null;
        market_cap_ath_timestamp: string | null;
      }
    >
  >(new Map());

  // Delay compact mode change to sync with Codex animation
  useEffect(() => {
    const timer = setTimeout(
      () => {
        setIsCompactMode(isCodexOpen);
      },
      isCodexOpen ? 0 : 100
    );
    return () => clearTimeout(timer);
  }, [isCodexOpen]);

  // Fetch API settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const settings = await getApiSettings();
        setApiSettings(settings);
      } catch (error) {
        // Silently fail - Use default values if fetch fails (fallback in tooltip)
      }
    };
    fetchSettings();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const container = tableContainerRef.current;
    if (!container) return undefined;

    const updateHeight = () => setViewportHeight(container.clientHeight);
    updateHeight();

    if ('ResizeObserver' in window && typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(updateHeight);
      observer.observe(container);
      return () => observer.disconnect();
    }

    const handleResize = () => updateHeight();
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }
    return undefined;
  }, []);

  const handleViewDetails = async (id: number) => {
    try {
      const tokenDetails = await getTokenById(id);
      setSelectedToken(tokenDetails);
      setIsModalOpen(true);
    } catch (error) {
      alert('Failed to load token details. Please try again.');
    }
  };

  const handleDelete = async (id: number) => {
    // Optimistically update UI immediately
    if (onDelete) {
      onDelete(id);
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/tokens/${id}`, {
        method: 'DELETE',
        cache: 'no-store'
      });

      if (!response.ok) {
        throw new Error('Failed to delete token');
      }

      toast.success('Token deleted successfully');
    } catch (error) {
      toast.error('Failed to delete token. Please try again.');
      // On error, refresh to restore correct state
      router.refresh();
    }
  };

  const handleRefreshMarketCap = async (tokenId: number) => {
    setRefreshingMarketCaps((prev) => new Set(prev).add(tokenId));

    try {
      const response = await refreshMarketCaps([tokenId]);

      if (response.successful > 0) {
        const result = response.results[0];

        // Immediately update local state for instant UI update
        setMarketCapUpdates((prev) => {
          const newMap = new Map(prev);
          newMap.set(tokenId, {
            market_cap_usd_current: result.market_cap_usd_current,
            market_cap_usd_previous: result.market_cap_usd_previous,
            market_cap_updated_at: result.market_cap_updated_at,
            market_cap_ath: result.market_cap_ath,
            market_cap_ath_timestamp: result.market_cap_ath_timestamp
          });
          return newMap;
        });

        toast.success(
          `Market cap updated: $${result.market_cap_usd_current?.toLocaleString() || 'N/A'}`
        );
        router.refresh();
      } else {
        toast.error('Failed to refresh market cap - no data returned');
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unknown error';
      toast.error(`Failed to refresh market cap: ${errorMessage}`);
    } finally {
      setRefreshingMarketCaps((prev) => {
        const newSet = new Set(prev);
        newSet.delete(tokenId);
        return newSet;
      });
    }
  };

  const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

const [tableInstance, setTableInstance] = useState<any>(null);

  const handleRefreshAllMarketCaps = useCallback(async () => {
    if (!tableInstance) {
      toast.error('Table not ready');
      return;
    }

    const visibleTokenIds = tableInstance
      .getRowModel()
      .rows.map((row: any) => row.original.id);

    if (visibleTokenIds.length === 0) {
      toast.error('No tokens to refresh');
      return;
    }

    setRefreshingAll(true);

    try {
      const response = await refreshMarketCaps(visibleTokenIds);

      // Immediately update local state for all tokens
      setMarketCapUpdates((prev) => {
        const newMap = new Map(prev);
        response.results.forEach((result) => {
          newMap.set(result.token_id, {
            market_cap_usd_current: result.market_cap_usd_current,
            market_cap_usd_previous: result.market_cap_usd_previous,
            market_cap_updated_at: result.market_cap_updated_at,
            market_cap_ath: result.market_cap_ath,
            market_cap_ath_timestamp: result.market_cap_ath_timestamp
          });
        });
        return newMap;
      });

      toast.success(
        `Refreshed ${response.successful}/${response.total_tokens} market caps (${response.api_credits_used} credits)`
      );
      router.refresh();
    } catch (error) {
      toast.error(`Failed to refresh market caps: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setRefreshingAll(false);
    }
  }, [tableInstance, router]);

  const handleRefreshSelectedMarketCaps = async () => {
    if (selectedTokenIds.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    const tokenIdsArray = Array.from(selectedTokenIds);
    setRefreshingAll(true);

    try {
      const response = await refreshMarketCaps(tokenIdsArray);

      // Immediately update local state for all selected tokens
      setMarketCapUpdates((prev) => {
        const newMap = new Map(prev);
        response.results.forEach((result) => {
          newMap.set(result.token_id, {
            market_cap_usd_current: result.market_cap_usd_current,
            market_cap_usd_previous: result.market_cap_usd_previous,
            market_cap_updated_at: result.market_cap_updated_at,
            market_cap_ath: result.market_cap_ath,
            market_cap_ath_timestamp: result.market_cap_ath_timestamp
          });
        });
        return newMap;
      });

      toast.success(
        `Refreshed ${response.successful}/${response.total_tokens} market caps (${response.api_credits_used} credits)`
      );
      router.refresh();
    } catch (error) {
      toast.error('Failed to refresh market caps');
    } finally {
      setRefreshingAll(false);
    }
  };

  const handleRowClick = (tokenId: number, event: React.MouseEvent) => {
    // Don't select if clicking on a link, button, or interactive element
    const target = event.target as HTMLElement;
    if (
      target.tagName === 'A' ||
      target.tagName === 'BUTTON' ||
      target.closest('a') ||
      target.closest('button')
    ) {
      return;
    }

    // Use startTransition to defer selection updates as low priority
    startTransition(() => {
      setSelectedTokenIds((prev) => {
        const newSet = new Set(prev);
        if (newSet.has(tokenId)) {
          newSet.delete(tokenId);
        } else {
          newSet.add(tokenId);
        }
        return newSet;
      });
    });
  };

  // Predictive prefetching: preload token detail page and API data on row hover
  const handleRowHover = useCallback(
    (tokenId: number) => {
      // Prefetch the token detail page route
      router.prefetch(`/dashboard/tokens/${tokenId}`);

      // Prefetch the API data for token details
      // This ensures instant modal display when clicked
      getTokenById(tokenId).catch(() => {
        // Silently fail - prefetch is optional optimization
      });
    },
    [router]
  );

  const handleBulkDownload = () => {
    if (selectedTokenIds.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    const selectedTokens = tokens.filter((token) =>
      selectedTokenIds.has(token.id)
    );

    selectedTokens.forEach((token) => {
      downloadAxiomJson(token as any);
    });

    toast.success(`Downloaded ${selectedTokens.length} token(s)`);
    setSelectedTokenIds(new Set());
  };

  const handleBulkDelete = async () => {
    if (selectedTokenIds.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    const selectedTokens = tokens.filter((token) =>
      selectedTokenIds.has(token.id)
    );

    const confirmed = window.confirm(
      `Delete ${selectedTokens.length} token(s)?\n\n${selectedTokens.map((t) => t.token_name || 'Unknown').join(', ')}`
    );

    if (!confirmed) return;

    // Delete all selected tokens
    const deletePromises = Array.from(selectedTokenIds).map((id) =>
      fetch(`${API_BASE_URL}/api/tokens/${id}`, {
        method: 'DELETE',
        cache: 'no-store'
      })
    );

    try {
      await Promise.all(deletePromises);
      toast.success(`Deleted ${selectedTokenIds.size} token(s)`);

      // Optimistically update UI
      selectedTokenIds.forEach((id) => {
        if (onDelete) {
          onDelete(id);
        }
      });

      setSelectedTokenIds(new Set());

      // Refresh to sync with server
      router.refresh();
    } catch (error) {
      toast.error('Failed to delete some tokens. Please try again.');
      router.refresh();
    }
  };

  // Merge tokens with local market cap updates for instant UI feedback
  const tokensWithUpdates = useMemo(() => {
    return tokens.map((token) => {
      const update = marketCapUpdates.get(token.id);
      if (update) {
        return {
          ...token,
          market_cap_usd_current: update.market_cap_usd_current,
          market_cap_updated_at: update.market_cap_updated_at,
          market_cap_ath: update.market_cap_ath,
          market_cap_ath_timestamp: update.market_cap_ath_timestamp
        };
      }
      return token;
    });
  }, [tokens, marketCapUpdates]);

  const columns = useMemo(
    () =>
      createColumns(
        handleViewDetails,
        handleDelete,
        handleRefreshMarketCap,
        handleRefreshAllMarketCaps,
        refreshingMarketCaps,
        refreshingAll,
        isCompactMode,
        apiSettings
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isCompactMode, refreshingMarketCaps, refreshingAll, apiSettings, handleRefreshAllMarketCaps]
  );

  const table = useReactTable({
    data: tokensWithUpdates,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: {
      pagination: {
        pageSize: 50
      }
    },
    state: {
      globalFilter
    },
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: (row, _columnId, filterValue) => {
      const search = filterValue.toLowerCase();
      // Search in token address, token name, token symbol, and wallet addresses
      const tokenData = row.original;
      return !!(
        tokenData.token_address?.toLowerCase().includes(search) ||
        tokenData.token_name?.toLowerCase().includes(search) ||
        tokenData.token_symbol?.toLowerCase().includes(search) ||
        tokenData.wallet_addresses?.some((addr) =>
          addr.toLowerCase().includes(search)
        )
      );
    }
  });

  const rows = table.getRowModel().rows;
  const totalRows = rows.length;
  const baseRowHeight = isCompactMode ? 52 : 72;
  const overscan = 6;
  const visibleCount =
    viewportHeight > 0
      ? Math.ceil(viewportHeight / Math.max(baseRowHeight, 1)) + overscan
      : totalRows;
  const startIndex = Math.max(
    0,
    Math.floor(scrollTop / Math.max(baseRowHeight, 1)) - overscan
  );
  const endIndex = Math.min(totalRows, startIndex + visibleCount);
  const visibleRows = rows.slice(startIndex, endIndex);
  const paddingTop = startIndex * baseRowHeight;
  const paddingBottom = Math.max(0, (totalRows - endIndex) * baseRowHeight);

  // Update table instance reference when table changes
  useEffect(() => {
    setTableInstance(table);
  }, [table]);

  return (
    <>
      <div className='space-y-4'>
        {/* Search Input */}
        <div className='flex items-center gap-2'>
          <div className='relative flex-1'>
            <Search className='text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2' />
            <Input
              placeholder='Search by token address or wallet address...'
              value={globalFilter ?? ''}
              onChange={(e) => setGlobalFilter(e.target.value)}
              className='pl-10'
            />
          </div>
        </div>

        {/* Selection Control Panel */}
        {selectedTokenIds.size > 0 && (
          <div className='bg-primary/10 border-primary/20 sticky top-0 z-10 flex items-center justify-center gap-2 rounded-md border p-2 backdrop-blur-sm'>
            <span className='text-primary text-sm font-medium'>
              {selectedTokenIds.size} token
              {selectedTokenIds.size !== 1 ? 's' : ''} selected
            </span>
            <Button
              variant='outline'
              size='sm'
              onClick={handleRefreshSelectedMarketCaps}
              className='h-7 gap-1 text-xs'
              disabled={refreshingAll}
            >
              <RefreshCw
                className={cn('h-3 w-3', refreshingAll && 'animate-spin')}
              />
              Refresh Market Caps
            </Button>
            <Button
              variant='outline'
              size='sm'
              onClick={handleBulkDownload}
              className='h-7 gap-1 text-xs'
            >
              <Download className='h-3 w-3' />
              Download
            </Button>
            <Button
              variant='destructive'
              size='sm'
              onClick={handleBulkDelete}
              className='h-7 gap-1 text-xs'
            >
              <Trash2 className='h-3 w-3' />
              Delete
            </Button>
            <Button
              variant='outline'
              size='sm'
              onClick={() => setSelectedTokenIds(new Set())}
              className='h-7 text-xs'
            >
              Deselect All
            </Button>
          </div>
        )}

        <div className='overflow-hidden rounded-md border'>
          <div
            className='max-h-[calc(100vh-300px)] max-w-full overflow-auto'
            ref={tableContainerRef}
            onScroll={handleScroll}
          >
            <Table className='w-full'>
              <TableHeader className='bg-background sticky top-0 z-10 shadow-sm'>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id} className='border-b-2'>
                    {headerGroup.headers.map((header) => (
                      <TableHead
                        key={header.id}
                        className={cn(
                          'bg-background whitespace-nowrap transition-all duration-300',
                          isCompactMode
                            ? 'px-2 py-2 text-xs'
                            : 'px-3 py-3 text-sm'
                        )}
                      >
                        {header.isPlaceholder
                          ? null
                          : flexRender(
                              header.column.columnDef.header,
                              header.getContext()
                            )}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {totalRows ? (
                  <>
                    {paddingTop > 0 && (
                      <TableRow aria-hidden='true'>
                        <TableCell
                          colSpan={columns.length}
                          className='p-0'
                          style={{ height: paddingTop }}
                        />
                      </TableRow>
                    )}
                    {visibleRows.map((row) => (
                      <MemoizedTableRow
                        key={row.id}
                        row={row}
                        isCompactMode={isCompactMode}
                        isSelected={selectedTokenIds.has(row.original.id)}
                        handleRowClick={handleRowClick}
                        handleRowHover={handleRowHover}
                      />
                    ))}
                    {paddingBottom > 0 && (
                      <TableRow aria-hidden='true'>
                        <TableCell
                          colSpan={columns.length}
                          className='p-0'
                          style={{ height: paddingBottom }}
                        />
                      </TableRow>
                    )}
                  </>
                ) : (
                  <TableRow>
                    <TableCell
                      colSpan={columns.length}
                      className='h-24 text-center'
                    >
                      No results.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>
        <div className='flex items-center justify-end space-x-2'>
          <Button
            variant='outline'
            size='sm'
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>

      {/* Token Details Modal */}
      <TokenDetailsModal
        token={selectedToken}
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </>
  );
}
