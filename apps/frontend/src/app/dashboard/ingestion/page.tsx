'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  getIngestSettings,
  updateIngestSettings,
  getIngestQueue,
  getIngestQueueStats,
  getScheduledJobs,
  runTier0Ingestion,
  runTier1Enrichment,
  promoteTokens,
  discardTokens,
  IngestSettings,
  IngestQueueEntry,
  IngestQueueStats,
  formatTimestamp
} from '@/lib/api';
import { StatusBar } from '@/components/status-bar';
import { useStatusBarData } from '@/hooks/useStatusBarData';
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
  Info
} from 'lucide-react';

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

// Tier display configuration with labels, colors, and tooltips
const tierConfig: Record<
  string,
  { label: string; color: string; tooltip: string; statusNote: string }
> = {
  ingested: {
    label: 'Discovered',
    color: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    tooltip: 'DexScreener snapshot only; no Helius calls yet.',
    statusNote: 'Not yet in dashboard'
  },
  enriched: {
    label: 'Pre-Analyzed',
    color: 'bg-green-500/20 text-green-400 border-green-500/30',
    tooltip:
      'Light Helius enrichment (holders/metadata); not in main dashboard yet.',
    statusNote: 'Needs promotion'
  },
  analyzed: {
    label: 'Analyzed (Live)',
    color: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    tooltip:
      'Full Meridinate analysis complete; visible in Tokens dashboard and SWAB.',
    statusNote: 'Live in dashboard'
  },
  discarded: {
    label: 'Discarded',
    color: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    tooltip: 'Manually discarded; will not be promoted.',
    statusNote: 'Excluded'
  }
};

// Helper to get tier display info
const getTierDisplay = (tier: string) =>
  tierConfig[tier] || {
    label: tier,
    color: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    tooltip: '',
    statusNote: ''
  };

// Status badge colors
const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  completed: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30'
};

export default function IngestionPage() {
  const [settings, setSettings] = useState<IngestSettings | null>(null);
  const [stats, setStats] = useState<IngestQueueStats | null>(null);
  const [entries, setEntries] = useState<IngestQueueEntry[]>([]);
  const [selectedTier, setSelectedTier] = useState<string>('all');
  const [selectedEntries, setSelectedEntries] = useState<Set<string>>(
    new Set()
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runningTier0, setRunningTier0] = useState(false);
  const [runningTier1, setRunningTier1] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [processingAddresses, setProcessingAddresses] = useState<Set<string>>(
    new Set()
  );
  const [savingSettings, setSavingSettings] = useState(false);

  // Track running jobs for completion detection
  const prevRunningJobsRef = useRef<Set<string>>(new Set());

  // Status bar data with live credit tracking
  const statusBarData = useStatusBarData({
    tokensScanned: stats?.by_tier?.analyzed ?? 0,
    pollInterval: 30000
  });

  // Fetch data independently - partial success still shows available data
  // Preserves stale data on failure so UI remains functional
  const fetchData = useCallback(async () => {
    setLoadError(null);
    let hasAnyError = false;
    const errors: string[] = [];

    // Fetch settings (independent)
    getIngestSettings()
      .then((data) => setSettings(data))
      .catch((err) => {
        console.error('Failed to fetch settings:', err);
        errors.push('settings');
        hasAnyError = true;
      });

    // Fetch stats (independent)
    getIngestQueueStats()
      .then((data) => setStats(data))
      .catch((err) => {
        console.error('Failed to fetch stats:', err);
        errors.push('stats');
        hasAnyError = true;
      });

    // Fetch queue entries (independent)
    getIngestQueue({
      tier: selectedTier === 'all' ? undefined : selectedTier,
      limit: 200
    })
      .then((data) => {
        setEntries(data.entries);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch queue:', err);
        errors.push('queue');
        hasAnyError = true;
        setLoading(false);
        // Only show error if no stale data available
        if (entries.length === 0) {
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
  }, [selectedTier, entries.length]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Poll for job completion and show toast when ingestion finishes
  useEffect(() => {
    const pollInterval = setInterval(async () => {
      try {
        const jobsData = await getScheduledJobs();
        const currentRunningIds = new Set(
          (jobsData.running_jobs || []).map((j) => j.id)
        );

        // Check if any previously running jobs have completed
        const prevIds = Array.from(prevRunningJobsRef.current);
        for (const prevId of prevIds) {
          if (!currentRunningIds.has(prevId)) {
            // Job completed - show toast
            toast.success('Ingestion finished — refresh to see changes', {
              duration: 5000,
              action: {
                label: 'Refresh',
                onClick: () => fetchData()
              }
            });
            break; // Only show one toast per poll cycle
          }
        }

        // Update ref for next poll
        prevRunningJobsRef.current = currentRunningIds;
      } catch (err) {
        // Silently ignore polling errors - this is background monitoring
        console.debug('Job status poll failed:', err);
      }
    }, 10000); // Poll every 10 seconds

    return () => clearInterval(pollInterval);
  }, [fetchData]);

  // Handle tier filter change
  const handleTierChange = (tier: string) => {
    setSelectedTier(tier);
    setSelectedEntries(new Set());
  };

  // Handle entry selection
  const toggleEntry = (address: string) => {
    const newSelected = new Set(selectedEntries);
    if (newSelected.has(address)) {
      newSelected.delete(address);
    } else {
      newSelected.add(address);
    }
    setSelectedEntries(newSelected);
  };

  // Select all visible entries
  const selectAll = () => {
    if (selectedEntries.size === entries.length) {
      setSelectedEntries(new Set());
    } else {
      setSelectedEntries(new Set(entries.map((e) => e.token_address)));
    }
  };

  // Run Tier-0 ingestion
  const handleRunTier0 = async () => {
    setRunningTier0(true);

    // Mark all 'ingested' tier tokens as processing (Tier-0 fetches new tokens)
    const ingestedAddresses = new Set(
      entries.filter((e) => e.tier === 'ingested').map((e) => e.token_address)
    );
    setProcessingAddresses(ingestedAddresses);

    // Show background-safe toast immediately
    toast.info(
      'Tier-0 ingestion is running in the background. You can leave this page safely.',
      { duration: 5000 }
    );

    try {
      const response = await runTier0Ingestion();
      const result = response.result;
      toast.success(
        `Tier-0 complete: ${result.tokens_new} new, ${result.tokens_updated} updated`
      );
      fetchData();
    } catch (error) {
      toast.error('Tier-0 ingestion failed');
    } finally {
      setRunningTier0(false);
      setProcessingAddresses(new Set());
    }
  };

  // Run Tier-1 enrichment
  const handleRunTier1 = async () => {
    setRunningTier1(true);

    // Mark all 'ingested' tier tokens as processing (Tier-1 enriches ingested tokens)
    const ingestedAddresses = new Set(
      entries.filter((e) => e.tier === 'ingested').map((e) => e.token_address)
    );
    setProcessingAddresses(ingestedAddresses);

    // Show background-safe toast immediately
    toast.info(
      'Tier-1 enrichment is running in the background. You can leave this page safely.',
      { duration: 5000 }
    );

    try {
      const response = await runTier1Enrichment();
      const result = response.result;
      toast.success(
        `Tier-1 complete: ${result.tokens_enriched} enriched, ${result.credits_used} credits`
      );
      fetchData();
    } catch (error) {
      toast.error('Tier-1 enrichment failed');
    } finally {
      setRunningTier1(false);
      setProcessingAddresses(new Set());
    }
  };

  // Promote selected tokens
  const handlePromote = async () => {
    if (selectedEntries.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    setPromoting(true);

    // Mark selected tokens as processing
    setProcessingAddresses(new Set(selectedEntries));

    // Show background-safe toast immediately
    toast.info(
      'Promotion is running in the background. You can leave this page safely.',
      { duration: 5000 }
    );

    try {
      const response = await promoteTokens(Array.from(selectedEntries));
      toast.success(`Promoted ${response.result.tokens_promoted} tokens`);
      setSelectedEntries(new Set());
      fetchData();
    } catch (error) {
      toast.error('Failed to promote tokens');
    } finally {
      setPromoting(false);
      setProcessingAddresses(new Set());
    }
  };

  // Discard selected tokens
  const handleDiscard = async () => {
    if (selectedEntries.size === 0) {
      toast.error('No tokens selected');
      return;
    }

    setDiscarding(true);

    // Mark selected tokens as processing
    setProcessingAddresses(new Set(selectedEntries));

    try {
      const response = await discardTokens(Array.from(selectedEntries));
      toast.success(`Discarded ${response.discarded} tokens`);
      setSelectedEntries(new Set());
      fetchData();
    } catch (error) {
      toast.error('Failed to discard tokens');
    } finally {
      setDiscarding(false);
      setProcessingAddresses(new Set());
    }
  };

  // Update settings
  const handleSettingChange = async (
    key: keyof IngestSettings,
    value: number | boolean
  ) => {
    if (!settings) return;

    const newSettings = { ...settings, [key]: value };
    setSettings(newSettings);

    setSavingSettings(true);
    try {
      await updateIngestSettings({ [key]: value });
      toast.success('Settings updated');
    } catch (error) {
      toast.error('Failed to update settings');
      // Revert on error
      setSettings(settings);
    } finally {
      setSavingSettings(false);
    }
  };

  // Render UI immediately - data sections show inline loading states
  return (
    <TooltipProvider>
      <div className='container mx-auto space-y-6 p-6'>
        {/* Header */}
        <div className='flex items-center justify-between'>
          <div>
            <h1 className='text-2xl font-bold'>Token Ingestion Pipeline</h1>
            <p className='text-muted-foreground'>
              Discover and enrich tokens from DexScreener before full analysis
            </p>
          </div>
          <Button variant='outline' size='sm' onClick={fetchData}>
            <RefreshCw className='mr-2 h-4 w-4' />
            Refresh
          </Button>
        </div>

        {/* Stats Cards */}
        <div className='grid gap-4 md:grid-cols-5'>
          <Card>
            <CardHeader className='pb-2'>
              <CardTitle className='text-muted-foreground text-sm font-medium'>
                Total Queue
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className='text-2xl font-bold'>
                {loading ? (
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
                {tierConfig.ingested.label}
                <Tooltip>
                  <TooltipTrigger>
                    <Info className='h-3 w-3 text-blue-400/60' />
                  </TooltipTrigger>
                  <TooltipContent>{tierConfig.ingested.tooltip}</TooltipContent>
                </Tooltip>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className='text-2xl font-bold'>
                {loading ? (
                  <span className='text-muted-foreground'>--</span>
                ) : (
                  stats?.by_tier?.ingested || 0
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className='pb-2'>
              <CardTitle className='flex items-center gap-1 text-sm font-medium text-green-400'>
                {tierConfig.enriched.label}
                <Tooltip>
                  <TooltipTrigger>
                    <Info className='h-3 w-3 text-green-400/60' />
                  </TooltipTrigger>
                  <TooltipContent>{tierConfig.enriched.tooltip}</TooltipContent>
                </Tooltip>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className='text-2xl font-bold'>
                {loading ? (
                  <span className='text-muted-foreground'>--</span>
                ) : (
                  stats?.by_tier?.enriched || 0
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
                {loading ? (
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
                {loading ? (
                  <span className='text-muted-foreground'>--</span>
                ) : (
                  stats?.by_tier?.discarded || 0
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Controls & Settings */}
        <Tabs defaultValue='queue' className='space-y-4'>
          <TabsList>
            <TabsTrigger value='queue'>Queue</TabsTrigger>
            <TabsTrigger value='settings'>Settings</TabsTrigger>
          </TabsList>

          <TabsContent value='queue' className='space-y-4'>
            {/* Action Buttons */}
            <div className='flex flex-wrap items-center gap-2'>
              <Button
                onClick={handleRunTier0}
                disabled={runningTier0}
                variant='outline'
              >
                {runningTier0 ? (
                  <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                ) : (
                  <Play className='mr-2 h-4 w-4' />
                )}
                Run Tier-0 (DexScreener)
              </Button>

              <Button
                onClick={handleRunTier1}
                disabled={runningTier1}
                variant='outline'
              >
                {runningTier1 ? (
                  <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                ) : (
                  <Play className='mr-2 h-4 w-4' />
                )}
                Run Tier-1 (Helius)
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

              <div className='text-muted-foreground ml-auto flex items-center gap-2 text-sm'>
                {stats?.last_tier0_run_at && (
                  <span>
                    Last Tier-0: {formatTimestamp(stats.last_tier0_run_at)}
                  </span>
                )}
                {stats?.last_tier1_run_at && (
                  <>
                    <span className='mx-1'>|</span>
                    <span>
                      Last Tier-1: {formatTimestamp(stats.last_tier1_run_at)}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Tier Filter */}
            <div className='flex gap-2'>
              {['all', 'ingested', 'enriched', 'analyzed', 'discarded'].map(
                (tier) => {
                  const config = getTierDisplay(tier);
                  return (
                    <Tooltip key={tier}>
                      <TooltipTrigger asChild>
                        <Button
                          variant={
                            selectedTier === tier ? 'default' : 'outline'
                          }
                          size='sm'
                          onClick={() => handleTierChange(tier)}
                        >
                          {tier === 'all' ? 'All' : config.label}
                          {tier !== 'all' &&
                            stats?.by_tier?.[tier] !== undefined && (
                              <Badge variant='secondary' className='ml-2'>
                                {stats.by_tier[tier]}
                              </Badge>
                            )}
                        </Button>
                      </TooltipTrigger>
                      {tier !== 'all' && config.tooltip && (
                        <TooltipContent>{config.tooltip}</TooltipContent>
                      )}
                    </Tooltip>
                  );
                }
              )}
            </div>

            {/* Queue Table */}
            <Card>
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
                    <TableHead>Dashboard</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>First Seen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell
                        colSpan={11}
                        className='text-muted-foreground py-8 text-center'
                      >
                        <div className='flex items-center justify-center gap-2'>
                          <Loader2 className='h-4 w-4 animate-spin' />
                          Loading queue...
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : loadError ? (
                    <TableRow>
                      <TableCell colSpan={11} className='py-8 text-center'>
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
                        colSpan={11}
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
                            {isLive ? (
                              <span className='flex items-center gap-1 text-xs text-purple-400'>
                                <CheckCircle2 className='h-3 w-3' />
                                Live
                              </span>
                            ) : entry.tier === 'discarded' ? (
                              <span className='text-muted-foreground text-xs'>
                                Excluded
                              </span>
                            ) : (
                              <Tooltip>
                                <TooltipTrigger>
                                  <span className='text-xs text-yellow-400'>
                                    {tierDisplay.statusNote}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  {entry.tier === 'enriched'
                                    ? 'Promote to run full analysis and add to Tokens dashboard'
                                    : 'Run Tier-1 enrichment to prepare for promotion'}
                                </TooltipContent>
                              </Tooltip>
                            )}
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
                          <TableCell className='text-muted-foreground text-xs'>
                            {entry.first_seen_at
                              ? formatTimestamp(entry.first_seen_at)
                              : '-'}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
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
                        <Label>Tier-0 Ingestion (Scheduled)</Label>
                        <p className='text-muted-foreground text-sm'>
                          Auto-fetch tokens from DexScreener hourly
                        </p>
                      </div>
                      <Switch
                        checked={settings.ingest_enabled}
                        onCheckedChange={(v) =>
                          handleSettingChange('ingest_enabled', v)
                        }
                      />
                    </div>

                    <div className='flex items-center justify-between'>
                      <div>
                        <Label>Tier-1 Enrichment (Scheduled)</Label>
                        <p className='text-muted-foreground text-sm'>
                          Auto-enrich with Helius every 4 hours
                        </p>
                      </div>
                      <Switch
                        checked={settings.enrich_enabled}
                        onCheckedChange={(v) =>
                          handleSettingChange('enrich_enabled', v)
                        }
                      />
                    </div>

                    <div className='flex items-center justify-between'>
                      <div>
                        <Label>Auto-Promote</Label>
                        <p className='text-muted-foreground text-sm'>
                          Automatically promote enriched tokens to full analysis
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

                {/* Batch & Budget */}
                <Card>
                  <CardHeader>
                    <CardTitle>Batch & Budget Limits</CardTitle>
                  </CardHeader>
                  <CardContent className='grid gap-4 md:grid-cols-3'>
                    <div className='space-y-2'>
                      <Label>Tier-0 Max Tokens/Run</Label>
                      <Input
                        type='number'
                        value={settings.tier0_max_tokens_per_run}
                        onChange={(e) =>
                          handleSettingChange(
                            'tier0_max_tokens_per_run',
                            Number(e.target.value)
                          )
                        }
                      />
                    </div>

                    <div className='space-y-2'>
                      <Label>Tier-1 Batch Size</Label>
                      <Input
                        type='number'
                        value={settings.tier1_batch_size}
                        onChange={(e) =>
                          handleSettingChange(
                            'tier1_batch_size',
                            Number(e.target.value)
                          )
                        }
                      />
                    </div>

                    <div className='space-y-2'>
                      <Label>Tier-1 Credit Budget/Run</Label>
                      <Input
                        type='number'
                        value={settings.tier1_credit_budget_per_run}
                        onChange={(e) =>
                          handleSettingChange(
                            'tier1_credit_budget_per_run',
                            Number(e.target.value)
                          )
                        }
                      />
                    </div>
                  </CardContent>
                </Card>

                {/* Last Run Info */}
                {(settings.last_tier0_run_at || settings.last_tier1_run_at) && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Last Run Info</CardTitle>
                    </CardHeader>
                    <CardContent className='space-y-2 text-sm'>
                      {settings.last_tier0_run_at && (
                        <p>
                          <span className='text-muted-foreground'>
                            Last Tier-0:
                          </span>{' '}
                          {formatTimestamp(settings.last_tier0_run_at)}
                        </p>
                      )}
                      {settings.last_tier1_run_at && (
                        <p>
                          <span className='text-muted-foreground'>
                            Last Tier-1:
                          </span>{' '}
                          {formatTimestamp(settings.last_tier1_run_at)} (
                          {settings.last_tier1_credits_used} credits)
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Sticky Bottom Status Bar */}
      <StatusBar
        tokensScanned={stats?.by_tier?.analyzed ?? 0}
        latestAnalysis={
          statusBarData.latestAnalysis?.analysis_timestamp || null
        }
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
