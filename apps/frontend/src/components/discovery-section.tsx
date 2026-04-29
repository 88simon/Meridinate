'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  getIngestSettings,
  updateIngestSettings,
  getIngestQueue,
  getIngestQueueStats,
  getScheduledJobs,
  runDiscovery,
  promoteTokens,
  discardTokens,
  IngestSettings,
  IngestQueueEntry,
  IngestQueueStats,
  formatTimestamp
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from '@/components/ui/collapsible';
import { toast } from 'sonner';
import {
  Play,
  RefreshCw,
  Settings,
  Trash2,
  ArrowUpCircle,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  Info,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

// Session storage cache keys
const CACHE_KEY_SETTINGS = 'discovery_section_settings';
const CACHE_KEY_STATS = 'discovery_section_stats';
const CACHE_KEY_ENTRIES = 'discovery_section_entries';

interface CachedData<T> {
  data: T;
  cached_at: number;
}

function getFromCache<T>(key: string): T | null {
  try {
    const cached = sessionStorage.getItem(key);
    if (!cached) return null;
    const parsed = JSON.parse(cached) as CachedData<T>;
    return parsed.data;
  } catch {
    return null;
  }
}

function setInCache<T>(key: string, data: T): void {
  try {
    sessionStorage.setItem(
      key,
      JSON.stringify({ data, cached_at: Date.now() })
    );
  } catch {
    // Ignore storage errors
  }
}

// Format USD values
function formatUsd(value: number | null): string {
  if (value === null || value === undefined) return '-';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

// Format hours as relative time
function formatAge(hours: number | null): string {
  if (hours === null || hours === undefined) return '-';
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

// Tier display configuration
const tierConfig: Record<
  string,
  { label: string; color: string; tooltip: string; statusNote: string }
> = {
  ingested: {
    label: 'Discovery Queue',
    color: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    tooltip: 'DexScreener snapshot; ready for promotion to full analysis.',
    statusNote: 'Ready to promote'
  },
  enriched: {
    label: 'Discovery Queue',
    color: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    tooltip: 'Ready for promotion to full analysis.',
    statusNote: 'Ready to promote'
  },
  analyzed: {
    label: 'Analyzed (Live)',
    color: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    tooltip:
      'Full Meridinate analysis complete; visible in Token Pipeline and Wallet Leaderboard.',
    statusNote: 'Live in dashboard'
  },
  discarded: {
    label: 'Discarded',
    color: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    tooltip: 'Manually discarded; will not be promoted.',
    statusNote: 'Excluded'
  }
};

const getTierDisplay = (tier: string) =>
  tierConfig[tier] || {
    label: tier,
    color: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    tooltip: '',
    statusNote: ''
  };

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  completed: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30'
};

interface DiscoverySectionProps {
  defaultOpen?: boolean;
  onPromoteComplete?: () => void;
}

export function DiscoverySection({
  defaultOpen = false,
  onPromoteComplete
}: DiscoverySectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  // Initialize from cache
  const cachedSettings = useRef(
    getFromCache<IngestSettings>(CACHE_KEY_SETTINGS)
  );
  const cachedStats = useRef(getFromCache<IngestQueueStats>(CACHE_KEY_STATS));
  const cachedEntries = useRef(
    getFromCache<IngestQueueEntry[]>(CACHE_KEY_ENTRIES)
  );

  const [settings, setSettings] = useState<IngestSettings | null>(
    cachedSettings.current
  );
  const [stats, setStats] = useState<IngestQueueStats | null>(
    cachedStats.current
  );
  const [entries, setEntries] = useState<IngestQueueEntry[]>(
    cachedEntries.current || []
  );
  const [selectedTier, setSelectedTier] = useState<string>('all');
  const [selectedEntries, setSelectedEntries] = useState<Set<string>>(
    new Set()
  );
  const [loading, setLoading] = useState(!cachedEntries.current);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runningDiscovery, setRunningDiscovery] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [processingAddresses, setProcessingAddresses] = useState<Set<string>>(
    new Set()
  );
  const [, setSavingSettings] = useState(false);

  const hasData = entries.length > 0;
  const prevRunningJobsRef = useRef<Set<string>>(new Set());

  const fetchData = useCallback(async () => {
    setLoadError(null);

    if (hasData) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    getIngestSettings()
      .then((data) => {
        setSettings(data);
        setInCache(CACHE_KEY_SETTINGS, data);
      })
      .catch((err) => {
        console.error('Failed to fetch settings:', err);
      });

    getIngestQueueStats()
      .then((data) => {
        setStats(data);
        setInCache(CACHE_KEY_STATS, data);
      })
      .catch((err) => {
        console.error('Failed to fetch stats:', err);
      });

    getIngestQueue({
      tier: selectedTier === 'all' ? undefined : selectedTier,
      limit: 200
    })
      .then((data) => {
        setEntries(data.entries);
        setInCache(CACHE_KEY_ENTRIES, data.entries);
        setLoading(false);
        setRefreshing(false);
      })
      .catch((err) => {
        console.error('Failed to fetch queue:', err);
        setLoading(false);
        setRefreshing(false);
        if (!hasData) {
          const errorMessage =
            err instanceof Error ? err.message : 'Failed to load data';
          if (errorMessage.includes('timeout')) {
            setLoadError(
              'Backend is busy. Stale data shown if available. Click Refresh to retry.'
            );
          } else {
            setLoadError(errorMessage);
          }
        }
      });
  }, [selectedTier, hasData]);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [fetchData, isOpen]);

  // Poll for job completion
  useEffect(() => {
    if (!isOpen) return;

    const pollInterval = setInterval(async () => {
      try {
        const jobsData = await getScheduledJobs();
        const currentRunningIds = new Set(
          (jobsData.running_jobs || []).map((j) => j.id)
        );

        const prevIds = Array.from(prevRunningJobsRef.current);
        for (const prevId of prevIds) {
          if (!currentRunningIds.has(prevId)) {
            toast.success('Ingestion finished — refresh to see changes', {
              duration: 5000,
              action: {
                label: 'Refresh',
                onClick: () => fetchData()
              }
            });
            break;
          }
        }

        prevRunningJobsRef.current = currentRunningIds;
      } catch (err) {
        console.debug('Job status poll failed:', err);
      }
    }, 10000);

    return () => clearInterval(pollInterval);
  }, [fetchData, isOpen]);

  const handleTierChange = (tier: string) => {
    setSelectedTier(tier);
    setSelectedEntries(new Set());
  };

  const toggleEntry = (address: string) => {
    const newSelected = new Set(selectedEntries);
    if (newSelected.has(address)) {
      newSelected.delete(address);
    } else {
      newSelected.add(address);
    }
    setSelectedEntries(newSelected);
  };

  const selectAll = () => {
    if (selectedEntries.size === entries.length) {
      setSelectedEntries(new Set());
    } else {
      setSelectedEntries(new Set(entries.map((e) => e.token_address)));
    }
  };

  const handleRunDiscovery = async () => {
    setRunningDiscovery(true);

    const queuedAddresses = new Set(
      entries
        .filter((e) => e.tier === 'ingested' || e.tier === 'enriched')
        .map((e) => e.token_address)
    );
    setProcessingAddresses(queuedAddresses);

    toast.info(
      'Discovery is running in the background. You can continue working.',
      { duration: 5000 }
    );

    try {
      const response = await runDiscovery();
      const result = response.result;
      toast.success(
        `Discovery complete: ${result.tokens_new} new, ${result.tokens_updated} updated`
      );
      fetchData();
    } catch {
      toast.error('Discovery failed');
    } finally {
      setRunningDiscovery(false);
      setProcessingAddresses(new Set());
    }
  };

  const handlePromote = async () => {
    if (selectedEntries.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    setPromoting(true);
    setProcessingAddresses(new Set(selectedEntries));

    toast.info(
      'Promotion is running in the background. You can continue working.',
      { duration: 5000 }
    );

    try {
      const response = await promoteTokens(Array.from(selectedEntries));
      toast.success(`Promoted ${response.result.tokens_promoted} tokens`);
      setSelectedEntries(new Set());
      fetchData();
      onPromoteComplete?.();
    } catch {
      toast.error('Failed to promote tokens');
    } finally {
      setPromoting(false);
      setProcessingAddresses(new Set());
    }
  };

  const handleDiscard = async () => {
    if (selectedEntries.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    setDiscarding(true);
    setProcessingAddresses(new Set(selectedEntries));

    try {
      const response = await discardTokens(Array.from(selectedEntries));
      toast.success(`Discarded ${response.discarded} tokens`);
      setSelectedEntries(new Set());
      fetchData();
    } catch {
      toast.error('Failed to discard tokens');
    } finally {
      setDiscarding(false);
      setProcessingAddresses(new Set());
    }
  };

  const handleSettingChange = async (
    key: keyof IngestSettings,
    value: number | boolean | string[] | null
  ) => {
    if (!settings) return;

    const newSettings = { ...settings, [key]: value };
    setSettings(newSettings);

    setSavingSettings(true);
    try {
      await updateIngestSettings({ [key]: value });
      toast.success('Settings updated');
    } catch {
      toast.error('Failed to update settings');
      setSettings(settings);
    } finally {
      setSavingSettings(false);
    }
  };

  const queueCount =
    (stats?.by_tier?.ingested || 0) + (stats?.by_tier?.enriched || 0);

  return (
    <TooltipProvider>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <div className='bg-card rounded-lg border'>
          {/* Header - Always visible */}
          <CollapsibleTrigger asChild>
            <button className='hover:bg-muted/50 flex w-full items-center justify-between p-4 transition-colors'>
              <div className='flex items-center gap-3'>
                <div className='flex items-center gap-2'>
                  <Play className='h-5 w-5 text-blue-400' />
                  <h2 className='text-lg font-semibold'>Token Discovery</h2>
                </div>
                {queueCount > 0 && (
                  <Badge variant='secondary' className='bg-blue-500/20 text-blue-400'>
                    {queueCount} in queue
                  </Badge>
                )}
                {refreshing && (
                  <Loader2 className='text-muted-foreground h-4 w-4 animate-spin' />
                )}
              </div>
              <div className='flex items-center gap-2'>
                {stats?.by_tier?.analyzed !== undefined && (
                  <span className='text-muted-foreground text-sm'>
                    {stats.by_tier.analyzed} analyzed
                  </span>
                )}
                {isOpen ? (
                  <ChevronUp className='h-5 w-5' />
                ) : (
                  <ChevronDown className='h-5 w-5' />
                )}
              </div>
            </button>
          </CollapsibleTrigger>

          <CollapsibleContent>
            <div className='space-y-4 border-t p-4'>
              {/* Stats Cards */}
              <div className='grid gap-4 md:grid-cols-4'>
                <Card>
                  <CardHeader className='pb-2'>
                    <CardTitle className='text-muted-foreground text-sm font-medium'>
                      Total Queue
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className='text-2xl font-bold'>
                      {loading && !stats ? (
                        <span className='text-muted-foreground'>--</span>
                      ) : (
                        stats?.total || 0
                      )}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className='pb-2'>
                    <CardTitle className='flex items-center gap-1 text-sm font-medium text-blue-400'>
                      Discovery Queue
                      <Tooltip>
                        <TooltipTrigger>
                          <Info className='h-3 w-3 text-blue-400/60' />
                        </TooltipTrigger>
                        <TooltipContent>
                          Tokens discovered from DexScreener, ready for promotion
                        </TooltipContent>
                      </Tooltip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className='text-2xl font-bold'>
                      {loading && !stats ? (
                        <span className='text-muted-foreground'>--</span>
                      ) : (
                        queueCount
                      )}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className='pb-2'>
                    <CardTitle className='flex items-center gap-1 text-sm font-medium text-purple-400'>
                      {tierConfig.analyzed.label}
                      <Tooltip>
                        <TooltipTrigger>
                          <Info className='h-3 w-3 text-purple-400/60' />
                        </TooltipTrigger>
                        <TooltipContent>{tierConfig.analyzed.tooltip}</TooltipContent>
                      </Tooltip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className='text-2xl font-bold'>
                      {loading && !stats ? (
                        <span className='text-muted-foreground'>--</span>
                      ) : (
                        stats?.by_tier?.analyzed || 0
                      )}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className='pb-2'>
                    <CardTitle className='flex items-center gap-1 text-sm font-medium text-gray-400'>
                      {tierConfig.discarded.label}
                      <Tooltip>
                        <TooltipTrigger>
                          <Info className='h-3 w-3 text-gray-400/60' />
                        </TooltipTrigger>
                        <TooltipContent>
                          {tierConfig.discarded.tooltip}
                        </TooltipContent>
                      </Tooltip>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className='text-2xl font-bold'>
                      {loading && !stats ? (
                        <span className='text-muted-foreground'>--</span>
                      ) : (
                        stats?.by_tier?.discarded || 0
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Tabs */}
              <Tabs defaultValue='queue' className='space-y-4'>
                <TabsList>
                  <TabsTrigger value='queue'>Queue</TabsTrigger>
                  <TabsTrigger value='settings'>Settings</TabsTrigger>
                </TabsList>

                <TabsContent value='queue' className='space-y-4'>
                  {/* Action Buttons */}
                  <div className='flex flex-wrap items-center gap-2'>
                    <Button
                      onClick={handleRunDiscovery}
                      disabled={runningDiscovery}
                      variant='outline'
                    >
                      {runningDiscovery ? (
                        <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                      ) : (
                        <Play className='mr-2 h-4 w-4' />
                      )}
                      Run Discovery
                    </Button>

                    <div className='bg-border mx-2 h-6 w-px' />

                    <Button
                      onClick={handlePromote}
                      disabled={selectedEntries.size === 0 || promoting}
                      variant='default'
                      size='sm'
                    >
                      {promoting ? (
                        <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                      ) : (
                        <ArrowUpCircle className='mr-2 h-4 w-4' />
                      )}
                      Promote ({selectedEntries.size})
                    </Button>

                    <Button
                      onClick={handleDiscard}
                      disabled={selectedEntries.size === 0 || discarding}
                      variant='destructive'
                      size='sm'
                    >
                      {discarding ? (
                        <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                      ) : (
                        <Trash2 className='mr-2 h-4 w-4' />
                      )}
                      Discard ({selectedEntries.size})
                    </Button>

                    <Button
                      variant='outline'
                      size='sm'
                      onClick={fetchData}
                      disabled={loading || refreshing}
                      className='ml-auto'
                    >
                      <RefreshCw
                        className={`mr-2 h-4 w-4 ${loading || refreshing ? 'animate-spin' : ''}`}
                      />
                      Refresh
                    </Button>

                    {(stats?.last_discovery_run_at || stats?.last_tier0_run_at) && (
                      <span className='text-muted-foreground text-sm'>
                        Last:{' '}
                        {formatTimestamp(
                          stats.last_discovery_run_at ??
                            stats.last_tier0_run_at ??
                            null
                        )}
                      </span>
                    )}
                  </div>

                  {/* Tier Filter */}
                  <div className='flex gap-2'>
                    {[
                      { key: 'all', label: 'All', tooltip: '' },
                      {
                        key: 'queue',
                        label: 'Discovery Queue',
                        tooltip: 'Tokens ready for promotion'
                      },
                      {
                        key: 'analyzed',
                        label: 'Analyzed (Live)',
                        tooltip: 'Fully analyzed and tracked'
                      },
                      {
                        key: 'discarded',
                        label: 'Discarded',
                        tooltip: 'Excluded from processing'
                      }
                    ].map(({ key, label, tooltip }) => {
                      const getCount = () => {
                        if (key === 'queue') {
                          return queueCount;
                        }
                        return stats?.by_tier?.[key] || 0;
                      };

                      return (
                        <Tooltip key={key}>
                          <TooltipTrigger asChild>
                            <Button
                              variant={selectedTier === key ? 'default' : 'outline'}
                              size='sm'
                              onClick={() =>
                                handleTierChange(key === 'queue' ? 'ingested' : key)
                              }
                            >
                              {label}
                              {key !== 'all' && (
                                <Badge variant='secondary' className='ml-2'>
                                  {getCount()}
                                </Badge>
                              )}
                            </Button>
                          </TooltipTrigger>
                          {tooltip && <TooltipContent>{tooltip}</TooltipContent>}
                        </Tooltip>
                      );
                    })}
                  </div>

                  {/* Queue Table */}
                  <Card>
                    <div className='max-h-[400px] overflow-auto'>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className='w-10'>
                              <Checkbox
                                checked={
                                  entries.length > 0 &&
                                  selectedEntries.size === entries.length
                                }
                                onCheckedChange={selectAll}
                              />
                            </TableHead>
                            <TableHead>Token</TableHead>
                            <TableHead>Address</TableHead>
                            <TableHead>MC</TableHead>
                            <TableHead>Volume</TableHead>
                            <TableHead>Liquidity</TableHead>
                            <TableHead>Age</TableHead>
                            <TableHead>Stage</TableHead>
                            <TableHead>Status</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {loading && !hasData ? (
                            <TableRow>
                              <TableCell
                                colSpan={9}
                                className='text-muted-foreground py-8 text-center'
                              >
                                <div className='flex items-center justify-center gap-2'>
                                  <Loader2 className='h-4 w-4 animate-spin' />
                                  Loading queue...
                                </div>
                              </TableCell>
                            </TableRow>
                          ) : loadError && !hasData ? (
                            <TableRow>
                              <TableCell colSpan={9} className='py-8 text-center'>
                                <div className='flex flex-col items-center gap-3'>
                                  <div className='text-muted-foreground'>
                                    {loadError}
                                  </div>
                                  <Button
                                    variant='outline'
                                    size='sm'
                                    onClick={fetchData}
                                  >
                                    <RefreshCw className='mr-2 h-4 w-4' />
                                    Retry
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          ) : entries.length === 0 ? (
                            <TableRow>
                              <TableCell
                                colSpan={9}
                                className='text-muted-foreground text-center'
                              >
                                No tokens in queue
                              </TableCell>
                            </TableRow>
                          ) : (
                            entries.map((entry) => {
                              const tierDisplay = getTierDisplay(entry.tier);
                              const isLive = entry.tier === 'analyzed';
                              return (
                                <TableRow
                                  key={entry.token_address}
                                  className={
                                    selectedEntries.has(entry.token_address)
                                      ? 'bg-muted/50'
                                      : ''
                                  }
                                >
                                  <TableCell>
                                    <Checkbox
                                      checked={selectedEntries.has(entry.token_address)}
                                      onCheckedChange={() =>
                                        toggleEntry(entry.token_address)
                                      }
                                    />
                                  </TableCell>
                                  <TableCell className='font-medium'>
                                    <div className='flex items-center gap-1.5'>
                                      {processingAddresses.has(entry.token_address) && (
                                        <Loader2 className='h-3 w-3 animate-spin text-blue-500' />
                                      )}
                                      {entry.token_symbol || entry.token_name || '-'}
                                    </div>
                                  </TableCell>
                                  <TableCell className='font-mono text-xs'>
                                    <Tooltip>
                                      <TooltipTrigger>
                                        {entry.token_address.slice(0, 8)}...
                                      </TooltipTrigger>
                                      <TooltipContent>
                                        {entry.token_address}
                                      </TooltipContent>
                                    </Tooltip>
                                  </TableCell>
                                  <TableCell>{formatUsd(entry.last_mc_usd)}</TableCell>
                                  <TableCell>
                                    {formatUsd(entry.last_volume_usd)}
                                  </TableCell>
                                  <TableCell>
                                    {formatUsd(entry.last_liquidity)}
                                  </TableCell>
                                  <TableCell>{formatAge(entry.age_hours)}</TableCell>
                                  <TableCell>
                                    <Tooltip>
                                      <TooltipTrigger>
                                        <Badge
                                          variant='outline'
                                          className={tierDisplay.color}
                                        >
                                          {tierDisplay.label}
                                        </Badge>
                                      </TooltipTrigger>
                                      <TooltipContent>
                                        {tierDisplay.tooltip}
                                      </TooltipContent>
                                    </Tooltip>
                                  </TableCell>
                                  <TableCell>
                                    <div className='flex items-center gap-1'>
                                      {entry.status === 'pending' && (
                                        <Clock className='h-3 w-3 text-yellow-400' />
                                      )}
                                      {entry.status === 'completed' && (
                                        <CheckCircle2 className='h-3 w-3 text-green-400' />
                                      )}
                                      {entry.status === 'failed' && (
                                        <Tooltip>
                                          <TooltipTrigger>
                                            <XCircle className='h-3 w-3 text-red-400' />
                                          </TooltipTrigger>
                                          <TooltipContent>
                                            {entry.last_error || 'Unknown error'}
                                          </TooltipContent>
                                        </Tooltip>
                                      )}
                                      <Badge
                                        variant='outline'
                                        className={statusColors[entry.status]}
                                      >
                                        {entry.status}
                                      </Badge>
                                    </div>
                                  </TableCell>
                                </TableRow>
                              );
                            })
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  </Card>
                </TabsContent>

                <TabsContent value='settings' className='space-y-6'>
                  {settings && (
                    <>
                      {/* Feature Flags */}
                      <Card>
                        <CardHeader>
                          <CardTitle className='flex items-center gap-2'>
                            <Settings className='h-5 w-5' />
                            Feature Flags
                          </CardTitle>
                        </CardHeader>
                        <CardContent className='space-y-4'>
                          <div className='flex items-center justify-between'>
                            <div>
                              <Label>Discovery (Scheduled)</Label>
                              <p className='text-muted-foreground text-sm'>
                                Auto-fetch tokens from DexScreener
                              </p>
                            </div>
                            <Switch
                              checked={
                                settings.discovery_enabled ?? settings.ingest_enabled
                              }
                              onCheckedChange={(v) =>
                                handleSettingChange('discovery_enabled', v)
                              }
                            />
                          </div>

                          <div className='flex items-center justify-between'>
                            <div>
                              <Label>Auto-Promote</Label>
                              <p className='text-muted-foreground text-sm'>
                                Automatically promote discovered tokens to full
                                analysis
                              </p>
                            </div>
                            <Switch
                              checked={settings.auto_promote_enabled}
                              onCheckedChange={(v) =>
                                handleSettingChange('auto_promote_enabled', v)
                              }
                            />
                          </div>
                        </CardContent>
                      </Card>

                      {/* Thresholds */}
                      <Card>
                        <CardHeader>
                          <CardTitle>Promotion Thresholds</CardTitle>
                        </CardHeader>
                        <CardContent className='grid gap-4 md:grid-cols-2'>
                          <div className='space-y-2'>
                            <Label>Min Market Cap ($)</Label>
                            <Input
                              type='number'
                              value={settings.mc_min}
                              onChange={(e) =>
                                handleSettingChange('mc_min', Number(e.target.value))
                              }
                            />
                          </div>

                          <div className='space-y-2'>
                            <Label>Min 24h Volume ($)</Label>
                            <Input
                              type='number'
                              value={settings.volume_min}
                              onChange={(e) =>
                                handleSettingChange(
                                  'volume_min',
                                  Number(e.target.value)
                                )
                              }
                            />
                          </div>

                          <div className='space-y-2'>
                            <Label>Min Liquidity ($)</Label>
                            <Input
                              type='number'
                              value={settings.liquidity_min}
                              onChange={(e) =>
                                handleSettingChange(
                                  'liquidity_min',
                                  Number(e.target.value)
                                )
                              }
                            />
                          </div>

                          <div className='space-y-2'>
                            <Label>Max Age (hours)</Label>
                            <Input
                              type='number'
                              value={settings.age_max_hours}
                              onChange={(e) =>
                                handleSettingChange(
                                  'age_max_hours',
                                  Number(e.target.value)
                                )
                              }
                            />
                          </div>
                        </CardContent>
                      </Card>

                      {/* Discovery Settings */}
                      <Card>
                        <CardHeader>
                          <CardTitle>Discovery Settings</CardTitle>
                        </CardHeader>
                        <CardContent className='grid gap-4 md:grid-cols-2'>
                          <div className='space-y-2'>
                            <Label>Max Tokens per Run</Label>
                            <Input
                              type='number'
                              value={
                                settings.discovery_max_per_run ??
                                settings.tier0_max_tokens_per_run
                              }
                              onChange={(e) =>
                                handleSettingChange(
                                  'discovery_max_per_run',
                                  Number(e.target.value)
                                )
                              }
                            />
                          </div>

                          <div className='space-y-2'>
                            <Label>Auto-Promote Max per Run</Label>
                            <Input
                              type='number'
                              value={settings.auto_promote_max_per_run}
                              onChange={(e) =>
                                handleSettingChange(
                                  'auto_promote_max_per_run',
                                  Number(e.target.value)
                                )
                              }
                            />
                          </div>
                        </CardContent>
                      </Card>

                      {/* CLOBr Enrichment */}
                      <Card>
                        <CardHeader>
                          <CardTitle>CLOBr Enrichment</CardTitle>
                          <p className='text-muted-foreground text-xs'>
                            Enrich tokens with CLOBr liquidity scores and market depth data during MC tracking. Tokens below the warning threshold are flagged in the UI.
                          </p>
                        </CardHeader>
                        <CardContent className='space-y-4'>
                          <div className='flex items-center justify-between'>
                            <div>
                              <Label>Enable CLOBr Enrichment</Label>
                              <p className='text-muted-foreground text-sm'>
                                Fetch liquidity scores and support/resistance levels from CLOBr
                              </p>
                            </div>
                            <Switch
                              checked={settings.clobr_enabled ?? false}
                              onCheckedChange={(v) =>
                                handleSettingChange('clobr_enabled', v)
                              }
                            />
                          </div>

                          <div className='space-y-2'>
                            <Label>Warning Threshold (0-100)</Label>
                            <Input
                              type='number'
                              min={0}
                              max={100}
                              value={settings.clobr_min_score ?? 50}
                              onChange={(e) =>
                                handleSettingChange(
                                  'clobr_min_score',
                                  Number(e.target.value)
                                )
                              }
                              disabled={!(settings.clobr_enabled ?? false)}
                            />
                          </div>
                        </CardContent>
                      </Card>

                      {/* Pipeline Filters */}
                      <Card>
                        <CardHeader>
                          <CardTitle>Pipeline Filters</CardTitle>
                          <p className='text-muted-foreground text-xs'>
                            Tokens not matching these filters are excluded during discovery.
                          </p>
                        </CardHeader>
                        <CardContent className='space-y-4'>
                          {/* Launchpad Filter */}
                          <div>
                            <Label className='mb-2 block text-sm'>Launchpads</Label>
                            <div className='grid grid-cols-3 gap-1.5'>
                              {[
                                { id: 'pumpswap', label: 'Pump.fun' },
                                { id: 'raydium', label: 'Raydium' },
                                { id: 'orca', label: 'Orca' },
                                { id: 'meteora', label: 'Meteora' },
                                { id: 'moonshot', label: 'Moonshot' },
                                { id: 'bonk', label: 'Bonk' },
                                { id: 'believe', label: 'Believe' },
                                { id: 'launchlab', label: 'LaunchLab' },
                                { id: 'boop', label: 'Boop' },
                              ].map(({ id, label }) => {
                                const included = (settings.launchpad_include ?? []) as string[];
                                const isChecked = included.length === 0 || included.includes(id);
                                return (
                                  <label
                                    key={id}
                                    className={`flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1 text-xs transition-colors ${
                                      isChecked
                                        ? 'border-primary/30 bg-primary/5 text-foreground'
                                        : 'border-muted bg-muted/30 text-muted-foreground line-through'
                                    }`}
                                  >
                                    <input
                                      type='checkbox'
                                      className='h-3 w-3 rounded'
                                      checked={isChecked}
                                      onChange={(e) => {
                                        const allPads = ['pumpswap', 'raydium', 'orca', 'meteora', 'moonshot', 'bonk', 'believe', 'launchlab', 'boop'];
                                        let newInclude: string[];
                                        if (included.length === 0) {
                                          newInclude = allPads.filter((x) => x !== id);
                                        } else if (e.target.checked) {
                                          newInclude = [...included, id];
                                        } else {
                                          newInclude = included.filter((x) => x !== id);
                                        }
                                        if (newInclude.length >= allPads.length) newInclude = [];
                                        handleSettingChange('launchpad_include', newInclude);
                                      }}
                                    />
                                    {label}
                                  </label>
                                );
                              })}
                            </div>
                          </div>

                          {/* Quote Token + Socials */}
                          <div className='grid gap-4 md:grid-cols-2'>
                            <div className='space-y-2'>
                              <Label>Quote Token</Label>
                              <Input
                                placeholder='SOL, USDC, ...'
                                value={(settings.quote_token_include ?? []).join(', ')}
                                onChange={(e) => {
                                  const vals = e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean);
                                  handleSettingChange('quote_token_include', vals);
                                }}
                              />
                              <p className='text-muted-foreground text-[10px]'>
                                Only these quote tokens (empty = all)
                              </p>
                            </div>
                            <div className='flex items-center justify-between rounded-lg border p-3'>
                              <div>
                                <Label>Require Socials</Label>
                                <p className='text-muted-foreground text-[10px]'>
                                  Only tokens with social links
                                </p>
                              </div>
                              <Switch
                                checked={settings.require_socials ?? false}
                                onCheckedChange={(v) => handleSettingChange('require_socials', v)}
                              />
                            </div>
                          </div>

                          {/* Transaction Filters */}
                          <div className='grid gap-4 md:grid-cols-2'>
                            <div className='space-y-2'>
                              <Label>Min Buys (24h)</Label>
                              <Input
                                type='number'
                                placeholder='0'
                                value={settings.buys_24h_min ?? ''}
                                onChange={(e) => handleSettingChange('buys_24h_min', e.target.value ? Number(e.target.value) : null)}
                              />
                            </div>
                            <div className='space-y-2'>
                              <Label>Min Net Buys (24h)</Label>
                              <Input
                                type='number'
                                placeholder='0'
                                value={settings.net_buys_24h_min ?? ''}
                                onChange={(e) => handleSettingChange('net_buys_24h_min', e.target.value ? Number(e.target.value) : null)}
                              />
                            </div>
                            <div className='space-y-2'>
                              <Label>Min TXs (24h)</Label>
                              <Input
                                type='number'
                                placeholder='0'
                                value={settings.txs_24h_min ?? ''}
                                onChange={(e) => handleSettingChange('txs_24h_min', e.target.value ? Number(e.target.value) : null)}
                              />
                            </div>
                            <div className='space-y-2'>
                              <Label>Min 1h Price Change (%)</Label>
                              <Input
                                type='number'
                                placeholder='0'
                                value={settings.price_change_h1_min ?? ''}
                                onChange={(e) => handleSettingChange('price_change_h1_min', e.target.value ? Number(e.target.value) : null)}
                              />
                            </div>
                          </div>

                          {/* Keyword Filters */}
                          <div className='grid gap-4 md:grid-cols-2'>
                            <div className='space-y-2'>
                              <Label>Keyword Include</Label>
                              <Input
                                placeholder='pepe, doge, ...'
                                value={(settings.keyword_include ?? []).join(', ')}
                                onChange={(e) => {
                                  const vals = e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean);
                                  handleSettingChange('keyword_include', vals);
                                }}
                              />
                              <p className='text-muted-foreground text-[10px]'>
                                Token name must contain one of these
                              </p>
                            </div>
                            <div className='space-y-2'>
                              <Label>Keyword Exclude</Label>
                              <Input
                                placeholder='scam, rug, ...'
                                value={(settings.keyword_exclude ?? []).join(', ')}
                                onChange={(e) => {
                                  const vals = e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean);
                                  handleSettingChange('keyword_exclude', vals);
                                }}
                              />
                              <p className='text-muted-foreground text-[10px]'>
                                Exclude tokens with these words
                              </p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </TooltipProvider>
  );
}
