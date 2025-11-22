'use client';

import {
  TopHolder,
  getTopHolders,
  SolscanSettings,
  getSolscanSettings,
  buildSolscanUrl
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Copy, ExternalLink, RefreshCw, Twitter } from 'lucide-react';
import { useState, useEffect } from 'react';
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
import { cn } from '@/lib/utils';

interface TopHoldersModalProps {
  tokenAddress: string;
  tokenSymbol?: string | null;
  initialHolders: TopHolder[] | null;
  lastUpdated: string | null;
  open: boolean;
  onClose: () => void;
  onRefreshComplete?: () => void;
}

export function TopHoldersModal({
  tokenAddress,
  tokenSymbol,
  initialHolders,
  lastUpdated,
  open,
  onClose,
  onRefreshComplete
}: TopHoldersModalProps) {
  const [holders, setHolders] = useState<TopHolder[] | null>(initialHolders);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [creditsUsed, setCreditsUsed] = useState<number>(0);
  const [solscanSettings, setSolscanSettings] =
    useState<SolscanSettings | null>(null);

  // Update holders when initialHolders changes (e.g., after page refresh)
  useEffect(() => {
    setHolders(initialHolders);
  }, [initialHolders]);

  // Fetch Solscan settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const settings = await getSolscanSettings();
        setSolscanSettings(settings);
      } catch {
        // Silently fail - will use basic Solscan URLs
      }
    };
    fetchSettings();
  }, []);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Address copied to clipboard');
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const result = await getTopHolders(tokenAddress);
      setHolders(result.holders);
      setCreditsUsed(result.api_credits_used);
      toast.success(
        `Refreshed top ${result.total_holders} holders (${result.api_credits_used} credits used)`
      );

      // Notify parent component to refresh token data
      if (onRefreshComplete) {
        onRefreshComplete();
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to refresh top holders');
    } finally {
      setIsRefreshing(false);
    }
  };

  // Format timestamp to relative time
  const formatTimeSinceUpdate = (timestamp: string): string => {
    const isoTimestamp = timestamp.replace(' ', 'T') + 'Z';
    const date = new Date(isoTimestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) {
      return `${diffDays}d ${diffHours % 24}h ago`;
    } else if (diffHours > 0) {
      return `${diffHours}h ${diffMins % 60}m ago`;
    } else if (diffMins > 0) {
      return `${diffMins}m ago`;
    } else {
      return 'Just now';
    }
  };

  if (!holders || holders.length === 0) {
    return (
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className='max-w-4xl'>
          <DialogHeader>
            <DialogTitle>Top 10 Token Holders</DialogTitle>
            <DialogDescription>
              No top holders data available yet. Click refresh to fetch.
            </DialogDescription>
          </DialogHeader>
          <div className='flex justify-center p-8'>
            <Button onClick={handleRefresh} disabled={isRefreshing}>
              {isRefreshing ? (
                <>
                  <RefreshCw className='mr-2 h-4 w-4 animate-spin' />
                  Refreshing...
                </>
              ) : (
                <>
                  <RefreshCw className='mr-2 h-4 w-4' />
                  Fetch Top Holders
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-h-[80vh] max-w-4xl overflow-y-auto'>
        <DialogHeader>
          <DialogTitle>Top 10 Token Holders</DialogTitle>
          <DialogDescription>
            Showing the largest {holders.length} token holders by balance.
            {lastUpdated && (
              <span className='ml-2 text-xs'>
                Last updated: {formatTimeSinceUpdate(lastUpdated)}
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className='mt-4'>
          {/* Token Address */}
          <div className='mb-4 rounded-lg border p-3'>
            <div className='flex items-center justify-between gap-2'>
              <div>
                <div className='text-muted-foreground text-xs font-medium'>
                  Token Address
                </div>
                <div className='font-mono text-sm break-all'>
                  {tokenAddress}
                </div>
              </div>
              <div className='flex gap-1'>
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant='outline'
                        size='sm'
                        className='h-8 w-8 p-0'
                        onClick={() => copyToClipboard(tokenAddress)}
                      >
                        <Copy className='h-3 w-3' />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className='text-xs'>Copy Address</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <a
                        href={`https://solscan.io/token/${tokenAddress}`}
                        target='_blank'
                        rel='noopener noreferrer'
                      >
                        <Button
                          variant='outline'
                          size='sm'
                          className='h-8 w-8 p-0'
                        >
                          <ExternalLink className='h-3 w-3' />
                        </Button>
                      </a>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className='text-xs'>View on Solscan</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>
          </div>

          {/* Holders Table */}
          <div className='rounded-lg border'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='w-12'>#</TableHead>
                  <TableHead>Wallet Address</TableHead>
                  <TableHead className='text-right'>
                    {tokenSymbol || 'TOKEN'} Balance
                  </TableHead>
                  <TableHead className='text-right'>Balance (USD)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {holders.map((holder, index) => (
                  <TableRow key={holder.address}>
                    <TableCell className='font-medium'>{index + 1}</TableCell>
                    <TableCell>
                      <div className='flex items-center gap-1'>
                        {solscanSettings ? (
                          <a
                            href={buildSolscanUrl(
                              holder.address,
                              solscanSettings
                            )}
                            target='_blank'
                            rel='noopener noreferrer'
                            className='text-primary truncate font-mono text-xs hover:underline'
                          >
                            {holder.address}
                          </a>
                        ) : (
                          <span className='font-mono text-xs'>
                            {holder.address}
                          </span>
                        )}
                        <a
                          href={`https://twitter.com/search?q=${encodeURIComponent(holder.address)}`}
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
                          onClick={() => copyToClipboard(holder.address)}
                        >
                          <Copy className='h-3 w-3' />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className='text-right font-semibold'>
                      {holder.token_balance_usd != null
                        ? `$${holder.token_balance_usd.toLocaleString('en-US', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2
                          })}`
                        : holder.uiAmountString}
                    </TableCell>
                    <TableCell className='text-right font-semibold'>
                      {holder.wallet_balance_usd != null
                        ? `$${holder.wallet_balance_usd.toLocaleString(
                            'en-US',
                            {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2
                            }
                          )}`
                        : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Refresh Button - Bottom Center */}
          <div className='mt-4 flex justify-center'>
            <TooltipProvider delayDuration={100}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={handleRefresh}
                    disabled={isRefreshing}
                    className='gap-2'
                  >
                    <RefreshCw
                      className={cn('h-4 w-4', isRefreshing && 'animate-spin')}
                    />
                    {isRefreshing ? 'Refreshing...' : 'Refresh Top Holders'}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className='text-xs'>Refresh top holders data</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          {/* Footer Info */}
          <div className='text-muted-foreground mt-4 text-center text-xs'>
            {creditsUsed > 0 ? (
              <>
                Last refresh used {creditsUsed} Helius API credit
                {creditsUsed !== 1 ? 's' : ''}. The credits have been added to
                the token&apos;s cumulative usage.
              </>
            ) : (
              <>
                Top holders data loaded from analysis. Click refresh to update.
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
