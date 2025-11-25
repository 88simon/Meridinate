'use client';

import React, {
  useEffect,
  useState,
  useRef,
  useMemo,
  useCallback,
  startTransition,
  useContext
} from 'react';
import dynamic from 'next/dynamic';
import Image from 'next/image';
import {
  getTokens,
  getMultiTokenWallets,
  TokensResponse,
  MultiTokenWalletsResponse,
  refreshWalletBalances,
  getSolscanSettings,
  buildSolscanUrl,
  SolscanSettings,
  API_BASE_URL
} from '@/lib/api';
import { shouldLog } from '@/lib/debug';
import { TokensTable } from './tokens-table';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { StatusBar } from '@/components/status-bar';
import { WalletTagsProvider } from '@/contexts/WalletTagsContext';
import { useAnalysisNotifications } from '@/hooks/useAnalysisNotifications';
import { ADDITIONAL_TAGS_DISPLAY } from '@/lib/wallet-tags';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';

// Lazy load heavy components to defer loading until needed
const Calendar = dynamic(
  () =>
    import('@/components/ui/calendar').then((mod) => ({
      default: mod.Calendar
    })),
  { ssr: false }
);
const WalletTags = dynamic(
  () =>
    import('@/components/wallet-tags').then((mod) => ({
      default: mod.WalletTags
    })),
  { ssr: false }
);
const AdditionalTagsPopover = dynamic(
  () =>
    import('@/components/additional-tags').then((mod) => ({
      default: mod.AdditionalTagsPopover
    })),
  { ssr: false }
);
const WalletTagLabels = dynamic(
  () =>
    import('@/components/wallet-tag-labels').then((mod) => ({
      default: mod.WalletTagLabels
    })),
  { ssr: false }
);
const Popover = dynamic(
  () =>
    import('@/components/ui/popover').then((mod) => ({ default: mod.Popover })),
  { ssr: false }
);
const PopoverContent = dynamic(
  () =>
    import('@/components/ui/popover').then((mod) => ({
      default: mod.PopoverContent
    })),
  { ssr: false }
);
const PopoverTrigger = dynamic(
  () =>
    import('@/components/ui/popover').then((mod) => ({
      default: mod.PopoverTrigger
    })),
  { ssr: false }
);

// Lazy load icons - only load when component renders
const Copy = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.Copy })),
  { ssr: false }
);
const Twitter = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.Twitter })),
  { ssr: false }
);
const CalendarIcon = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.CalendarIcon })),
  { ssr: false }
);
const X = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.X })),
  { ssr: false }
);
const ChevronLeft = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.ChevronLeft })),
  { ssr: false }
);
const ChevronRight = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.ChevronRight })),
  { ssr: false }
);
const ChevronDown = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.ChevronDown })),
  { ssr: false }
);
const ChevronUp = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.ChevronUp })),
  { ssr: false }
);
const RefreshCw = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.RefreshCw })),
  { ssr: false }
);
const Tags = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.Tags })),
  { ssr: false }
);
const Info = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.Info })),
  { ssr: false }
);
const Filter = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.Filter })),
  { ssr: false }
);
const Search = dynamic(
  () => import('lucide-react').then((mod) => ({ default: mod.Search })),
  { ssr: false }
);

// Lazy load the wallet top holders modal
const WalletTopHoldersModal = dynamic(
  () =>
    import('./wallet-top-holders-modal').then((mod) => ({
      default: mod.WalletTopHoldersModal
    })),
  { ssr: false }
);

// No longer using Framer Motion - replaced with CSS transitions for better performance

// Bulk Tags Popover Component
function BulkTagsPopover({
  selectedWallets,
  onTagsApplied
}: {
  selectedWallets: string[];
  onTagsApplied: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [action, setAction] = useState<'add' | 'remove'>('add');

  const toggleTag = (tag: string) => {
    const newSet = new Set(selectedTags);
    if (newSet.has(tag)) {
      newSet.delete(tag);
    } else {
      newSet.add(tag);
    }
    setSelectedTags(newSet);
  };

  const applyTags = async () => {
    if (selectedTags.size === 0) {
      toast.error('Please select at least one tag');
      return;
    }

    setLoading(true);
    try {
      const { addWalletTag, removeWalletTag } = await import('@/lib/api');

      let successCount = 0;
      let failCount = 0;

      for (const walletAddress of selectedWallets) {
        for (const tag of Array.from(selectedTags)) {
          try {
            if (action === 'add') {
              await addWalletTag(walletAddress, tag, false);
            } else {
              await removeWalletTag(walletAddress, tag);
            }
            successCount++;
          } catch (error) {
            failCount++;
            // Silent failure - will report count at the end
          }
        }
      }

      // Trigger refresh events for all wallets
      selectedWallets.forEach((walletAddress) => {
        window.dispatchEvent(
          new CustomEvent('walletTagsChanged', { detail: { walletAddress } })
        );
      });

      if (failCount === 0) {
        toast.success(
          `${action === 'add' ? 'Added' : 'Removed'} ${selectedTags.size} tag(s) ${action === 'add' ? 'to' : 'from'} ${selectedWallets.length} wallet(s)`
        );
      } else {
        toast.warning(
          `Completed with ${successCount} success(es) and ${failCount} failure(s)`
        );
      }

      onTagsApplied();
      setSelectedTags(new Set());
    } catch (error: any) {
      toast.error(error.message || 'Failed to apply tags');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className='space-y-4'>
      <div>
        <h4 className='mb-3 text-sm font-semibold'>Batch Tag Management</h4>
        <p className='text-muted-foreground mb-3 text-xs'>
          {action === 'add' ? 'Add' : 'Remove'} tags{' '}
          {action === 'add' ? 'to' : 'from'} {selectedWallets.length} selected
          wallet(s)
        </p>
      </div>

      {/* Action Toggle */}
      <div className='flex gap-2'>
        <Button
          variant={action === 'add' ? 'default' : 'outline'}
          size='sm'
          onClick={() => setAction('add')}
          className='h-8 flex-1 text-xs'
        >
          Add Tags
        </Button>
        <Button
          variant={action === 'remove' ? 'default' : 'outline'}
          size='sm'
          onClick={() => setAction('remove')}
          className='h-8 flex-1 text-xs'
        >
          Remove Tags
        </Button>
      </div>

      {/* Tag Selection */}
      <div className='space-y-2'>
        {ADDITIONAL_TAGS_DISPLAY.map((tag) => (
          <label key={tag} className='flex cursor-pointer items-center gap-2'>
            <input
              type='checkbox'
              checked={selectedTags.has(tag)}
              onChange={() => toggleTag(tag)}
              disabled={loading}
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-sm'>{tag}</span>
          </label>
        ))}
      </div>

      {/* Apply Button */}
      <Button
        onClick={applyTags}
        disabled={loading || selectedTags.size === 0}
        className='w-full'
        size='sm'
      >
        {loading
          ? 'Applying...'
          : `${action === 'add' ? 'Add' : 'Remove'} ${selectedTags.size > 0 ? `${selectedTags.size} Tag(s)` : 'Tags'}`}
      </Button>
    </div>
  );
}

// Search Help Popover Component
function SearchHelpPopover() {
  return (
    <div className='w-80 space-y-3 text-sm'>
      <div>
        <h4 className='mb-2 font-semibold'>🔍 Search Guide</h4>
        <p className='text-muted-foreground text-xs'>
          Type anything to search all fields, or use smart prefixes for precision.
        </p>
      </div>

      <div className='space-y-2'>
        <div>
          <div className='mb-1 text-xs font-medium'>Smart Prefixes</div>
          <div className='bg-muted space-y-1 rounded-md p-2 font-mono text-xs'>
            <div>
              <span className='text-primary'>token:</span>
              <span className='text-muted-foreground'>Ant</span>
              <span className='ml-2 text-[10px]'>→ Search token names</span>
            </div>
            <div>
              <span className='text-primary'>tag:</span>
              <span className='text-muted-foreground'>bot</span>
              <span className='ml-2 text-[10px]'>→ Search wallet tags</span>
            </div>
            <div>
              <span className='text-primary'>wallet:</span>
              <span className='text-muted-foreground'>5e8S...</span>
              <span className='ml-2 text-[10px]'>→ Search addresses</span>
            </div>
            <div>
              <span className='text-primary'>gem</span>
              <span className='text-muted-foreground'> / </span>
              <span className='text-primary'>dud</span>
              <span className='ml-2 text-[10px]'>→ Token status</span>
            </div>
          </div>
        </div>

        <div>
          <div className='mb-1 text-xs font-medium'>Combine Terms</div>
          <div className='bg-muted space-y-1 rounded-md p-2 font-mono text-xs'>
            <div className='text-muted-foreground'>gem token:Ant</div>
            <div className='text-muted-foreground'>tag:bot tag:whale</div>
          </div>
        </div>

        <div>
          <div className='mb-1 text-xs font-medium'>Basic Search</div>
          <div className='text-muted-foreground text-xs'>
            Without prefixes, searches all fields at once.
          </div>
        </div>
      </div>
    </div>
  );
}

// Fuzzy match helper - calculates similarity between two strings (0-1)
function fuzzyMatch(query: string, target: string): number {
  const q = query.toLowerCase();
  const t = target.toLowerCase();

  // Exact match
  if (t.includes(q)) return 1;

  // Calculate Levenshtein distance-like similarity
  let matches = 0;
  let lastIndex = -1;

  for (const char of q) {
    const index = t.indexOf(char, lastIndex + 1);
    if (index > lastIndex) {
      matches++;
      lastIndex = index;
    }
  }

  const similarity = matches / q.length;

  // Boost score if starts with query
  if (t.startsWith(q)) {
    return Math.min(similarity + 0.3, 1);
  }

  return similarity;
}

// Filter Popover Component for Multi-Token Early Wallets Table
function MTWTFilterPopover({
  filters,
  onChange,
  onClear
}: {
  filters: {
    walletTags: string[];
    tokenStatus: {
      hasGems: boolean;
      hasDuds: boolean;
      hasUntagged: boolean;
      allGems: boolean;
      allDuds: boolean;
    };
    balanceRange: {
      min: number | null;
      max: number | null;
    };
    tokenCountRange: {
      min: number | null;
      max: number | null;
    };
    topHolder: {
      isTopHolder: boolean;
      top5Only: boolean;
    };
  };
  onChange: (filters: any) => void;
  onClear: () => void;
}) {
  return (
    <div className='w-80 space-y-4'>
      <div className='flex items-center justify-between'>
        <h4 className='text-sm font-semibold'>Filters</h4>
        <Button
          variant='ghost'
          size='sm'
          onClick={onClear}
          className='h-7 px-2 text-xs'
        >
          Clear All
        </Button>
      </div>

      {/* Wallet Tags Filter */}
      <div className='space-y-2'>
        <label className='text-xs font-medium'>🏷️ Wallet Tags</label>
        <div className='space-y-1.5'>
          {ADDITIONAL_TAGS_DISPLAY.map((tag) => (
            <label key={tag} className='flex cursor-pointer items-center gap-2 text-sm'>
              <input
                type='checkbox'
                checked={filters.walletTags.includes(tag)}
                onChange={(e) => {
                  const newTags = e.target.checked
                    ? [...filters.walletTags, tag]
                    : filters.walletTags.filter((t) => t !== tag);
                  onChange({
                    ...filters,
                    walletTags: newTags
                  });
                }}
                className='h-4 w-4 rounded border-gray-300'
              />
              <span className='text-xs'>{tag}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Token Status Filter */}
      <div className='space-y-2'>
        <label className='text-xs font-medium'>💎 Token Status</label>
        <div className='space-y-1.5'>
          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={filters.tokenStatus.hasGems}
              onChange={(e) =>
                onChange({
                  ...filters,
                  tokenStatus: {
                    ...filters.tokenStatus,
                    hasGems: e.target.checked
                  }
                })
              }
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-xs'>Has GEMs (at least one)</span>
          </label>
          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={filters.tokenStatus.hasDuds}
              onChange={(e) =>
                onChange({
                  ...filters,
                  tokenStatus: {
                    ...filters.tokenStatus,
                    hasDuds: e.target.checked
                  }
                })
              }
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-xs'>Has DUDs (at least one)</span>
          </label>
          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={filters.tokenStatus.hasUntagged}
              onChange={(e) =>
                onChange({
                  ...filters,
                  tokenStatus: {
                    ...filters.tokenStatus,
                    hasUntagged: e.target.checked
                  }
                })
              }
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-xs'>Has untagged tokens</span>
          </label>
          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={filters.tokenStatus.allGems}
              onChange={(e) =>
                onChange({
                  ...filters,
                  tokenStatus: {
                    ...filters.tokenStatus,
                    allGems: e.target.checked
                  }
                })
              }
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-xs'>ALL tokens are GEMs</span>
          </label>
          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={filters.tokenStatus.allDuds}
              onChange={(e) =>
                onChange({
                  ...filters,
                  tokenStatus: {
                    ...filters.tokenStatus,
                    allDuds: e.target.checked
                  }
                })
              }
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-xs'>ALL tokens are DUDs</span>
          </label>
        </div>
      </div>

      {/* Balance Range Filter */}
      <div className='space-y-2'>
        <label className='text-xs font-medium'>💰 Balance (USD)</label>
        <div className='flex gap-2'>
          <input
            type='number'
            placeholder='Min'
            value={filters.balanceRange.min ?? ''}
            onChange={(e) =>
              onChange({
                ...filters,
                balanceRange: {
                  ...filters.balanceRange,
                  min: e.target.value ? parseFloat(e.target.value) : null
                }
              })
            }
            className='h-8 w-full rounded border px-2 text-xs'
          />
          <input
            type='number'
            placeholder='Max'
            value={filters.balanceRange.max ?? ''}
            onChange={(e) =>
              onChange({
                ...filters,
                balanceRange: {
                  ...filters.balanceRange,
                  max: e.target.value ? parseFloat(e.target.value) : null
                }
              })
            }
            className='h-8 w-full rounded border px-2 text-xs'
          />
        </div>
        <div className='flex flex-wrap gap-1'>
          <Button
            variant='outline'
            size='sm'
            onClick={() =>
              onChange({
                ...filters,
                balanceRange: { min: 1000, max: null }
              })
            }
            className='h-6 px-2 text-[10px]'
          >
            &gt;$1k
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={() =>
              onChange({
                ...filters,
                balanceRange: { min: 10000, max: null }
              })
            }
            className='h-6 px-2 text-[10px]'
          >
            &gt;$10k
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={() =>
              onChange({
                ...filters,
                balanceRange: { min: 100000, max: null }
              })
            }
            className='h-6 px-2 text-[10px]'
          >
            &gt;$100k
          </Button>
        </div>
      </div>

      {/* Token Count Range Filter */}
      <div className='space-y-2'>
        <label className='text-xs font-medium'>🪙 Number of Tokens</label>
        <div className='flex gap-2'>
          <input
            type='number'
            placeholder='Min'
            value={filters.tokenCountRange.min ?? ''}
            onChange={(e) =>
              onChange({
                ...filters,
                tokenCountRange: {
                  ...filters.tokenCountRange,
                  min: e.target.value ? parseInt(e.target.value) : null
                }
              })
            }
            className='h-8 w-full rounded border px-2 text-xs'
          />
          <input
            type='number'
            placeholder='Max'
            value={filters.tokenCountRange.max ?? ''}
            onChange={(e) =>
              onChange({
                ...filters,
                tokenCountRange: {
                  ...filters.tokenCountRange,
                  max: e.target.value ? parseInt(e.target.value) : null
                }
              })
            }
            className='h-8 w-full rounded border px-2 text-xs'
          />
        </div>
        <div className='flex flex-wrap gap-1'>
          <Button
            variant='outline'
            size='sm'
            onClick={() =>
              onChange({
                ...filters,
                tokenCountRange: { min: 2, max: null }
              })
            }
            className='h-6 px-2 text-[10px]'
          >
            2+
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={() =>
              onChange({
                ...filters,
                tokenCountRange: { min: 5, max: null }
              })
            }
            className='h-6 px-2 text-[10px]'
          >
            5+
          </Button>
          <Button
            variant='outline'
            size='sm'
            onClick={() =>
              onChange({
                ...filters,
                tokenCountRange: { min: 10, max: null }
              })
            }
            className='h-6 px-2 text-[10px]'
          >
            10+
          </Button>
        </div>
      </div>

      {/* Top Holder Filter */}
      <div className='space-y-2'>
        <label className='text-xs font-medium'>🔝 Top Holder Status</label>
        <div className='space-y-1.5'>
          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={filters.topHolder.isTopHolder}
              onChange={(e) =>
                onChange({
                  ...filters,
                  topHolder: {
                    ...filters.topHolder,
                    isTopHolder: e.target.checked
                  }
                })
              }
              className='h-4 w-4 rounded border-gray-300'
            />
            <span className='text-xs'>Is top holder (any token)</span>
          </label>
        </div>
      </div>
    </div>
  );
}

// Filter interface and defaults for Multi-Token Early Wallets Table
interface MTWTFilters {
  walletTags: string[];
  tokenStatus: {
    hasGems: boolean;
    hasDuds: boolean;
    hasUntagged: boolean;
    allGems: boolean;
    allDuds: boolean;
  };
  balanceRange: {
    min: number | null;
    max: number | null;
  };
  tokenCountRange: {
    min: number | null;
    max: number | null;
  };
  topHolder: {
    isTopHolder: boolean;
    top5Only: boolean;
  };
}

const DEFAULT_MTWT_FILTERS: MTWTFilters = {
  walletTags: [],
  tokenStatus: {
    hasGems: false,
    hasDuds: false,
    hasUntagged: false,
    allGems: false,
    allDuds: false
  },
  balanceRange: {
    min: null,
    max: null
  },
  tokenCountRange: {
    min: null,
    max: null
  },
  topHolder: {
    isTopHolder: false,
    top5Only: false
  }
};

export default function TokensPage() {
  const [data, setData] = useState<TokensResponse | null>(null);
  const [multiWallets, setMultiWallets] =
    useState<MultiTokenWalletsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  const [hasActiveJobs, setHasActiveJobs] = useState(false);
  const [pollsSinceLastActive, setPollsSinceLastActive] = useState(0);
  const [dateRange, setDateRange] = useState<{
    from: Date | undefined;
    to: Date | undefined;
  }>({ from: undefined, to: undefined });
  const hasInitializedPolling = useRef(false);

  // Solscan settings state
  const [solscanSettings, setSolscanSettings] = useState<SolscanSettings>({
    activity_type: 'ACTIVITY_SPL_TRANSFER',
    exclude_amount_zero: 'true',
    remove_spam: 'true',
    value: '100',
    token_address: 'So11111111111111111111111111111111111111111',
    page_size: '10'
  });

  // Multi-token wallet panel state
  const [isWalletPanelExpanded, setIsWalletPanelExpanded] = useState(false);
  const [walletPage, setWalletPage] = useState(0);
  const [selectedWallets, setSelectedWallets] = useState<Set<string>>(
    new Set()
  );
  const walletsPerPage = 5;

  // Sorting state for multi-token early wallets table
  type SortColumn = 'address' | 'balance' | 'tokens' | 'new';
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Virtualization state for multi-token wallet table
  const walletContainerRef = useRef<HTMLDivElement>(null);
  const [walletScrollTop, setWalletScrollTop] = useState(0);
  const [walletViewportHeight, setWalletViewportHeight] = useState(0);

  // Top Holders modal state
  const [selectedWalletForTopHolders, setSelectedWalletForTopHolders] = useState<string | null>(null);
  const [isWalletTopHoldersModalOpen, setIsWalletTopHoldersModalOpen] = useState(false);
  const [topHolderCounts, setTopHolderCounts] = useState<Map<string, number>>(new Map());

  // Filter state for Multi-Token Early Wallets Table
  const [mtwFilters, setMtwFilters] = useState<MTWTFilters>(DEFAULT_MTWT_FILTERS);
  const [isFilterPopoverOpen, setIsFilterPopoverOpen] = useState(false);

  // Wallet tags cache for filtering (fetched separately to avoid provider scope issues)
  const [walletTagsCache, setWalletTagsCache] = useState<Record<string, Array<{tag: string}>>>({});

  // Search state for Multi-Token Early Wallets Table
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchHelpOpen, setIsSearchHelpOpen] = useState(false);
  const searchDebounceRef = useRef<NodeJS.Timeout | null>(null);

  // Scroll to top button ref
  const mtwSectionRef = useRef<HTMLDivElement>(null);

  // Track latest refetch request to prevent race conditions
  const latestRefetchId = useRef(0);

  // Use API settings from context

  const fetchData = useCallback(() => {
    setLoading(true);
    // Use startTransition to defer non-urgent updates and avoid blocking paint
    startTransition(() => {
      Promise.all([getTokens(), getMultiTokenWallets(2)])
        .then(([tokensData, walletsData]) => {
          setData(tokensData);
          setMultiWallets(walletsData);
        })
        .catch(() => {
          setError(
            'Failed to load data. Make sure the FastAPI backend is running on localhost:5003'
          );
        })
        .finally(() => setLoading(false));
    });
  }, []);

  // Refetch only multi-token wallets (used after gem/dud updates)
  // Uses request ID tracking to prevent race conditions when rapidly clicking GEM/DUD buttons
  const refetchMultiWallets = useCallback(async () => {
    // Increment and capture the request ID for this fetch
    latestRefetchId.current += 1;
    const thisRequestId = latestRefetchId.current;

    try {
      const walletsData = await getMultiTokenWallets(2);

      // Only update state if this is still the most recent request
      // This prevents stale responses from overwriting newer data
      if (thisRequestId === latestRefetchId.current) {
        setMultiWallets(walletsData);
      }
    } catch (error) {
      console.error('Failed to refetch multi-token wallets:', error);
    }
  }, []);

  // WebSocket notifications for real-time analysis updates
  const handleAnalysisComplete = useCallback(() => {
    if (shouldLog()) {
    }
    // Refresh the tokens list when analysis completes
    fetchData();
  }, [fetchData]);

  useAnalysisNotifications(handleAnalysisComplete);

  const handleTokenDelete = (tokenId: number) => {
    // Optimistically update UI by removing the token from local state
    if (data) {
      setData({
        ...data,
        tokens: data.tokens.filter((token) => token.id !== tokenId),
        total: data.total - 1
      });
    }
  };

  // Scroll to top function for Multi-Token Early Wallets section
  const scrollToTop = useCallback(() => {
    if (mtwSectionRef.current) {
      mtwSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  // Note: buildSolscanUrl function is imported from @/lib/api

  useEffect(() => {
    // Fetch tokens and multi-token wallets from Flask API
    fetchData();

    // Request notification permission silently (no test notification on every refresh)
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then(() => {});
    }

    // Load Solscan settings from backend
    getSolscanSettings()
      .then(setSolscanSettings)
      .catch(() => {
        // Silently fail - will use defaults
      });

    // Poll for Solscan settings changes every 500ms for near-instant updates
    // Tab visibility-aware: pause polling when tab is hidden
    let settingsInterval: NodeJS.Timeout | null = null;

    const startSettingsPolling = () => {
      if (settingsInterval) return; // Already polling
      settingsInterval = setInterval(() => {
        if (!document.hidden) {
          getSolscanSettings()
            .then(setSolscanSettings)
            .catch(() => {
              // Silently fail
            });
        }
      }, 500);
    };

    const stopSettingsPolling = () => {
      if (settingsInterval) {
        clearInterval(settingsInterval);
        settingsInterval = null;
      }
    };

    // Start polling immediately
    startSettingsPolling();

    // Handle visibility changes
    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopSettingsPolling();
      } else {
        // Refresh settings immediately when tab becomes visible
        getSolscanSettings()
          .then(setSolscanSettings)
          .catch(() => {});
        startSettingsPolling();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      stopSettingsPolling();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchData]);

  // Poll for active analysis jobs and auto-refresh when they complete
  // Tab visibility-aware: pause polling when tab is hidden
  useEffect(() => {
    // Guard against React Strict Mode double-mounting
    if (hasInitializedPolling.current) return;
    hasInitializedPolling.current = true;

    const isFirstPollRef = { current: true };
    let pollInterval: NodeJS.Timeout | null = null;

    // Initialize lastJobId on mount to prevent showing old notifications
    const initializeLastJobId = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/analysis`);
        const analysisData = await response.json();

        if (analysisData.jobs && analysisData.jobs.length > 0) {
          const latestJob = analysisData.jobs[0];
          if (latestJob.status === 'completed') {
            setLastJobId(latestJob.job_id);
          }

          // Check if there are any active jobs
          const activeJobs = analysisData.jobs.some(
            (job: any) => job.status === 'queued' || job.status === 'processing'
          );
          setHasActiveJobs(activeJobs);
        }
      } catch (err) {}
    };

    const startAnalysisPolling = () => {
      if (pollInterval) return; // Already polling

      pollInterval = setInterval(async () => {
        // Skip the first poll since we already initialized
        if (isFirstPollRef.current) {
          isFirstPollRef.current = false;
          return;
        }

        // Skip polling if tab is hidden
        if (document.hidden) {
          return;
        }

        // OPTIMIZATION: Only poll if there are active jobs or if we haven't checked recently
        // Check every 10th poll even when no active jobs (to catch new analyses started from AHK)
        if (!hasActiveJobs && pollsSinceLastActive < 10) {
          setPollsSinceLastActive((prev) => prev + 1);
          return;
        }

        // Reset counter when we do poll
        setPollsSinceLastActive(0);

        try {
          const response = await fetch(`${API_BASE_URL}/analysis`);
          const analysisData = await response.json();

          if (analysisData.jobs && analysisData.jobs.length > 0) {
            const latestJob = analysisData.jobs[0];

            // Update hasActiveJobs state
            const activeJobs = analysisData.jobs.some(
              (job: any) =>
                job.status === 'queued' || job.status === 'processing'
            );
            setHasActiveJobs(activeJobs);

            // Check if there's a new completed job we haven't seen yet
            if (
              latestJob.status === 'completed' &&
              latestJob.job_id !== lastJobId
            ) {
              setLastJobId(latestJob.job_id);
              // Refresh the tokens list without showing loading state
              Promise.all([getTokens(), getMultiTokenWallets(2)])
                .then(([tokensData, walletsData]) => {
                  setData(tokensData);
                  setMultiWallets(walletsData);

                  const tokenName = latestJob.token_name || 'Token';
                  toast.success(`Analysis complete: ${tokenName}`);

                  // Show desktop notification if permission granted
                  if (
                    'Notification' in window &&
                    Notification.permission === 'granted'
                  ) {
                    const notification = new Notification(
                      'Analysis Complete ✓',
                      {
                        body: `${tokenName} analysis finished\nClick to view results`,
                        icon: '/favicon.ico',
                        tag: 'analysis-complete',
                        requireInteraction: false,
                        silent: true // No sound
                      }
                    );

                    // Auto-close notification after 0.75 seconds
                    setTimeout(() => notification.close(), 750);

                    // Focus window when notification is clicked
                    notification.onclick = () => {
                      window.focus();
                      notification.close();
                    };
                  }
                })
                .catch(() => {});
            }
          } else {
            // No jobs at all, stop polling
            setHasActiveJobs(false);
          }
        } catch (err) {
          // Silently fail - don't spam errors if backend is temporarily unavailable
        }
      }, 3000); // Poll every 3 seconds
    };

    const stopAnalysisPolling = () => {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    };

    // Initialize and start polling
    initializeLastJobId();
    startAnalysisPolling();

    // Handle visibility changes
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Keep interval running but skip polls (allows intelligent polling logic to continue)
        // The interval itself checks document.hidden
      } else {
        // When tab becomes visible, check immediately if there are active jobs
        if (hasActiveJobs) {
          fetchData();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      stopAnalysisPolling();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastJobId, hasActiveJobs]);

  // Collect all unique wallet addresses for batch tag fetching
  // MUST be before early returns to comply with Rules of Hooks
  const allWalletAddresses = useMemo(() => {
    const addresses = new Set<string>();

    // Add wallets from multi-token wallets
    if (multiWallets?.wallets) {
      multiWallets.wallets.forEach((wallet) => {
        addresses.add(wallet.wallet_address);
      });
    }

    return Array.from(addresses);
  }, [multiWallets]);

  // Wallet panel helpers
  const handleWalletRowClick = (
    walletAddress: string,
    event: React.MouseEvent
  ) => {
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

    setSelectedWallets((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(walletAddress)) {
        newSet.delete(walletAddress);
      } else {
        newSet.add(walletAddress);
      }
      return newSet;
    });
  };

  const handleRefreshBalances = async (walletAddressesOverride?: string[]) => {
    const walletAddresses =
      walletAddressesOverride || Array.from(selectedWallets);

    if (walletAddresses.length === 0) {
      toast.error('No wallets selected');
      return;
    }

    toast.info(
      `Refreshing balances for ${walletAddresses.length} wallet(s)...`
    );

    try {
      const response = await refreshWalletBalances(walletAddresses);

      // Refresh the multi-token wallets data to show updated balances
      const walletsData = await getMultiTokenWallets(2);
      setMultiWallets(walletsData);

      toast.success(
        `Refreshed ${response.successful} of ${response.total_wallets} wallet(s) (${response.api_credits_used} API credits used)`
      );

      // Clear selection after refresh only if using selected wallets (not single wallet)
      if (!walletAddressesOverride) {
        setSelectedWallets(new Set());
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to refresh balances');
    }
  };

  const handleRefreshAllBalances = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const allVisibleAddresses = walletsToDisplay.map((w) => w.wallet_address);
    await handleRefreshBalances(allVisibleAddresses);
  };

  // Handle wallet container scroll for virtualization
  const handleWalletScroll = useCallback(() => {
    if (walletContainerRef.current) {
      setWalletScrollTop(walletContainerRef.current.scrollTop);
    }
  }, []);

  // Update viewport height when container size changes
  useEffect(() => {
    if (walletContainerRef.current) {
      const updateViewportHeight = () => {
        setWalletViewportHeight(walletContainerRef.current?.clientHeight ?? 0);
      };
      updateViewportHeight();
      window.addEventListener('resize', updateViewportHeight);
      return () => window.removeEventListener('resize', updateViewportHeight);
    }
  }, [isWalletPanelExpanded]);

  // Fetch top holder counts for all multi-token wallets
  useEffect(() => {
    if (!multiWallets?.wallets) return;

    const fetchTopHolderCounts = async () => {
      const walletAddresses = multiWallets.wallets.map(w => w.wallet_address);

      try {
        // Use batch endpoint - single request instead of N requests
        const response = await fetch(
          `${API_BASE_URL}/wallets/batch-top-holder-counts`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wallet_addresses: walletAddresses })
          }
        );

        if (response.ok) {
          const data = await response.json();
          // Convert counts object to Map
          const newCounts = new Map<string, number>(
            Object.entries(data.counts)
          );
          setTopHolderCounts(newCounts);
        }
      } catch {
        // Silently fail - top holder counts are non-critical
      }
    };

    fetchTopHolderCounts();
  }, [multiWallets]);

  // Fetch wallet tags for filtering
  useEffect(() => {
    if (!multiWallets?.wallets || multiWallets.wallets.length === 0) return;

    const fetchWalletTags = async () => {
      const walletAddresses = multiWallets.wallets.map(w => w.wallet_address);

      try {
        const response = await fetch(`${API_BASE_URL}/wallets/batch-tags`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ addresses: walletAddresses })
        });

        if (!response.ok) {
          console.error('Failed to fetch wallet tags:', response.statusText);
          return;
        }

        const tagsData = await response.json();
        setWalletTagsCache(tagsData);
      } catch (error) {
        console.error('Error fetching wallet tags:', error);
      }
    };

    fetchWalletTags();
  }, [multiWallets]);

  // Load filters from localStorage on mount
  useEffect(() => {
    try {
      const savedFilters = localStorage.getItem('mtwFilters');
      if (savedFilters) {
        const parsed = JSON.parse(savedFilters);
        // Validate structure before applying
        if (parsed && typeof parsed === 'object' && parsed.tokenStatus) {
          setMtwFilters(parsed);
        } else {
          // Invalid structure, clear localStorage
          localStorage.removeItem('mtwFilters');
        }
      }
    } catch (error) {
      console.error('Failed to load filters from localStorage:', error);
      localStorage.removeItem('mtwFilters');
    }
  }, []);

  // Save filters to localStorage whenever they change
  useEffect(() => {
    try {
      localStorage.setItem('mtwFilters', JSON.stringify(mtwFilters));
    } catch (error) {
      console.error('Failed to save filters to localStorage:', error);
    }
  }, [mtwFilters]);

  // Sync filters with URL params on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlFiltersParam = params.get('mtwFilters');

    if (urlFiltersParam) {
      try {
        const urlFilters = JSON.parse(decodeURIComponent(urlFiltersParam));
        setMtwFilters(urlFilters);
      } catch (error) {
        console.error('Failed to parse filters from URL:', error);
      }
    }
  }, []);

  // Update URL params whenever filters change
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    // Only add to URL if filters are not default
    const hasActiveFilters = JSON.stringify(mtwFilters) !== JSON.stringify(DEFAULT_MTWT_FILTERS);

    if (hasActiveFilters) {
      params.set('mtwFilters', encodeURIComponent(JSON.stringify(mtwFilters)));
    } else {
      params.delete('mtwFilters');
    }

    const newUrl = params.toString() ? `?${params.toString()}` : window.location.pathname;
    window.history.replaceState({}, '', newUrl);
  }, [mtwFilters]);

  // Load search from localStorage on mount
  useEffect(() => {
    try {
      const savedSearch = localStorage.getItem('mtwSearch');
      if (savedSearch) {
        setSearchQuery(savedSearch);
      }
    } catch (error) {
      console.error('Failed to load search from localStorage:', error);
    }
  }, []);

  // Save search to localStorage whenever it changes
  useEffect(() => {
    try {
      if (searchQuery) {
        localStorage.setItem('mtwSearch', searchQuery);
      } else {
        localStorage.removeItem('mtwSearch');
      }
    } catch (error) {
      console.error('Failed to save search to localStorage:', error);
    }
  }, [searchQuery]);

  // Sync search with URL params on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlSearch = params.get('search');
    if (urlSearch) {
      setSearchQuery(decodeURIComponent(urlSearch));
    }
  }, []);

  // Update URL params whenever search changes
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    if (searchQuery.trim()) {
      params.set('search', encodeURIComponent(searchQuery));
    } else {
      params.delete('search');
    }

    const newUrl = params.toString() ? `?${params.toString()}` : window.location.pathname;
    window.history.replaceState({}, '', newUrl);
  }, [searchQuery]);

  // Sort handler for multi-token wallets table
  const handleSort = useCallback(
    (column: SortColumn) => {
      if (sortColumn === column) {
        // Toggle direction if clicking same column
        setSortDirection((prevDir) => (prevDir === 'asc' ? 'desc' : 'asc'));
      } else {
        // New column, default to descending
        setSortColumn(column);
        setSortDirection('desc');
      }
    },
    [sortColumn]
  );

  // Get all available wallet tags from context
  const allWalletTags = useMemo(() => {
    const tags = new Set<string>();
    if (multiWallets?.wallets) {
      // This will be populated from wallet tags context - for now use placeholder
      ADDITIONAL_TAGS_DISPLAY.forEach(tag => tags.add(tag));
    }
    return Array.from(tags);
  }, [multiWallets]);

  // Parse search query for smart prefixes
  const parsedSearch = useMemo(() => {
    if (!searchQuery.trim()) {
      return { tokens: [], tags: [], wallets: [], statuses: [], general: [] };
    }

    const tokens: string[] = [];
    const tags: string[] = [];
    const wallets: string[] = [];
    const statuses: ('gem' | 'dud')[] = [];
    const general: string[] = [];

    // Split by spaces but preserve quoted strings
    const terms = searchQuery.match(/(?:[^\s"]+|"[^"]*")+/g) || [];

    terms.forEach((term) => {
      const lower = term.toLowerCase();

      // Check for prefixes
      if (lower.startsWith('token:')) {
        tokens.push(term.substring(6).replace(/"/g, ''));
      } else if (lower.startsWith('tag:')) {
        tags.push(term.substring(4).replace(/"/g, ''));
      } else if (lower.startsWith('wallet:')) {
        wallets.push(term.substring(7).replace(/"/g, ''));
      } else if (lower === 'gem' || lower === 'dud') {
        statuses.push(lower as 'gem' | 'dud');
      } else {
        // No prefix - add to general search
        general.push(term.replace(/"/g, ''));
      }
    });

    return { tokens, tags, wallets, statuses, general };
  }, [searchQuery]);

  // Filtered wallets (applied before sorting)
  const filteredWallets = useMemo(() => {
    if (!multiWallets?.wallets) return [];

    const filtered = multiWallets.wallets.filter((wallet) => {
      // Search filter (applied first, combines with other filters using AND)
      if (searchQuery.trim()) {
        let passesSearch = false;

        // If there are any specific prefix searches, check those
        const hasSpecificSearch = parsedSearch.tokens.length > 0 ||
                                   parsedSearch.tags.length > 0 ||
                                   parsedSearch.wallets.length > 0 ||
                                   parsedSearch.statuses.length > 0;

        if (hasSpecificSearch) {
          // Token name search (OR logic for multiple token: terms)
          if (parsedSearch.tokens.length > 0) {
            // Split comma-separated token names string (backend sends string[], but it's comma-separated)
            const tokenNamesRaw = wallet.token_names as string[] | string;
            const tokenNamesArray = Array.isArray(tokenNamesRaw)
              ? tokenNamesRaw
              : (tokenNamesRaw as string).split(',').map((n: string) => n.trim());

            // Check if any search term matches any token name (with fuzzy matching)
            const hasMatch = parsedSearch.tokens.some(searchTerm =>
              tokenNamesArray.some((tokenName: string) => {
                const similarity = fuzzyMatch(searchTerm, tokenName);
                return similarity >= 0.7; // 70% similarity threshold
              })
            );

            if (hasMatch) {
              passesSearch = true;
            }
          }

          // Tag search (OR logic for multiple tag: terms)
          if (parsedSearch.tags.length > 0) {
            const walletTags = walletTagsCache[wallet.wallet_address] || [];
            const walletTagNames = walletTags.map(t => t.tag.toLowerCase());
            if (parsedSearch.tags.some(term => walletTagNames.includes(term.toLowerCase()))) {
              passesSearch = true;
            }
          }

          // Wallet address search (OR logic for multiple wallet: terms)
          if (parsedSearch.wallets.length > 0) {
            if (parsedSearch.wallets.some(term =>
              wallet.wallet_address.toLowerCase().includes(term.toLowerCase())
            )) {
              passesSearch = true;
            }
          }

          // Status search (gem/dud)
          if (parsedSearch.statuses.length > 0) {
            for (const status of parsedSearch.statuses) {
              if (status === 'gem' && wallet.gem_statuses.some(s => s === 'gem')) {
                passesSearch = true;
                break;
              }
              if (status === 'dud' && wallet.gem_statuses.some(s => s === 'dud')) {
                passesSearch = true;
                break;
              }
            }
          }
        }

        // General search (no prefix) - searches all fields (OR logic) with fuzzy matching
        if (parsedSearch.general.length > 0) {
          for (const term of parsedSearch.general) {
            // Search in token names with fuzzy matching
            const tokenNamesRaw = wallet.token_names as string[] | string;
            const tokenNamesArray = Array.isArray(tokenNamesRaw)
              ? tokenNamesRaw
              : (tokenNamesRaw as string).split(',').map((n: string) => n.trim());

            const hasTokenMatch = tokenNamesArray.some((tokenName: string) => {
              const similarity = fuzzyMatch(term, tokenName);
              return similarity >= 0.7;
            });

            if (hasTokenMatch) {
              passesSearch = true;
              break;
            }

            // Search in wallet address (exact partial match, no fuzzy)
            if (wallet.wallet_address.toLowerCase().includes(term.toLowerCase())) {
              passesSearch = true;
              break;
            }

            // Search in tags with fuzzy matching
            const walletTags = walletTagsCache[wallet.wallet_address] || [];
            const hasTagMatch = walletTags.some(t => {
              const similarity = fuzzyMatch(term, t.tag);
              return similarity >= 0.7;
            });

            if (hasTagMatch) {
              passesSearch = true;
              break;
            }

            // Search in gem/dud status
            const lowerTerm = term.toLowerCase();
            if (lowerTerm === 'gem' && wallet.gem_statuses.some(s => s === 'gem')) {
              passesSearch = true;
              break;
            }
            if (lowerTerm === 'dud' && wallet.gem_statuses.some(s => s === 'dud')) {
              passesSearch = true;
              break;
            }
          }
        }

        if (!passesSearch) {
          return false;
        }
      }

      // Wallet tags filter (OR logic within this category)
      if (mtwFilters.walletTags.length > 0) {
        const walletTags = walletTagsCache[wallet.wallet_address] || [];
        const walletTagNames = walletTags.map(t => t.tag.charAt(0).toUpperCase() + t.tag.slice(1));

        // Check if wallet has ANY of the selected tags (OR logic)
        const hasAnySelectedTag = mtwFilters.walletTags.some(selectedTag =>
          walletTagNames.includes(selectedTag)
        );

        if (!hasAnySelectedTag) {
          return false;
        }
      }

      // Token status filter (OR logic for each checkbox, AND across categories)
      const tokenStatusFilters = mtwFilters.tokenStatus;
      const hasAnyTokenStatusFilter =
        tokenStatusFilters.hasGems ||
        tokenStatusFilters.hasDuds ||
        tokenStatusFilters.hasUntagged ||
        tokenStatusFilters.allGems ||
        tokenStatusFilters.allDuds;

      if (hasAnyTokenStatusFilter) {
        let passesTokenStatus = false;

        // Check if wallet has at least one GEM
        if (tokenStatusFilters.hasGems) {
          const hasGem = wallet.gem_statuses.some(status => status === 'gem');
          if (hasGem) passesTokenStatus = true;
        }

        // Check if wallet has at least one DUD
        if (tokenStatusFilters.hasDuds) {
          const hasDud = wallet.gem_statuses.some(status => status === 'dud');
          if (hasDud) passesTokenStatus = true;
        }

        // Check if wallet has at least one untagged token
        if (tokenStatusFilters.hasUntagged) {
          const hasUntagged = wallet.gem_statuses.some(status => status === null);
          if (hasUntagged) passesTokenStatus = true;
        }

        // Check if ALL tokens are GEMs
        if (tokenStatusFilters.allGems) {
          const allGems = wallet.gem_statuses.every(status => status === 'gem');
          if (allGems && wallet.gem_statuses.length > 0) passesTokenStatus = true;
        }

        // Check if ALL tokens are DUDs
        if (tokenStatusFilters.allDuds) {
          const allDuds = wallet.gem_statuses.every(status => status === 'dud');
          if (allDuds && wallet.gem_statuses.length > 0) passesTokenStatus = true;
        }

        if (!passesTokenStatus) return false;
      }

      // Balance range filter (AND logic)
      if (mtwFilters.balanceRange.min !== null || mtwFilters.balanceRange.max !== null) {
        const balance = wallet.wallet_balance_usd ?? 0;

        if (mtwFilters.balanceRange.min !== null && balance < mtwFilters.balanceRange.min) {
          return false;
        }

        if (mtwFilters.balanceRange.max !== null && balance > mtwFilters.balanceRange.max) {
          return false;
        }
      }

      // Token count range filter (AND logic)
      if (mtwFilters.tokenCountRange.min !== null || mtwFilters.tokenCountRange.max !== null) {
        const tokenCount = wallet.token_count;

        if (mtwFilters.tokenCountRange.min !== null && tokenCount < mtwFilters.tokenCountRange.min) {
          return false;
        }

        if (mtwFilters.tokenCountRange.max !== null && tokenCount > mtwFilters.tokenCountRange.max) {
          return false;
        }
      }

      // Top holder filter (AND logic)
      if (mtwFilters.topHolder.isTopHolder || mtwFilters.topHolder.top5Only) {
        const topHolderCount = topHolderCounts.get(wallet.wallet_address) ?? 0;

        if (mtwFilters.topHolder.isTopHolder && topHolderCount === 0) {
          return false;
        }

        if (mtwFilters.topHolder.top5Only) {
          // For "top 5 only" we need to check if the wallet is in top 5 of any token
          // This is more complex - for now we'll just check if they're a top holder
          // TODO: Enhance this to actually check rank position
          if (topHolderCount === 0) return false;
        }
      }

      return true;
    });

    console.log('MTWT Filters:', {
      totalWallets: multiWallets.wallets.length,
      filteredWallets: filtered.length,
      activeFilters: mtwFilters
    });

    return filtered;
  }, [multiWallets, mtwFilters, topHolderCounts, walletTagsCache, parsedSearch, searchQuery]);

  // Sorted wallets (applied before pagination/virtualization)
  const sortedWallets = useMemo(() => {
    if (!filteredWallets.length) return [];

    const walletsCopy = [...filteredWallets];

    if (!sortColumn) return walletsCopy;

    walletsCopy.sort((a, b) => {
      let compareValue = 0;

      switch (sortColumn) {
        case 'address':
          // Sort by is_new first, then by address
          if (a.is_new && !b.is_new) compareValue = -1;
          else if (!a.is_new && b.is_new) compareValue = 1;
          else compareValue = a.wallet_address.localeCompare(b.wallet_address);
          break;

        case 'balance':
          const balanceA = a.wallet_balance_usd ?? 0;
          const balanceB = b.wallet_balance_usd ?? 0;
          compareValue = balanceA - balanceB;
          break;

        case 'tokens':
          compareValue = a.token_count - b.token_count;
          break;

        case 'new':
          // Sort by whether wallet has a new token
          const hasNewTokenA = a.marked_at_analysis_id !== null;
          const hasNewTokenB = b.marked_at_analysis_id !== null;
          if (hasNewTokenA && !hasNewTokenB) compareValue = -1;
          else if (!hasNewTokenA && hasNewTokenB) compareValue = 1;
          else compareValue = 0;
          break;
      }

      return sortDirection === 'asc' ? compareValue : -compareValue;
    });

    return walletsCopy;
  }, [filteredWallets, sortColumn, sortDirection]);

  // Pagination logic for multi-token wallets (collapsed mode)
  const walletsPaginated = useMemo(() => {
    if (!sortedWallets.length) return [];
    if (isWalletPanelExpanded) return sortedWallets;

    const start = walletPage * walletsPerPage;
    const end = start + walletsPerPage;
    return sortedWallets.slice(start, end);
  }, [sortedWallets, isWalletPanelExpanded, walletPage]);

  // Virtualization logic for expanded mode
  const { walletsToDisplay, walletPaddingTop, walletPaddingBottom } =
    useMemo(() => {
      if (!isWalletPanelExpanded || !sortedWallets.length) {
        return {
          walletsToDisplay: walletsPaginated,
          walletPaddingTop: 0,
          walletPaddingBottom: 0
        };
      }

      const allWallets = sortedWallets;
      const totalWallets = allWallets.length;
      const baseRowHeight = 60; // Average height per wallet row (compressed)
      const overscan = 5;
      const visibleCount =
        walletViewportHeight > 0
          ? Math.ceil(walletViewportHeight / Math.max(baseRowHeight, 1)) +
            overscan
          : totalWallets;
      const startIndex = Math.max(
        0,
        Math.floor(walletScrollTop / Math.max(baseRowHeight, 1)) - overscan
      );
      const endIndex = Math.min(totalWallets, startIndex + visibleCount);
      const visibleWallets = allWallets.slice(startIndex, endIndex);
      const paddingTop = startIndex * baseRowHeight;
      const paddingBottom = Math.max(
        0,
        (totalWallets - endIndex) * baseRowHeight
      );

      return {
        walletsToDisplay: visibleWallets,
        walletPaddingTop: paddingTop,
        walletPaddingBottom: paddingBottom
      };
    }, [
      sortedWallets,
      isWalletPanelExpanded,
      walletsPaginated,
      walletScrollTop,
      walletViewportHeight
    ]);

  const totalWalletPages = useMemo(() => {
    if (!sortedWallets.length) return 0;
    return Math.ceil(sortedWallets.length / walletsPerPage);
  }, [sortedWallets]);

  const formatWalletTimestamp = (timestamp?: string | null) => {
    if (!timestamp) return 'Not refreshed yet';
    const iso = timestamp.replace(' ', 'T') + 'Z';
    const date = new Date(iso);
    return `Updated ${date.toLocaleString()}`;
  };

  const getWalletTrend = (
    wallet: MultiTokenWalletsResponse['wallets'][number]
  ) => {
    const current = wallet.wallet_balance_usd;
    const previous = wallet.wallet_balance_usd_previous;
    if (current === null || current === undefined) return 'none';
    if (previous === null || previous === undefined) return 'none';
    if (current > previous) return 'up';
    if (current < previous) return 'down';
    return 'flat';
  };

  if (loading) {
    return (
      <WalletTagsProvider walletAddresses={allWalletAddresses}>
        <div className='flex h-full items-center justify-center'>
          <div className='text-center'>
            <div className='text-lg font-medium'>Loading tokens...</div>
            <div className='text-muted-foreground mt-2 text-sm'>
              Fetching data from Flask backend
            </div>
          </div>
        </div>
      </WalletTagsProvider>
    );
  }

  if (error || !data) {
    return (
      <WalletTagsProvider walletAddresses={allWalletAddresses}>
        <div className='flex h-full items-center justify-center'>
          <div className='text-center'>
            <div className='text-destructive text-lg font-medium'>Error</div>
            <div className='text-muted-foreground mt-2 text-sm'>
              {error || 'Failed to load tokens'}
            </div>
          </div>
        </div>
      </WalletTagsProvider>
    );
  }

  // Filter tokens by date range
  const filteredTokens = data.tokens.filter((token) => {
    // If no dates selected, show all tokens
    if (!dateRange.from && !dateRange.to) return true;

    const tokenDate = new Date(
      token.analysis_timestamp.replace(' ', 'T') + 'Z'
    );

    if (dateRange.from && dateRange.to) {
      const endOfDay = new Date(dateRange.to);
      endOfDay.setHours(23, 59, 59, 999);
      return tokenDate >= dateRange.from && tokenDate <= endOfDay;
    } else if (dateRange.from) {
      return tokenDate >= dateRange.from;
    } else if (dateRange.to) {
      const endOfDay = new Date(dateRange.to);
      endOfDay.setHours(23, 59, 59, 999);
      return tokenDate <= endOfDay;
    }

    return false;
  });

  return (
    <WalletTagsProvider walletAddresses={allWalletAddresses}>
      <div className='flex h-full flex-col space-y-4 pb-16'>
        <div className='flex items-center justify-between'>
          <div>
            <h1 className='text-xl font-bold tracking-tight'>
              Analyzed Tokens
            </h1>
            <p className='text-muted-foreground text-sm'>
              View and manage your analyzed Solana tokens
            </p>
          </div>
          <Button
            variant='outline'
            size='sm'
            onClick={() => {
              if (!('Notification' in window)) {
                toast.error('Notifications not supported in this browser');
                return;
              }

              if (Notification.permission !== 'granted') {
                toast.error(
                  `Permission: ${Notification.permission}. Please allow notifications.`
                );
                return;
              }

              try {
                const testNotif = new Notification('Test Notification', {
                  body: 'This is a test notification. Tab out to test!',
                  icon: '/favicon.ico',
                  tag: 'test-notif',
                  requireInteraction: false,
                  silent: false
                });

                testNotif.onshow = () =>
                  (testNotif.onclick = () => {
                    window.focus();
                  });
                testNotif.onerror = () =>
                  setTimeout(() => testNotif.close(), 5000);
                toast.success(
                  'Test notification created! Check if it appears.'
                );
              } catch (error: any) {
                toast.error(`Failed: ${error.message || 'Unknown error'}`);
              }
            }}
          >
            Test Notification
          </Button>
        </div>

        {/* Date Range Filter - Moved to top bar */}
        <div className='flex items-center gap-2'>
          {(dateRange.from || dateRange.to) && (
            <>
              <div className='text-muted-foreground text-sm'>
                Filtered: {filteredTokens.length} of {data.tokens.length} tokens
              </div>
              <Button
                variant='ghost'
                size='sm'
                className='h-6 w-6 p-0'
                onClick={() => setDateRange({ from: undefined, to: undefined })}
              >
                <X className='h-3 w-3' />
              </Button>
            </>
          )}
          <Popover>
            <PopoverTrigger asChild>
              <Button variant='outline' size='sm' className='h-8 gap-2'>
                <CalendarIcon className='h-4 w-4' />
                Filter by Date
              </Button>
            </PopoverTrigger>
            <PopoverContent className='w-auto p-0' align='start'>
              <div className='p-3'>
                <div className='mb-2 text-sm font-medium'>
                  Filter by Scan Date
                </div>
                <div className='space-y-2'>
                  <Calendar
                    mode='range'
                    selected={{ from: dateRange.from, to: dateRange.to }}
                    onSelect={(range: any) =>
                      setDateRange({ from: range?.from, to: range?.to })
                    }
                    numberOfMonths={1}
                    defaultMonth={new Date()}
                  />
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>

        {/* Multi-Token Early Wallets Section */}
        {multiWallets && multiWallets.total > 0 && (
          <div ref={mtwSectionRef} className='bg-card rounded-lg border p-3'>
            {/* Sticky Header with Title, Filters, Search, and Scroll to Top */}
            <div className='sticky top-0 z-10 bg-card pb-2 pt-1'>
              {/* Three-section layout: Title (left) | Filters + Search (center) | Scroll to Top (right) */}
              <div className='relative flex items-start justify-between gap-4'>
                {/* Left: Title and Count */}
                <div className='flex shrink-0 items-center gap-2 pt-2'>
                  <Image
                    src="/icons/tokens/bunny_icon.png"
                    alt="Bunny"
                    width={24}
                    height={24}
                    className='h-6 w-6'
                  />
                  <h2 className='text-base font-bold whitespace-nowrap'>Multi-Token Early Wallets</h2>
                  <span className='bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs font-semibold'>
                    {filteredWallets.length}
                  </span>
                  {filteredWallets.length !== multiWallets.total && (
                    <span className='text-muted-foreground text-xs whitespace-nowrap'>
                      of {multiWallets.total}
                    </span>
                  )}
                </div>

                {/* Center: Filters and Search */}
                <div className='flex flex-1 flex-col items-center gap-2'>
                  {/* Filters Button */}
                  <Popover open={isFilterPopoverOpen} onOpenChange={setIsFilterPopoverOpen}>
                    <PopoverTrigger asChild>
                      <Button variant='outline' size='sm' className='h-7 gap-1.5'>
                        <Filter className='h-3.5 w-3.5' />
                        Filters
                        {(() => {
                          const activeCount =
                            mtwFilters.walletTags.length +
                            (mtwFilters.tokenStatus.hasGems ? 1 : 0) +
                            (mtwFilters.tokenStatus.hasDuds ? 1 : 0) +
                            (mtwFilters.tokenStatus.hasUntagged ? 1 : 0) +
                            (mtwFilters.tokenStatus.allGems ? 1 : 0) +
                            (mtwFilters.tokenStatus.allDuds ? 1 : 0) +
                            (mtwFilters.balanceRange.min !== null || mtwFilters.balanceRange.max !== null ? 1 : 0) +
                            (mtwFilters.tokenCountRange.min !== null || mtwFilters.tokenCountRange.max !== null ? 1 : 0) +
                            (mtwFilters.topHolder.isTopHolder ? 1 : 0);
                          return activeCount > 0 ? (
                            <span className='bg-primary text-primary-foreground ml-1 flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold'>
                              {activeCount}
                            </span>
                          ) : null;
                        })()}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className='w-auto p-4' align='center'>
                      <MTWTFilterPopover
                        filters={mtwFilters}
                        onChange={setMtwFilters}
                        onClear={() => setMtwFilters(DEFAULT_MTWT_FILTERS)}
                      />
                    </PopoverContent>
                  </Popover>

                  {/* Search Bar */}
                  <div className='relative flex w-full max-w-md items-center gap-1'>
                    <div className='relative flex-1'>
                      <Search className='text-muted-foreground absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2' />
                      <input
                        type='text'
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder='Search tokens, wallets, tags... (try "gem token:Ant")'
                        className='h-8 w-full rounded-md border bg-background pl-9 pr-8 text-xs focus:outline-none focus:ring-2 focus:ring-primary'
                      />
                      {searchQuery && (
                        <button
                          onClick={() => setSearchQuery('')}
                          className='text-muted-foreground hover:text-foreground absolute right-2 top-1/2 -translate-y-1/2'
                        >
                          <X className='h-3.5 w-3.5' />
                        </button>
                      )}
                    </div>
                    <Popover open={isSearchHelpOpen} onOpenChange={setIsSearchHelpOpen}>
                      <PopoverTrigger asChild>
                        <Button
                          variant='ghost'
                          size='sm'
                          className='h-8 w-8 p-0'
                          aria-label='Search help'
                        >
                          <Info className='h-4 w-4' />
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className='w-auto p-4' align='center'>
                        <SearchHelpPopover />
                      </PopoverContent>
                    </Popover>
                  </div>
                </div>

                {/* Right: Scroll to Top Button (always visible) */}
                <div className='shrink-0 pt-2'>
                  <TooltipProvider delayDuration={100}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant='outline'
                          size='sm'
                          className='h-7 w-7 p-0'
                          onClick={scrollToTop}
                          aria-label='Scroll to top'
                        >
                          <ChevronUp className='h-4 w-4' />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className='text-xs'>Scroll to top</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </div>
            </div>

            <p className='text-muted-foreground mb-2 text-center text-xs'>
              Wallets appearing in multiple analyzed tokens
            </p>

            {/* Active Filters Chips */}
            {(() => {
              const activeFilters: Array<{ label: string; onRemove: () => void }> = [];

              // Wallet tags filters
              mtwFilters.walletTags.forEach((tag) => {
                activeFilters.push({
                  label: `Tag: ${tag}`,
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      walletTags: mtwFilters.walletTags.filter((t) => t !== tag)
                    })
                });
              });

              // Token status filters
              if (mtwFilters.tokenStatus.hasGems) {
                activeFilters.push({
                  label: 'Has GEMs',
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      tokenStatus: { ...mtwFilters.tokenStatus, hasGems: false }
                    })
                });
              }
              if (mtwFilters.tokenStatus.hasDuds) {
                activeFilters.push({
                  label: 'Has DUDs',
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      tokenStatus: { ...mtwFilters.tokenStatus, hasDuds: false }
                    })
                });
              }
              if (mtwFilters.tokenStatus.hasUntagged) {
                activeFilters.push({
                  label: 'Has untagged',
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      tokenStatus: { ...mtwFilters.tokenStatus, hasUntagged: false }
                    })
                });
              }
              if (mtwFilters.tokenStatus.allGems) {
                activeFilters.push({
                  label: 'All GEMs',
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      tokenStatus: { ...mtwFilters.tokenStatus, allGems: false }
                    })
                });
              }
              if (mtwFilters.tokenStatus.allDuds) {
                activeFilters.push({
                  label: 'All DUDs',
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      tokenStatus: { ...mtwFilters.tokenStatus, allDuds: false }
                    })
                });
              }

              // Balance range filter
              if (mtwFilters.balanceRange.min !== null || mtwFilters.balanceRange.max !== null) {
                const min = mtwFilters.balanceRange.min;
                const max = mtwFilters.balanceRange.max;
                let label = 'Balance: ';
                if (min !== null && max !== null) {
                  label += `$${min.toLocaleString()} - $${max.toLocaleString()}`;
                } else if (min !== null) {
                  label += `≥ $${min.toLocaleString()}`;
                } else if (max !== null) {
                  label += `≤ $${max.toLocaleString()}`;
                }
                activeFilters.push({
                  label,
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      balanceRange: { min: null, max: null }
                    })
                });
              }

              // Token count range filter
              if (mtwFilters.tokenCountRange.min !== null || mtwFilters.tokenCountRange.max !== null) {
                const min = mtwFilters.tokenCountRange.min;
                const max = mtwFilters.tokenCountRange.max;
                let label = 'Tokens: ';
                if (min !== null && max !== null) {
                  label += `${min} - ${max}`;
                } else if (min !== null) {
                  label += `≥ ${min}`;
                } else if (max !== null) {
                  label += `≤ ${max}`;
                }
                activeFilters.push({
                  label,
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      tokenCountRange: { min: null, max: null }
                    })
                });
              }

              // Top holder filter
              if (mtwFilters.topHolder.isTopHolder) {
                activeFilters.push({
                  label: 'Is top holder',
                  onRemove: () =>
                    setMtwFilters({
                      ...mtwFilters,
                      topHolder: { ...mtwFilters.topHolder, isTopHolder: false }
                    })
                });
              }

              if (activeFilters.length === 0) return null;

              return (
                <div className='mb-3 flex flex-wrap gap-1.5'>
                  {activeFilters.map((filter, index) => (
                    <span
                      key={index}
                      className='bg-primary/10 text-primary flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium'
                    >
                      {filter.label}
                      <button
                        onClick={filter.onRemove}
                        className='hover:bg-primary/20 rounded-full p-0.5 transition-colors'
                      >
                        <X className='h-2.5 w-2.5' />
                      </button>
                    </span>
                  ))}
                  {activeFilters.length > 1 && (
                    <button
                      onClick={() => setMtwFilters(DEFAULT_MTWT_FILTERS)}
                      className='text-muted-foreground hover:text-foreground text-xs underline'
                    >
                      Clear all
                    </button>
                  )}
                </div>
              );
            })()}

            {/* Top Selection Controls - Sticky Bar */}
            {selectedWallets.size > 0 && (
              <div className='bg-primary/10 border-primary/20 sticky top-0 z-20 mb-2 flex items-center justify-center gap-2 rounded-md border p-2 shadow-md backdrop-blur-sm'>
                <span className='text-primary text-xs font-medium'>
                  {selectedWallets.size} wallet
                  {selectedWallets.size !== 1 ? 's' : ''} selected
                </span>
                <div className='flex items-center gap-1.5'>
                  {/* Bulk Refresh Balance */}
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => handleRefreshBalances()}
                    className='h-6 gap-1 px-2 text-xs'
                    title={`Refresh ${selectedWallets.size} wallet balance(s) - ${selectedWallets.size} API credit(s)`}
                  >
                    <RefreshCw className='h-3 w-3' />
                    Refresh ({selectedWallets.size})
                  </Button>

                  {/* Bulk Tags */}
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant='outline'
                        size='sm'
                        className='h-6 gap-1 px-2 text-xs'
                      >
                        <Tags className='h-3 w-3' />
                        Tags ({selectedWallets.size})
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className='w-56'>
                      <BulkTagsPopover
                        selectedWallets={Array.from(selectedWallets)}
                        onTagsApplied={() => {
                          toast.success('Tags applied to selected wallets');
                        }}
                      />
                    </PopoverContent>
                  </Popover>

                  {/* Deselect All */}
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => setSelectedWallets(new Set())}
                    className='h-6 px-2 text-xs'
                  >
                    Deselect All
                  </Button>
                </div>
              </div>
            )}

            <div
              ref={walletContainerRef}
              onScroll={handleWalletScroll}
              className={`overflow-x-auto ${isWalletPanelExpanded ? 'max-h-[600px] overflow-y-auto' : ''}`}
            >
              <table
                className='w-full table-fixed'
                style={{ minWidth: '1000px' }}
              >
                <colgroup>
                  <col style={{ width: '320px' }} />
                  <col style={{ width: '220px' }} />
                  <col style={{ width: '140px' }} />
                  <col style={{ width: '80px' }} />
                  <col style={{ width: 'auto' }} />
                </colgroup>
                <thead
                  className={
                    isWalletPanelExpanded ? 'bg-card sticky top-0 z-10' : ''
                  }
                >
                  <tr className='border-b'>
                    <th className='pr-4 pb-2 text-left text-xs font-medium'>
                      <button
                        onClick={() => handleSort('address')}
                        className='hover:text-primary flex items-center gap-1 transition-colors'
                      >
                        <span>Wallet Address</span>
                        {sortColumn === 'address' &&
                          (sortDirection === 'asc' ? (
                            <ChevronUp className='h-3 w-3' />
                          ) : (
                            <ChevronDown className='h-3 w-3' />
                          ))}
                      </button>
                    </th>
                    <th className='px-4 pb-2 text-left text-xs font-medium'>
                      <div className='flex items-center justify-start gap-1'>
                        <button
                          onClick={() => handleSort('balance')}
                          className='hover:text-primary flex items-center gap-1 transition-colors'
                        >
                          <span>Balance (USD)</span>
                          {sortColumn === 'balance' &&
                            (sortDirection === 'asc' ? (
                              <ChevronUp className='h-3 w-3' />
                            ) : (
                              <ChevronDown className='h-3 w-3' />
                            ))}
                        </button>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant='ghost'
                                size='sm'
                                className='h-5 w-5 p-0'
                                onClick={handleRefreshAllBalances}
                              >
                                <RefreshCw className='h-3 w-3' />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className='text-xs'>
                                Refresh all visible wallet balances
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
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
                                Refreshing a single wallet balance costs 1 API
                                credit
                              </p>
                              <p className='text-xs'>
                                Refreshing all {walletsToDisplay.length}{' '}
                                wallet(s) costs {walletsToDisplay.length} API
                                credits
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    </th>
                    <th className='px-4 pb-2 text-left text-xs font-medium'>
                      Tags
                    </th>
                    <th className='px-4 pb-2 text-center text-xs font-medium'>
                      <button
                        onClick={() => handleSort('tokens')}
                        className='hover:text-primary mx-auto flex items-center gap-1 transition-colors'
                      >
                        <span>Tokens</span>
                        {sortColumn === 'tokens' &&
                          (sortDirection === 'asc' ? (
                            <ChevronUp className='h-3 w-3' />
                          ) : (
                            <ChevronDown className='h-3 w-3' />
                          ))}
                      </button>
                    </th>
                    <th className='pb-2 pl-4 text-left text-xs font-medium'>
                      <button
                        onClick={() => handleSort('new')}
                        className='hover:text-primary flex items-center gap-1 transition-colors'
                      >
                        <span>Token Names</span>
                        {sortColumn === 'new' &&
                          (sortDirection === 'asc' ? (
                            <ChevronUp className='h-3 w-3' />
                          ) : (
                            <ChevronDown className='h-3 w-3' />
                          ))}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {walletPaddingTop > 0 && (
                    <tr aria-hidden='true'>
                      <td
                        colSpan={5}
                        className='p-0'
                        style={{ height: walletPaddingTop }}
                      />
                    </tr>
                  )}
                  {walletsToDisplay.map((wallet) => {
                    const isSelected = selectedWallets.has(
                      wallet.wallet_address
                    );
                    const cn = (...classes: (string | boolean)[]) =>
                      classes.filter(Boolean).join(' ');
                    return (
                      <tr
                        key={wallet.wallet_address}
                        className={cn(
                          'cursor-pointer border-b transition-all duration-200 ease-out',
                          'hover:shadow-[0_1px_3px_rgba(0,0,0,0.05)]',
                          isSelected &&
                            'bg-primary/20 shadow-[inset_0_0_0_2px_rgba(59,130,246,0.3),0_0_10px_rgba(59,130,246,0.2)]',
                          isSelected &&
                            'hover:bg-primary/25 hover:shadow-[inset_0_0_0_2px_rgba(59,130,246,0.4),0_0_15px_rgba(59,130,246,0.3)]',
                          isSelected && 'active:bg-primary/30',
                          !isSelected && 'hover:bg-muted/50',
                          !isSelected && 'active:bg-muted/70'
                        )}
                        onClick={(e) =>
                          handleWalletRowClick(wallet.wallet_address, e)
                        }
                      >
                        <td className='py-1.5 pr-4'>
                          <div className='flex flex-col gap-0.5'>
                            <div className='flex items-center gap-1.5 overflow-hidden'>
                              <a
                                href={buildSolscanUrl(
                                  wallet.wallet_address,
                                  solscanSettings
                                )}
                                target='_blank'
                                rel='noopener noreferrer'
                                className='text-primary truncate font-sans text-xs hover:underline'
                              >
                                {wallet.wallet_address}
                              </a>
                              {wallet.is_new && (
                                <span className='flex-shrink-0 rounded bg-green-500 px-1.5 py-0.5 text-[10px] font-bold text-white uppercase'>
                                  NEW
                                </span>
                              )}
                              <a
                                href={`https://twitter.com/search?q=${encodeURIComponent(wallet.wallet_address)}`}
                                target='_blank'
                                rel='noopener noreferrer'
                                title='Search on Twitter/X'
                                className='flex-shrink-0'
                              >
                                <Button
                                  variant='ghost'
                                  size='sm'
                                  className='h-6 w-6 p-0'
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <Twitter className='h-3 w-3' />
                                </Button>
                              </a>
                              <Button
                                variant='ghost'
                                size='sm'
                                className='h-6 w-6 flex-shrink-0 p-0'
                                onClick={() => {
                                  navigator.clipboard.writeText(
                                    wallet.wallet_address
                                  );
                                  toast.success('Address copied to clipboard');
                                }}
                              >
                                <Copy className='h-3 w-3' />
                              </Button>
                            </div>
                            <WalletTagLabels
                              walletAddress={wallet.wallet_address}
                            />
                          </div>
                        </td>
                        <td className='px-4 py-1.5 font-mono text-xs'>
                          <div className='flex items-center gap-1.5'>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-5 w-5 flex-shrink-0 p-0'
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRefreshBalances([wallet.wallet_address]);
                              }}
                              title={`Refresh balance - 1 API credit`}
                            >
                              <RefreshCw className='h-3 w-3' />
                            </Button>
                            <div className='flex min-w-0 flex-col gap-0.5'>
                              <div className='flex items-center gap-1'>
                                {(() => {
                                  const trend = getWalletTrend(wallet);
                                  const current = wallet.wallet_balance_usd;
                                  const formatted =
                                    current !== null && current !== undefined
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
                              <div className='text-muted-foreground truncate text-[11px]'>
                                {formatWalletTimestamp(
                                  wallet.wallet_balance_updated_at as
                                    | string
                                    | null
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className='px-4 py-1.5'>
                          <div className='flex items-center gap-1.5'>
                            <WalletTags
                              walletAddress={wallet.wallet_address}
                              iconOnly
                            />
                            <AdditionalTagsPopover
                              walletAddress={wallet.wallet_address}
                              compact
                            />
                            {/* Top Holder Tag */}
                            {topHolderCounts.has(wallet.wallet_address) && topHolderCounts.get(wallet.wallet_address)! > 0 && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedWalletForTopHolders(wallet.wallet_address);
                                  setIsWalletTopHoldersModalOpen(true);
                                }}
                                className='relative rounded bg-purple-500/90 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-purple-600 transition-colors uppercase'
                              >
                                TOP HOLDER
                                {/* Notification Badge */}
                                <span className='absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white border border-background'>
                                  {topHolderCounts.get(wallet.wallet_address)}
                                </span>
                              </button>
                            )}
                          </div>
                        </td>
                        <td className='px-4 py-1.5 text-center'>
                          <span className='bg-primary text-primary-foreground rounded-full px-2 py-0.5 text-xs font-bold'>
                            {wallet.token_count}
                          </span>
                        </td>
                        <td className='py-1.5 pl-4'>
                          <div className='flex flex-wrap gap-1.5 overflow-hidden'>
                            {wallet.token_names.map((name, idx) => {
                              // Show NEW badge for the latest scanned token (regardless of multi-token threshold)
                              const latestTokenId = data.tokens[0]?.id;
                              const isNewToken =
                                wallet.token_ids[idx] === latestTokenId;
                              const gemStatus = wallet.gem_statuses?.[idx];

                              return (
                                <a
                                  key={idx}
                                  href={`https://gmgn.ai/sol/token/${wallet.token_addresses[idx]}?min=0.1&isInputValue=true`}
                                  target='_blank'
                                  rel='noopener noreferrer'
                                  className='bg-muted hover:bg-muted/80 flex items-center gap-1 rounded px-1.5 py-0.5 text-xs'
                                >
                                  {name}
                                  {gemStatus === 'gem' && (
                                    <span className='rounded bg-green-500 px-1 py-0.5 text-[9px] font-bold text-white uppercase'>
                                      GEM
                                    </span>
                                  )}
                                  {gemStatus === 'dud' && (
                                    <span className='rounded bg-red-500 px-1 py-0.5 text-[9px] font-bold text-white uppercase'>
                                      DUD
                                    </span>
                                  )}
                                  {isNewToken && (
                                    <span className='rounded bg-green-500 px-1 py-0.5 text-[9px] font-bold text-white uppercase'>
                                      NEW
                                    </span>
                                  )}
                                </a>
                              );
                            })}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {walletPaddingBottom > 0 && (
                    <tr aria-hidden='true'>
                      <td
                        colSpan={5}
                        className='p-0'
                        style={{ height: walletPaddingBottom }}
                      />
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Collapse/Expand Controls */}
            <div className='mt-1 border-t pt-1'>
              {/* Wallet count info */}
              <div className='mb-1 flex items-center justify-center'>
                <div className='text-muted-foreground text-[11px]'>
                  {isWalletPanelExpanded ? (
                    <>Showing all {multiWallets.wallets.length} wallets</>
                  ) : (
                    <>
                      Showing {walletsToDisplay.length} of{' '}
                      {multiWallets.wallets.length} wallets
                    </>
                  )}
                </div>
              </div>

              {/* Bottom Selection Controls */}
              {selectedWallets.size > 0 && (
                <div className='bg-primary/10 border-primary/20 mb-1 flex items-center justify-center gap-2 rounded-md border p-1'>
                  <span className='text-primary text-[11px] font-medium'>
                    {selectedWallets.size} wallet
                    {selectedWallets.size !== 1 ? 's' : ''} selected
                  </span>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => setSelectedWallets(new Set())}
                    className='h-5 px-1.5 text-[11px]'
                  >
                    Deselect All
                  </Button>
                </div>
              )}

              {/* Centered pagination and expand/collapse */}
              <div className='flex items-center justify-center gap-2'>
                {/* Pagination controls (only when collapsed) */}
                {!isWalletPanelExpanded && totalWalletPages > 1 && (
                  <div className='flex items-center gap-1'>
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={() => setWalletPage((p) => Math.max(0, p - 1))}
                      disabled={walletPage === 0}
                      className='h-5 px-1'
                    >
                      <ChevronLeft className='h-3 w-3' />
                    </Button>
                    <span className='text-muted-foreground px-1 text-[11px]'>
                      Page {walletPage + 1} / {totalWalletPages}
                    </span>
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={() =>
                        setWalletPage((p) =>
                          Math.min(totalWalletPages - 1, p + 1)
                        )
                      }
                      disabled={walletPage >= totalWalletPages - 1}
                      className='h-5 px-1'
                    >
                      <ChevronRight className='h-3 w-3' />
                    </Button>
                  </div>
                )}

                {/* Expand/Collapse button */}
                <Button
                  variant='outline'
                  size='sm'
                  onClick={() => setIsWalletPanelExpanded((prev) => !prev)}
                  className='h-5 gap-1 px-1.5 text-[11px]'
                >
                  {isWalletPanelExpanded ? (
                    <>
                      <ChevronUp className='h-3 w-3' />
                      Collapse
                    </>
                  ) : (
                    <>
                      <ChevronDown className='h-3 w-3' />
                      Expand All
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Tokens Table */}
        <TokensTable
          tokens={filteredTokens}
          onDelete={handleTokenDelete}
          onGemStatusUpdate={refetchMultiWallets}
          onTokenDataRefresh={fetchData}
        />
      </div>

      {/* Sticky Bottom Status Bar */}
      <StatusBar
        tokensScanned={data.tokens.length}
        latestAnalysis={data.tokens[0]?.analysis_timestamp || null}
        latestTokenName={data.tokens[0]?.token_name || null}
        latestWalletsFound={data.tokens[0]?.wallets_found || null}
        latestApiCredits={
          data.tokens[0]?.last_analysis_credits ||
          data.tokens[0]?.credits_used ||
          null
        }
        totalApiCreditsToday={data.tokens
          .filter((token) => {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const analysisDate = new Date(
              token.analysis_timestamp.replace(' ', 'T') + 'Z'
            );
            return analysisDate >= today;
          })
          .reduce(
            (sum, token) =>
              sum + (token.last_analysis_credits || token.credits_used || 0),
            0
          )}
        isFiltered={!!(dateRange.from || dateRange.to)}
        filteredCount={filteredTokens.length}
      />

      {/* Wallet Top Holders Modal */}
      {selectedWalletForTopHolders && (
        <WalletTopHoldersModal
          walletAddress={selectedWalletForTopHolders}
          open={isWalletTopHoldersModalOpen}
          onClose={() => {
            setIsWalletTopHoldersModalOpen(false);
            setSelectedWalletForTopHolders(null);
          }}
        />
      )}
    </WalletTagsProvider>
  );
}
