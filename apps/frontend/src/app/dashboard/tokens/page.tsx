'use client';

import React, {
  useEffect,
  useState,
  useRef,
  useMemo,
  useCallback,
  startTransition
} from 'react';
import dynamic from 'next/dynamic';
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
const WalletAddressWithBotIndicator = dynamic(
  () =>
    import('@/components/additional-tags').then((mod) => ({
      default: mod.WalletAddressWithBotIndicator
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
        {['Bot', 'Whale', 'Insider'].map((tag) => (
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

  // Virtualization state for multi-token wallet table
  const walletContainerRef = useRef<HTMLDivElement>(null);
  const [walletScrollTop, setWalletScrollTop] = useState(0);
  const [walletViewportHeight, setWalletViewportHeight] = useState(0);

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

  // Pagination logic for multi-token wallets (collapsed mode)
  const walletsPaginated = useMemo(() => {
    if (!multiWallets?.wallets) return [];
    if (isWalletPanelExpanded) return multiWallets.wallets;

    const start = walletPage * walletsPerPage;
    const end = start + walletsPerPage;
    return multiWallets.wallets.slice(start, end);
  }, [multiWallets, isWalletPanelExpanded, walletPage]);

  // Virtualization logic for expanded mode
  const { walletsToDisplay, walletPaddingTop, walletPaddingBottom } =
    useMemo(() => {
      if (!isWalletPanelExpanded || !multiWallets?.wallets) {
        return {
          walletsToDisplay: walletsPaginated,
          walletPaddingTop: 0,
          walletPaddingBottom: 0
        };
      }

      const allWallets = multiWallets.wallets;
      const totalWallets = allWallets.length;
      const baseRowHeight = 80; // Average height per wallet row
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
      multiWallets,
      isWalletPanelExpanded,
      walletsPaginated,
      walletScrollTop,
      walletViewportHeight
    ]);

  const totalWalletPages = useMemo(() => {
    if (!multiWallets?.wallets) return 0;
    return Math.ceil(multiWallets.wallets.length / walletsPerPage);
  }, [multiWallets]);

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

        {/* Multi-Token Wallets Section */}
        {multiWallets && multiWallets.total > 0 && (
          <div className='bg-card rounded-lg border p-6'>
            <div className='mb-2 flex items-center gap-3'>
              <h2 className='text-xl font-bold'>Multi-Token Wallets</h2>
              <span className='bg-primary/10 text-primary rounded-full px-3 py-1 text-sm font-semibold'>
                {multiWallets.total}
              </span>
            </div>
            <p className='text-muted-foreground mb-4 text-sm'>
              Wallets that appear in multiple analyzed tokens (potential
              whale/insider wallets)
            </p>

            {/* Top Selection Controls - Sticky Bar */}
            {selectedWallets.size > 0 && (
              <div className='bg-primary/10 border-primary/20 sticky top-0 z-20 mb-4 flex flex-col items-center gap-2 rounded-md border p-3 shadow-md backdrop-blur-sm'>
                <span className='text-primary text-sm font-medium'>
                  {selectedWallets.size} wallet
                  {selectedWallets.size !== 1 ? 's' : ''} selected
                </span>
                <div className='flex items-center gap-2'>
                  {/* Bulk Refresh Balance */}
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => handleRefreshBalances()}
                    className='h-7 gap-1.5 text-xs'
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
                        className='h-7 gap-1.5 text-xs'
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
                    className='h-7 text-xs'
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
              <table className='w-full'>
                <thead
                  className={
                    isWalletPanelExpanded ? 'bg-card sticky top-0 z-10' : ''
                  }
                >
                  <tr className='border-b'>
                    <th className='pr-4 pb-3 text-left font-medium'>
                      Wallet Address
                    </th>
                    <th className='px-4 pb-3 text-right font-medium'>
                      <div className='flex items-center justify-end gap-1.5'>
                        <span>Balance (USD)</span>
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
                    <th className='px-4 pb-3 text-left font-medium'>Tags</th>
                    <th className='px-4 pb-3 text-center font-medium'>
                      Tokens
                    </th>
                    <th className='pb-3 pl-4 text-left font-medium'>
                      Token Names
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
                        <td className='py-3 pr-4'>
                          <div className='flex items-center gap-2'>
                            <WalletAddressWithBotIndicator
                              walletAddress={wallet.wallet_address}
                            >
                              <a
                                href={buildSolscanUrl(
                                  wallet.wallet_address,
                                  solscanSettings
                                )}
                                target='_blank'
                                rel='noopener noreferrer'
                                className='text-primary font-sans text-xs hover:underline'
                              >
                                {wallet.wallet_address}
                              </a>
                            </WalletAddressWithBotIndicator>
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
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Twitter className='h-3 w-3' />
                              </Button>
                            </a>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-6 w-6 p-0'
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
                        </td>
                        <td className='px-4 py-3 text-right font-mono text-sm'>
                          <div className='flex flex-col items-end gap-1'>
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
                            <div className='text-muted-foreground text-[11px]'>
                              {formatWalletTimestamp(
                                wallet.wallet_balance_updated_at as
                                  | string
                                  | null
                              )}
                            </div>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-6 w-6 p-0'
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRefreshBalances([wallet.wallet_address]);
                              }}
                              title={`Refresh balance - 1 API credit`}
                            >
                              <RefreshCw className='h-3 w-3' />
                            </Button>
                          </div>
                        </td>
                        <td className='px-4 py-3'>
                          <div className='flex items-center gap-2'>
                            <WalletTags walletAddress={wallet.wallet_address} />
                            <AdditionalTagsPopover
                              walletAddress={wallet.wallet_address}
                              compact
                            />
                          </div>
                        </td>
                        <td className='px-4 py-3 text-center'>
                          <span className='bg-primary text-primary-foreground rounded-full px-3 py-1 text-sm font-bold'>
                            {wallet.token_count}
                          </span>
                        </td>
                        <td className='py-3 pl-4'>
                          <div className='flex flex-wrap gap-2'>
                            {wallet.token_names.map((name, idx) => (
                              <a
                                key={idx}
                                href={`https://gmgn.ai/sol/token/${wallet.token_addresses[idx]}?min=0.1&isInputValue=true`}
                                target='_blank'
                                rel='noopener noreferrer'
                                className='bg-muted hover:bg-muted/80 rounded px-2 py-1 text-xs'
                              >
                                {name}
                              </a>
                            ))}
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
            <div className='mt-4 border-t pt-4'>
              {/* Wallet count info */}
              <div className='mb-3 flex items-center justify-center'>
                <div className='text-muted-foreground text-sm'>
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
                <div className='bg-primary/10 border-primary/20 mb-3 flex items-center justify-center gap-2 rounded-md border p-2'>
                  <span className='text-primary text-sm font-medium'>
                    {selectedWallets.size} wallet
                    {selectedWallets.size !== 1 ? 's' : ''} selected
                  </span>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => setSelectedWallets(new Set())}
                    className='h-7 text-xs'
                  >
                    Deselect All
                  </Button>
                </div>
              )}

              {/* Centered pagination and expand/collapse */}
              <div className='flex items-center justify-center gap-3'>
                {/* Pagination controls (only when collapsed) */}
                {!isWalletPanelExpanded && totalWalletPages > 1 && (
                  <div className='flex items-center gap-1'>
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={() => setWalletPage((p) => Math.max(0, p - 1))}
                      disabled={walletPage === 0}
                      className='h-7 px-2'
                    >
                      <ChevronLeft className='h-3 w-3' />
                    </Button>
                    <span className='text-muted-foreground px-2 text-xs'>
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
                      className='h-7 px-2'
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
                  className='h-7'
                >
                  {isWalletPanelExpanded ? (
                    <>
                      <ChevronUp className='mr-1 h-4 w-4' />
                      Collapse
                    </>
                  ) : (
                    <>
                      <ChevronDown className='mr-1 h-4 w-4' />
                      Expand All
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Tokens Table */}
        <TokensTable tokens={filteredTokens} onDelete={handleTokenDelete} />
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
    </WalletTagsProvider>
  );
}
