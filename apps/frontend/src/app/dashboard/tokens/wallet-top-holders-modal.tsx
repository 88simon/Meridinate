'use client';

import {
  TopHolder,
  getSolscanSettings,
  SolscanSettings,
  buildSolscanUrl,
  API_BASE_URL
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Copy, ExternalLink, Twitter } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';

interface WalletTopHolderToken {
  token_id: number;
  token_name: string;
  token_symbol: string;
  token_address: string;
  top_holders: TopHolder[];
  top_holders_limit: number;
  wallet_rank: number;
  last_updated: string | null;
}

interface WalletTopHolderTokensResponse {
  wallet_address: string;
  total_tokens: number;
  tokens: WalletTopHolderToken[];
}

interface WalletTopHoldersModalProps {
  walletAddress: string;
  open: boolean;
  onClose: () => void;
}

export function WalletTopHoldersModal({
  walletAddress,
  open,
  onClose
}: WalletTopHoldersModalProps) {
  const [tokensData, setTokensData] =
    useState<WalletTopHolderTokensResponse | null>(null);
  const [activeTokenIndex, setActiveTokenIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [solscanSettings, setSolscanSettings] =
    useState<SolscanSettings | null>(null);

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

  // Fetch top holder tokens when modal opens
  useEffect(() => {
    if (open && walletAddress) {
      fetchTopHolderTokens();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, walletAddress]);

  const fetchTopHolderTokens = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/wallets/${walletAddress}/top-holder-tokens`
      );
      if (!response.ok) {
        throw new Error('Failed to fetch top holder tokens');
      }
      const data: WalletTopHolderTokensResponse = await response.json();
      setTokensData(data);
      setActiveTokenIndex(0); // Reset to first tab
    } catch (error: any) {
      toast.error(error.message || 'Failed to load top holder tokens');
      setTokensData(null);
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Address copied to clipboard');
  };

  // Format timestamp to relative time
  const formatTimeSinceUpdate = (timestamp: string | null): string => {
    if (!timestamp) return 'Never';
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

  if (!tokensData || tokensData.tokens.length === 0) {
    return (
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className='max-w-4xl'>
          <DialogHeader>
            <DialogTitle>Top Holder Tokens</DialogTitle>
            <DialogDescription>
              {isLoading
                ? 'Loading...'
                : 'This wallet is not a top holder in any analyzed tokens.'}
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  const activeToken = tokensData.tokens[activeTokenIndex];

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-h-[85vh] max-w-5xl overflow-hidden'>
        <DialogHeader>
          <DialogTitle>Top Holder Tokens</DialogTitle>
          <DialogDescription>
            Wallet is a top holder in {tokensData.total_tokens} token
            {tokensData.total_tokens !== 1 ? 's' : ''}
          </DialogDescription>
        </DialogHeader>

        <div className='mt-2'>
          {/* Chrome-style Tabs */}
          <div className='mb-4 flex gap-1 overflow-x-auto border-b'>
            {tokensData.tokens.map((token, index) => (
              <button
                key={token.token_id}
                onClick={() => setActiveTokenIndex(index)}
                className={cn(
                  'flex-shrink-0 rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-all',
                  activeTokenIndex === index
                    ? 'border-primary bg-primary/5 text-foreground'
                    : 'border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <div className='flex items-center gap-2'>
                  <span className='truncate max-w-[150px]'>
                    {token.token_name}
                  </span>
                  <Badge
                    variant='outline'
                    className='flex-shrink-0 text-[10px]'
                  >
                    #{token.wallet_rank}
                  </Badge>
                </div>
              </button>
            ))}
          </div>

          {/* Active Tab Content */}
          <div className='max-h-[calc(85vh-200px)] overflow-y-auto'>
            {/* Token Info */}
            <div className='mb-4 rounded-lg border p-3'>
              <div className='flex items-center justify-between gap-2'>
                <div className='flex-1'>
                  {/* Token Name and Symbol */}
                  <div className='mb-2 flex items-center gap-2'>
                    <span className='text-sm font-semibold'>
                      {activeToken.token_name}
                    </span>
                    <span className='bg-primary/10 text-primary rounded px-2 py-0.5 text-xs font-mono font-medium'>
                      {activeToken.token_symbol}
                    </span>
                    <Badge variant='secondary' className='text-[10px]'>
                      Rank #{activeToken.wallet_rank} of{' '}
                      {activeToken.top_holders_limit}
                    </Badge>
                  </div>
                  <div className='text-muted-foreground text-xs font-medium'>
                    Token Address
                  </div>
                  <div className='font-mono text-sm break-all'>
                    {activeToken.token_address}
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
                          onClick={() =>
                            copyToClipboard(activeToken.token_address)
                          }
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
                          href={`https://solscan.io/token/${activeToken.token_address}`}
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
                      {activeToken.token_symbol || 'TOKEN'} Balance
                    </TableHead>
                    <TableHead className='text-right'>Balance (USD)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeToken.top_holders.map((holder, index) => {
                    const isCurrentWallet = holder.address === walletAddress;
                    return (
                      <TableRow
                        key={holder.address}
                        className={cn(
                          isCurrentWallet &&
                            'bg-primary/10 border-l-4 border-l-primary'
                        )}
                      >
                        <TableCell className='font-medium'>
                          {index + 1}
                        </TableCell>
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
                            {isCurrentWallet && (
                              <Badge variant='default' className='text-[10px]'>
                                YOU
                              </Badge>
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
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {/* Footer Info */}
            <div className='text-muted-foreground mt-4 text-center text-xs'>
              {activeToken.last_updated && (
                <>
                  Last updated:{' '}
                  {formatTimeSinceUpdate(activeToken.last_updated)}
                </>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
