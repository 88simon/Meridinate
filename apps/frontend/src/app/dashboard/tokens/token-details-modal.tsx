'use client';

import {
  TokenDetail,
  formatTimestamp,
  downloadAxiomJson,
  getTokenAnalysisHistory,
  AnalysisHistory,
  refreshWalletBalances
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Download,
  ExternalLink,
  Copy,
  History,
  Twitter,
  RefreshCw,
  Info
} from 'lucide-react';
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
  DialogTitle
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { WalletTags } from '@/components/wallet-tags';
import {
  AdditionalTagsPopover,
  WalletAddressWithBotIndicator
} from '@/components/additional-tags';

interface TokenDetailsModalProps {
  token: TokenDetail | null;
  open: boolean;
  onClose: () => void;
}

export function TokenDetailsModal({
  token,
  open,
  onClose
}: TokenDetailsModalProps) {
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<AnalysisHistory | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [refreshingWallets, setRefreshingWallets] = useState<Set<string>>(
    new Set()
  );
  const [refreshingAll, setRefreshingAll] = useState(false);

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
    }
  }, [open, token]);

  if (!token) return null;

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
        <DialogHeader>
          <div className='flex items-center justify-between'>
            <div>
              <DialogTitle className='text-2xl'>
                {token.token_name || 'Unknown Token'}
              </DialogTitle>
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
        <div className='mt-4 grid grid-cols-4 gap-4'>
          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground mb-2 text-sm font-medium'>
              Token Address
            </div>
            <div className='flex items-center gap-2'>
              <code className='text-xs break-all'>
                {token.token_address.slice(0, 16)}...
              </code>
              <Button
                variant='ghost'
                size='sm'
                onClick={() => copyAddress(token.token_address)}
              >
                {copied ? 'Copied!' : <Copy className='h-4 w-4' />}
              </Button>
            </div>
            <a
              href={`https://solscan.io/token/${token.token_address}`}
              target='_blank'
              rel='noopener noreferrer'
              className='text-primary mt-2 flex items-center text-xs hover:underline'
            >
              View on Solscan <ExternalLink className='ml-1 h-3 w-3' />
            </a>
          </div>

          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground mb-2 text-sm font-medium'>
              Acronym
            </div>
            <Badge variant='secondary' className='font-mono text-lg'>
              {token.acronym}
            </Badge>
          </div>

          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground mb-2 text-sm font-medium'>
              Wallets Found
            </div>
            <div className='text-2xl font-bold'>{token.wallets_found}</div>
          </div>

          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground mb-2 text-sm font-medium'>
              Analyzed
            </div>
            <div className='text-sm'>
              {formatTimestamp(token.analysis_timestamp)}
            </div>
          </div>
        </div>

        {/* Tabs for Current Analysis and History */}
        <Tabs defaultValue='current' className='mt-6'>
          <TabsList className='grid w-full grid-cols-2'>
            <TabsTrigger value='current'>Latest Analysis</TabsTrigger>
            <TabsTrigger value='history'>
              <History className='mr-2 h-4 w-4' />
              History ({history?.total_runs || 0} runs)
            </TabsTrigger>
          </TabsList>

          {/* Current Analysis Tab */}
          <TabsContent value='current'>
            <div className='mt-4 rounded-md border'>
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
                                Refreshing a single wallet balance costs 1 API
                                credit
                              </p>
                              <p className='text-xs'>
                                Refreshing all {token.wallets.length} wallet(s)
                                costs {token.wallets.length} API credits
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
                    <TableHead className='text-right'>Tags</TableHead>
                    <TableHead>First Buy Time</TableHead>
                    <TableHead className='text-right'>Amount (USD)</TableHead>
                    <TableHead className='text-center'>Txns</TableHead>
                    <TableHead className='text-right'>Avg Buy</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {token.wallets.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={8}
                        className='text-muted-foreground py-12 text-center'
                      >
                        No wallets found
                      </TableCell>
                    </TableRow>
                  ) : (
                    token.wallets.map((wallet, index) => (
                      <TableRow key={wallet.id}>
                        <TableCell className='text-primary font-semibold'>
                          #{index + 1}
                        </TableCell>
                        <TableCell className='font-mono text-sm'>
                          <div className='flex items-center gap-2'>
                            <WalletAddressWithBotIndicator
                              walletAddress={wallet.wallet_address}
                            >
                              {wallet.wallet_address}
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
                              >
                                <Twitter className='h-3 w-3' />
                              </Button>
                            </a>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-6 w-6 p-0'
                              onClick={() => copyAddress(wallet.wallet_address)}
                            >
                              <Copy className='h-3 w-3' />
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell className='text-right font-mono text-sm'>
                          <div className='flex items-center justify-end gap-2'>
                            <span>
                              {wallet.wallet_balance_usd !== null &&
                              wallet.wallet_balance_usd !== undefined
                                ? `$${Math.round(wallet.wallet_balance_usd)}`
                                : 'N/A'}
                            </span>
                            <Button
                              variant='ghost'
                              size='sm'
                              className='h-6 w-6 p-0'
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRefreshBalance(wallet.wallet_address);
                              }}
                              disabled={
                                refreshingWallets.has(wallet.wallet_address) ||
                                refreshingAll
                              }
                              title='Refresh balance - 1 API credit'
                            >
                              <RefreshCw
                                className={`h-3 w-3 ${refreshingWallets.has(wallet.wallet_address) ? 'animate-spin' : ''}`}
                              />
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell className='text-right'>
                          <div className='flex justify-end gap-2'>
                            <WalletTags walletAddress={wallet.wallet_address} />
                            <AdditionalTagsPopover
                              walletId={wallet.id}
                              walletAddress={wallet.wallet_address}
                            />
                            <a
                              href={`https://solscan.io/account/${wallet.wallet_address}`}
                              target='_blank'
                              rel='noopener noreferrer'
                            >
                              <Button variant='outline' size='sm'>
                                <ExternalLink className='h-4 w-4' />
                              </Button>
                            </a>
                          </div>
                        </TableCell>
                        <TableCell className='text-sm'>
                          {formatTimestamp(wallet.first_buy_timestamp)}
                        </TableCell>
                        <TableCell className='text-right'>
                          {wallet.total_usd
                            ? `$${Math.round(wallet.total_usd)}`
                            : 'N/A'}
                        </TableCell>
                        <TableCell className='text-center'>
                          {wallet.transaction_count || 1}
                        </TableCell>
                        <TableCell className='text-right'>
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
                    .reduce((sum, prevRun) => sum + prevRun.wallets_found, 0);
                  const startWallet = walletOffset + 1;
                  const endWallet = walletOffset + run.wallets_found;
                  const analysisNumber = history.runs.length - runIndex;

                  return (
                    <div key={run.id} className='rounded-lg border p-4'>
                      <div className='mb-3 flex items-center justify-between'>
                        <div>
                          <h4 className='text-sm font-semibold'>
                            Analysis #{analysisNumber} (Wallets {startWallet}-
                            {endWallet})
                            {runIndex === 0 && (
                              <Badge variant='secondary' className='ml-2'>
                                Latest
                              </Badge>
                            )}
                          </h4>
                          <p className='text-muted-foreground text-xs'>
                            {formatTimestamp(run.analysis_timestamp)}
                          </p>
                        </div>
                        <div className='text-right text-sm'>
                          <div className='font-semibold'>
                            {run.wallets_found} wallets
                          </div>
                          <div className='text-muted-foreground text-xs'>
                            {run.credits_used} credits
                          </div>
                        </div>
                      </div>

                      <div className='rounded-md border'>
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
                                          Refreshing all {run.wallets.length}{' '}
                                          wallet(s) costs {run.wallets.length}{' '}
                                          API credits
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
                                  colSpan={8}
                                  className='text-muted-foreground py-8 text-center text-sm'
                                >
                                  No wallets in this run
                                </TableCell>
                              </TableRow>
                            ) : (
                              run.wallets.map((wallet, index) => (
                                <TableRow key={wallet.id}>
                                  <TableCell className='text-primary text-sm font-semibold'>
                                    #{walletOffset + index + 1}
                                  </TableCell>
                                  <TableCell className='font-mono text-xs'>
                                    <div className='flex items-center gap-1'>
                                      <WalletAddressWithBotIndicator
                                        walletAddress={wallet.wallet_address}
                                      >
                                        {wallet.wallet_address}
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
                                          copyAddress(wallet.wallet_address)
                                        }
                                      >
                                        <Copy className='h-2.5 w-2.5' />
                                      </Button>
                                    </div>
                                  </TableCell>
                                  <TableCell className='text-right font-mono text-xs'>
                                    <div className='flex items-center justify-end gap-1'>
                                      <span>
                                        {wallet.wallet_balance_usd !== null &&
                                        wallet.wallet_balance_usd !== undefined
                                          ? `$${Math.round(wallet.wallet_balance_usd)}`
                                          : 'N/A'}
                                      </span>
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
                                    <div className='flex justify-end gap-1'>
                                      <WalletTags
                                        walletAddress={wallet.wallet_address}
                                      />
                                      <AdditionalTagsPopover
                                        walletId={wallet.id}
                                        walletAddress={wallet.wallet_address}
                                        compact
                                      />
                                      <a
                                        href={`https://solscan.io/account/${wallet.wallet_address}`}
                                        target='_blank'
                                        rel='noopener noreferrer'
                                      >
                                        <Button variant='outline' size='sm'>
                                          <ExternalLink className='h-3 w-3' />
                                        </Button>
                                      </a>
                                    </div>
                                  </TableCell>
                                  <TableCell className='text-xs'>
                                    {formatTimestamp(
                                      wallet.first_buy_timestamp
                                    )}
                                  </TableCell>
                                  <TableCell className='text-right text-sm'>
                                    {wallet.total_usd
                                      ? `$${Math.round(wallet.total_usd)}`
                                      : 'N/A'}
                                  </TableCell>
                                  <TableCell className='text-center text-sm'>
                                    {wallet.transaction_count || 1}
                                  </TableCell>
                                  <TableCell className='text-right text-sm'>
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
      </DialogContent>
    </Dialog>
  );
}
