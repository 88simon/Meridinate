'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getSwabStats,
  getSwabPositions,
  getSwabSettings,
  updateSwabSettings,
  batchStopSwabPositions,
  triggerSwabCheck,
  triggerSwabPnlUpdate,
  getSwabSchedulerStatus,
  purgeSwabData,
  reconcileAllPositions,
  SwabStats,
  SwabSettings,
  SwabPositionsResponse,
  SwabPosition,
  ReconciliationResponse
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Settings, Filter, RefreshCw, Play, AlertCircle, Trash2, Twitter, Copy, RotateCcw, Wrench } from 'lucide-react';
import { SwabSettingsPanel } from './swab-settings-panel';
import { SwabFilterPanel } from './swab-filter-panel';
import { WalletTagLabels } from '@/components/wallet-tag-labels';

interface SwabTabProps {
  isActive: boolean;
}

// Group positions by wallet address
interface WalletGroup {
  wallet_address: string;
  positions: SwabPosition[];
  total_positions: number;
  holding_count: number;
  sold_count: number;
  avg_pnl: number | null;
}

export function SwabTab({ isActive }: SwabTabProps) {
  const [stats, setStats] = useState<SwabStats | null>(null);
  const [settings, setSettings] = useState<SwabSettings | null>(null);
  const [positions, setPositions] = useState<SwabPositionsResponse | null>(null);
  const [schedulerStatus, setSchedulerStatus] = useState<{
    running: boolean;
    next_check_at: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkLoading, setCheckLoading] = useState(false);
  const [pnlUpdateLoading, setPnlUpdateLoading] = useState(false);
  const [batchUntrackLoading, setBatchUntrackLoading] = useState(false);
  const [purgeLoading, setPurgeLoading] = useState(false);
  const [reconcileLoading, setReconcileLoading] = useState(false);

  // Panel states
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  // Filter state (display filters only - MTEW gate is in settings)
  const [filters, setFilters] = useState({
    status: 'all' as 'holding' | 'sold' | 'stale' | 'all',
    pnl_min: undefined as number | undefined,
    pnl_max: undefined as number | undefined
  });

  // Pagination
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Multi-select state for batch untrack
  const [selectedPositions, setSelectedPositions] = useState<Set<number>>(new Set());

  const fetchData = useCallback(async () => {
    if (!isActive) return;

    try {
      // First fetch settings to get the MTEW→SWAB gate threshold
      const settingsData = await getSwabSettings();
      setSettings(settingsData);

      const [statsData, positionsData, schedulerData] = await Promise.all([
        getSwabStats(),
        getSwabPositions({
          // Use settings.min_token_count as the MTEW→SWAB gate
          min_token_count: settingsData.min_token_count,
          status: filters.status === 'all' ? undefined : filters.status,
          pnl_min: filters.pnl_min,
          pnl_max: filters.pnl_max,
          limit: pageSize,
          offset: page * pageSize
        }),
        getSwabSchedulerStatus()
      ]);

      setStats(statsData);
      setPositions(positionsData);
      setSchedulerStatus(schedulerData);
    } catch (error) {
      console.error('Error fetching SWAB data:', error);
    } finally {
      setLoading(false);
    }
  }, [isActive, filters, page]);

  useEffect(() => {
    if (isActive) {
      setLoading(true);
      fetchData();
    }
  }, [isActive, fetchData]);

  // Refresh every 30 seconds when active
  useEffect(() => {
    if (!isActive) return;

    const interval = setInterval(() => {
      fetchData();
    }, 30000);

    return () => clearInterval(interval);
  }, [isActive, fetchData]);

  // Group positions by wallet
  const walletGroups = useMemo((): WalletGroup[] => {
    if (!positions?.positions) return [];

    const grouped = new Map<string, SwabPosition[]>();
    for (const pos of positions.positions) {
      const existing = grouped.get(pos.wallet_address) || [];
      existing.push(pos);
      grouped.set(pos.wallet_address, existing);
    }

    const groups: WalletGroup[] = [];
    Array.from(grouped.entries()).forEach(([wallet_address, walletPositions]) => {
      const holding = walletPositions.filter((p: SwabPosition) => p.still_holding).length;
      const sold = walletPositions.filter((p: SwabPosition) => !p.still_holding).length;
      const pnlValues = walletPositions
        .filter((p: SwabPosition) => p.pnl_ratio != null)
        .map((p: SwabPosition) => p.pnl_ratio!);
      const avg_pnl = pnlValues.length > 0 ? pnlValues.reduce((a: number, b: number) => a + b, 0) / pnlValues.length : null;

      groups.push({
        wallet_address,
        positions: walletPositions,
        total_positions: walletPositions.length,
        holding_count: holding,
        sold_count: sold,
        avg_pnl
      });
    });

    return groups;
  }, [positions]);

  const handleSettingsUpdate = async (newSettings: Partial<SwabSettings>) => {
    try {
      const updated = await updateSwabSettings(newSettings);
      setSettings(updated);
      toast.success('SWAB settings updated');
      fetchData();
    } catch {
      toast.error('Failed to update settings');
    }
  };

  const handleTriggerCheck = async () => {
    setCheckLoading(true);
    try {
      const result = await triggerSwabCheck();
      toast.success(
        `Checked ${result.positions_checked} positions: ${result.still_holding} holding, ${result.sold} sold (${result.credits_used} credits)`
      );
      fetchData();
    } catch {
      toast.error('Failed to trigger position check');
    } finally {
      setCheckLoading(false);
    }
  };

  const handleTriggerPnlUpdate = async () => {
    setPnlUpdateLoading(true);
    try {
      const result = await triggerSwabPnlUpdate();
      toast.success(`Updated PnL for ${result.positions_updated} positions across ${result.tokens_updated} tokens`);
      fetchData();
    } catch {
      toast.error('Failed to update PnL ratios');
    } finally {
      setPnlUpdateLoading(false);
    }
  };

  const handleBatchUntrack = async () => {
    if (selectedPositions.size === 0) return;

    setBatchUntrackLoading(true);
    try {
      const result = await batchStopSwabPositions(Array.from(selectedPositions));
      toast.success(`Untracked ${result.positions_stopped} positions`);
      setSelectedPositions(new Set());
      fetchData();
    } catch {
      toast.error('Failed to untrack positions');
    } finally {
      setBatchUntrackLoading(false);
    }
  };

  const handlePurge = async () => {
    if (!confirm('This will delete ALL SWAB position tracking data. This action cannot be undone. Continue?')) {
      return;
    }

    setPurgeLoading(true);
    try {
      const result = await purgeSwabData();
      toast.success(`Purged ${result.positions_deleted} positions and ${result.metrics_deleted} wallet metrics`);
      setSelectedPositions(new Set());
      fetchData();
    } catch {
      toast.error('Failed to purge SWAB data');
    } finally {
      setPurgeLoading(false);
    }
  };

  const handleReconcile = async () => {
    setReconcileLoading(true);
    try {
      const result = await reconcileAllPositions({ max_positions: 50, max_signatures: 100 });

      if (result.positions_found === 0) {
        toast.info('No positions need reconciliation - all positions have sell data');
      } else {
        const successCount = result.positions_reconciled;
        const noTxCount = result.positions_no_tx_found;
        const errorCount = result.positions_error;

        if (successCount > 0) {
          toast.success(
            `Reconciled ${successCount}/${result.positions_found} positions (${result.credits_used} credits)` +
            (noTxCount > 0 ? ` - ${noTxCount} sells too old to find` : '')
          );
        } else if (noTxCount > 0) {
          toast.warning(
            `${noTxCount} sells too old to find (>100 transactions ago). ` +
            `PnL shown is MC-based estimate. Set up webhook for future accurate tracking.`,
            { duration: 8000 }
          );
        } else {
          toast.error(`Reconciliation failed for ${errorCount} positions`);
        }
      }
      fetchData();
    } catch {
      toast.error('Failed to reconcile positions');
    } finally {
      setReconcileLoading(false);
    }
  };

  const togglePositionSelection = (positionId: number) => {
    setSelectedPositions((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(positionId)) {
        newSet.delete(positionId);
      } else {
        newSet.add(positionId);
      }
      return newSet;
    });
  };

  const toggleAllSelection = () => {
    if (!positions?.positions) return;

    const trackablePositions = positions.positions.filter((p) => p.still_holding && p.tracking_enabled);
    if (selectedPositions.size === trackablePositions.length) {
      setSelectedPositions(new Set());
    } else {
      setSelectedPositions(new Set(trackablePositions.map((p) => p.id)));
    }
  };

  const formatPnl = (pnl: number | null | undefined, pnlUsd?: number | null) => {
    if (pnl === null || pnl === undefined) return '--';
    const formatted = pnl.toFixed(2);
    const usdFormatted =
      pnlUsd != null
        ? pnlUsd >= 0
          ? `+$${pnlUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
          : `-$${Math.abs(pnlUsd).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
        : null;

    const colorClass = pnl > 1 ? 'text-green-500' : pnl < 1 ? 'text-red-500' : 'text-yellow-500';

    return (
      <span className={colorClass}>
        {formatted}x{usdFormatted && <span className="text-muted-foreground ml-1 text-[10px]">({usdFormatted})</span>}
      </span>
    );
  };

  const formatMarketCap = (mc: number | null | undefined) => {
    if (mc === null || mc === undefined) return '--';
    if (mc >= 1000000) return `$${(mc / 1000000).toFixed(2)}M`;
    if (mc >= 1000) return `$${(mc / 1000).toFixed(1)}K`;
    return `$${mc.toFixed(0)}`;
  };

  const formatHoldTime = (seconds: number | null | undefined) => {
    if (seconds === null || seconds === undefined) return '--';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);

    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
  };

  const formatLastUpdated = (timestamp: string | null | undefined) => {
    if (!timestamp) return '--';
    // Database stores timestamps in UTC - append 'Z' to parse correctly
    const utcTimestamp = timestamp.includes('Z') || timestamp.includes('+') ? timestamp : timestamp + 'Z';
    const date = new Date(utcTimestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  if (!isActive) return null;

  const trackablePositions = positions?.positions.filter((p) => p.still_holding && p.tracking_enabled) || [];
  const allSelected = trackablePositions.length > 0 && selectedPositions.size === trackablePositions.length;

  return (
    <div className="space-y-2">
      {/* Compact Stats Bar */}
      <div className="flex items-center justify-center gap-4 py-1">
        {stats && (
          <>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold">{stats.total_positions}</span>
              <span className="text-muted-foreground text-xs">positions</span>
            </div>
            <div className="text-muted-foreground">|</div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold text-green-500">{stats.holding}</span>
              <span className="text-muted-foreground text-xs">holding</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold text-red-500">{stats.sold}</span>
              <span className="text-muted-foreground text-xs">sold</span>
            </div>
            <div className="text-muted-foreground">|</div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold">
                {stats.win_rate != null ? `${(stats.win_rate * 100).toFixed(0)}%` : '--'}
              </span>
              <span className="text-muted-foreground text-xs">win</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold">
                {stats.avg_pnl_ratio != null ? `${stats.avg_pnl_ratio.toFixed(1)}x` : '--'}
              </span>
              <span className="text-muted-foreground text-xs">avg</span>
            </div>
            <div className="text-muted-foreground">|</div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold text-yellow-500">{stats.stale_positions}</span>
              <span className="text-muted-foreground text-xs">stale</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-sm font-medium">{stats.credits_used_today}</span>
              <span className="text-muted-foreground text-xs">/{stats.daily_credit_budget} cr</span>
            </div>
          </>
        )}
      </div>

      {/* Controls - Centered */}
      <div className="flex items-center justify-center gap-2 py-1">
        {settings && (
          <button
            onClick={() => handleSettingsUpdate({ auto_check_enabled: !settings.auto_check_enabled })}
            className="flex items-center gap-1.5 rounded px-2 py-1 transition-colors hover:bg-muted"
            title={settings.auto_check_enabled ? 'Click to disable auto-check' : 'Click to enable auto-check'}
          >
            <div
              className={`h-2 w-2 rounded-full transition-colors ${settings.auto_check_enabled ? 'bg-green-500' : 'bg-gray-400'}`}
            />
            <span className={`text-xs font-medium ${settings.auto_check_enabled ? 'text-green-500' : 'text-muted-foreground'}`}>
              {settings.auto_check_enabled ? 'Auto' : 'Manual'}
            </span>
            {schedulerStatus?.next_check_at && settings.auto_check_enabled && (
              <span className="text-muted-foreground text-xs">
                ({new Date(schedulerStatus.next_check_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})
              </span>
            )}
          </button>
        )}

        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={handleTriggerPnlUpdate}
          disabled={pnlUpdateLoading}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${pnlUpdateLoading ? 'animate-spin' : ''}`} />
          PnL
        </Button>

        <Button
          variant="default"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={handleTriggerCheck}
          disabled={checkLoading || (stats?.credits_remaining ?? 0) < 10}
        >
          <Play className="mr-1 h-3 w-3" />
          {checkLoading ? '...' : `Check (~${stats?.estimated_check_credits ?? 0})`}
        </Button>

        <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => setIsSettingsOpen(true)} title="Settings">
          <Settings className="h-3.5 w-3.5" />
        </Button>

        <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => setIsFilterOpen(true)} title="Filter">
          <Filter className="h-3.5 w-3.5" />
        </Button>

        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7 text-orange-500 hover:bg-orange-500/20"
          onClick={handleReconcile}
          disabled={reconcileLoading}
          title="Reconcile sold positions (fix PnL for positions without sell data)"
        >
          {reconcileLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Wrench className="h-3.5 w-3.5" />}
        </Button>

        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7 text-destructive hover:bg-destructive hover:text-destructive-foreground"
          onClick={handlePurge}
          disabled={purgeLoading}
          title="Purge all SWAB data"
        >
          {purgeLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {/* Position Table */}
      <div className="rounded-lg border">
        <div className="border-b px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Position Tracking</span>
            <span className="text-muted-foreground text-xs">
              {positions?.total ?? 0} positions · {stats?.unique_wallets ?? 0} wallets
            </span>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-6">
            <RefreshCw className="text-muted-foreground h-5 w-5 animate-spin" />
          </div>
        ) : positions?.positions.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-6">
            <AlertCircle className="text-muted-foreground h-4 w-4" />
            <p className="text-muted-foreground text-sm">No positions tracked yet (analyze tokens with MTEWs to start)</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-card sticky top-0 z-10">
                <tr className="text-muted-foreground border-b text-left text-xs">
                  <th className="px-3 py-1.5">MTEW Wallet</th>
                  <th className="px-3 py-1.5">Token</th>
                  <th className="px-3 py-1.5 text-right">Entry MC</th>
                  <th className="px-3 py-1.5 text-right">Current MC</th>
                  <th className="px-3 py-1.5">Status</th>
                  <th className="px-3 py-1.5 text-right">PnL</th>
                  <th className="px-3 py-1.5 text-right">FPnL</th>
                  <th className="px-3 py-1.5 text-right">Hold Time</th>
                  <th className="px-3 py-1.5">Last Updated</th>
                  <th className="px-3 py-1.5 w-20">
                    <Button
                      variant={selectedPositions.size > 0 ? 'destructive' : 'ghost'}
                      size="sm"
                      className="h-5 px-2 text-[10px]"
                      onClick={selectedPositions.size > 0 ? handleBatchUntrack : toggleAllSelection}
                      disabled={batchUntrackLoading || trackablePositions.length === 0}
                    >
                      {batchUntrackLoading ? (
                        <RefreshCw className="h-3 w-3 animate-spin" />
                      ) : selectedPositions.size > 0 ? (
                        <>
                          <Trash2 className="mr-1 h-3 w-3" />
                          {selectedPositions.size}
                        </>
                      ) : (
                        'Untrack'
                      )}
                    </Button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {walletGroups.map((group, groupIndex) =>
                  group.positions.map((pos, posIndex) => (
                    <tr
                      key={pos.id}
                      className={`hover:bg-muted/30 border-b text-xs ${
                        posIndex === group.positions.length - 1 ? 'border-b-2' : ''
                      } ${!pos.still_holding ? 'opacity-50' : ''}`}
                    >
                      {/* Only show wallet on first row of group */}
                      <td className="px-3 py-1">
                        {posIndex === 0 ? (
                          <div className="flex flex-col gap-0.5">
                            <div className="flex items-center gap-1">
                              <span className="font-mono font-medium">
                                {pos.wallet_address.slice(0, 6)}...{pos.wallet_address.slice(-4)}
                              </span>
                              <a
                                href={`https://twitter.com/search?q=${encodeURIComponent(pos.wallet_address)}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="Search on Twitter/X"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Button variant="ghost" size="sm" className="h-5 w-5 p-0">
                                  <Twitter className="h-3 w-3" />
                                </Button>
                              </a>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-5 w-5 p-0"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  navigator.clipboard.writeText(pos.wallet_address);
                                  toast.success('Address copied to clipboard');
                                }}
                                title="Copy address"
                              >
                                <Copy className="h-3 w-3" />
                              </Button>
                            </div>
                            {group.total_positions > 1 && (
                              <span className="text-muted-foreground text-[10px]">
                                {group.holding_count}H / {group.sold_count}S · {group.avg_pnl?.toFixed(1) ?? '--'}x avg
                              </span>
                            )}
                            <WalletTagLabels walletAddress={pos.wallet_address} />
                          </div>
                        ) : null}
                      </td>
                      <td className="px-3 py-1">
                        <span className="font-medium">{pos.token_name}</span>
                        <span className="text-muted-foreground ml-1">({pos.token_symbol})</span>
                      </td>
                      <td className="px-3 py-1 text-right font-mono">{formatMarketCap(pos.entry_market_cap)}</td>
                      <td className="px-3 py-1 text-right font-mono">
                        {pos.still_holding ? formatMarketCap(pos.current_market_cap) : formatMarketCap(pos.exit_market_cap)}
                      </td>
                      <td className="px-3 py-1">
                        {pos.still_holding ? (
                          <span className="rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] text-green-500">Hold</span>
                        ) : (
                          <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] text-red-500">Sold</span>
                        )}
                      </td>
                      <td className="px-3 py-1 text-right font-mono">
                        {pos.pnl_ratio != null ? (
                          formatPnl(pos.pnl_ratio, pos.pnl_usd)
                        ) : !pos.still_holding && pos.fpnl_ratio != null ? (
                          <span className="text-muted-foreground" title="Estimated from market cap (no transaction data)">
                            ~{formatPnl(pos.fpnl_ratio)}
                          </span>
                        ) : (
                          '--'
                        )}
                      </td>
                      <td className="px-3 py-1 text-right font-mono">
                        {!pos.still_holding && pos.fpnl_ratio != null ? formatPnl(pos.fpnl_ratio) : '--'}
                      </td>
                      <td className="text-muted-foreground px-3 py-1 text-right">{formatHoldTime(pos.hold_time_seconds)}</td>
                      <td className="text-muted-foreground px-3 py-1">{formatLastUpdated(pos.position_checked_at)}</td>
                      <td className="px-3 py-1 text-center">
                        {pos.still_holding && pos.tracking_enabled && (
                          <input
                            type="checkbox"
                            checked={selectedPositions.has(pos.id)}
                            onChange={() => togglePositionSelection(pos.id)}
                            className="h-3.5 w-3.5 cursor-pointer rounded border-gray-300"
                          />
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {positions && positions.total > pageSize && (
          <div className="flex items-center justify-between border-t px-3 py-2">
            <span className="text-muted-foreground text-xs">
              {page * pageSize + 1}-{Math.min((page + 1) * pageSize, positions.total)} of {positions.total}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                className="h-6 px-2 text-xs"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-6 px-2 text-xs"
                disabled={!positions.has_more}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Settings Panel */}
      {isSettingsOpen && settings && (
        <SwabSettingsPanel settings={settings} onClose={() => setIsSettingsOpen(false)} onSave={handleSettingsUpdate} />
      )}

      {/* Filter Panel */}
      {isFilterOpen && (
        <SwabFilterPanel
          filters={filters}
          onClose={() => setIsFilterOpen(false)}
          onApply={(newFilters) => {
            setFilters(newFilters);
            setPage(0);
            setIsFilterOpen(false);
          }}
        />
      )}
    </div>
  );
}
