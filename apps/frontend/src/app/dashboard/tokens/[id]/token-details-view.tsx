'use client';

import {
  TokenDetail,
  formatTimestamp,
  downloadAxiomJson,
  getSolscanSettings,
  buildSolscanUrl,
  SolscanSettings
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Download, ExternalLink, Copy } from 'lucide-react';
import { useState, useRef, useMemo, useCallback, useEffect } from 'react';
import Link from 'next/link';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { WalletTags } from '@/components/wallet-tags';

interface TokenDetailsViewProps {
  token: TokenDetail;
}

export function TokenDetailsView({ token }: TokenDetailsViewProps) {
  const [copied, setCopied] = useState(false);
  const [solscanSettings, setSolscanSettings] = useState<SolscanSettings>({
    activity_type: 'ACTIVITY_SPL_TRANSFER',
    exclude_amount_zero: 'true',
    remove_spam: 'true',
    value: '100',
    token_address: 'So11111111111111111111111111111111111111111',
    page_size: '10'
  });

  // Virtualization state
  const walletsContainerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  // Handle scroll for virtualization
  const handleScroll = useCallback(() => {
    if (walletsContainerRef.current) {
      setScrollTop(walletsContainerRef.current.scrollTop);
    }
  }, []);

  // Update viewport height on mount and resize
  useEffect(() => {
    if (walletsContainerRef.current) {
      const updateHeight = () => {
        setViewportHeight(walletsContainerRef.current?.clientHeight ?? 0);
      };
      updateHeight();
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    }
  }, []);

  // Fetch Solscan settings on mount
  useEffect(() => {
    getSolscanSettings()
      .then(setSolscanSettings)
      .catch(() => {
        // Silently fail, keep default settings
      });
  }, []);

  // Virtualization logic
  const { visibleWallets, paddingTop, paddingBottom } = useMemo(() => {
    if (!token?.wallets) {
      return { visibleWallets: [], paddingTop: 0, paddingBottom: 0 };
    }

    const allWallets = token.wallets;
    const totalWallets = allWallets.length;
    const baseRowHeight = 80;
    const overscan = 5;
    const visibleCount =
      viewportHeight > 0
        ? Math.ceil(viewportHeight / Math.max(baseRowHeight, 1)) + overscan
        : totalWallets;
    const startIndex = Math.max(
      0,
      Math.floor(scrollTop / Math.max(baseRowHeight, 1)) - overscan
    );
    const endIndex = Math.min(totalWallets, startIndex + visibleCount);
    const visible = allWallets.slice(startIndex, endIndex);
    const paddingTop = startIndex * baseRowHeight;
    const paddingBottom = Math.max(
      0,
      (totalWallets - endIndex) * baseRowHeight
    );

    return {
      visibleWallets: visible,
      paddingTop,
      paddingBottom
    };
  }, [token, scrollTop, viewportHeight]);

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

  const copyAddress = (address: string) => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className='flex h-full flex-col space-y-6'>
      {/* Header */}
      <div className='flex items-center justify-between'>
        <div>
          <h1 className='text-3xl font-bold tracking-tight'>
            {token.token_name || 'Unknown Token'}
          </h1>
          <p className='text-muted-foreground'>
            {token.token_symbol || '-'} • Early Buyer Analysis
          </p>
        </div>
        <Button onClick={() => downloadAxiomJson(token)}>
          <Download className='mr-2 h-4 w-4' />
          Download Axiom JSON
        </Button>
      </div>

      {/* Token Info Cards */}
      <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-4'>
        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-muted-foreground text-sm font-medium'>
              Token Address
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className='flex items-center justify-between gap-2'>
              <code className='text-xs'>
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
              href={`https://gmgn.ai/sol/token/${token.token_address}?min=0.1&isInputValue=true`}
              target='_blank'
              rel='noopener noreferrer'
              className='text-primary mt-2 flex items-center text-xs hover:underline'
            >
              View on GMGN <ExternalLink className='ml-1 h-3 w-3' />
            </a>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-muted-foreground text-sm font-medium'>
              Acronym
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant='secondary' className='font-mono text-lg'>
              {token.acronym}
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-muted-foreground text-sm font-medium'>
              Wallets Found
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className='text-2xl font-bold'>{token.wallets_found}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className='pb-3'>
            <CardTitle className='text-muted-foreground text-sm font-medium'>
              Analyzed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className='text-sm'>
              {formatTimestamp(token.analysis_timestamp)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Early Buyer Wallets Table */}
      <Card>
        <CardHeader>
          <CardTitle>Early Buyer Wallets</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            ref={walletsContainerRef}
            onScroll={handleScroll}
            className='max-h-[600px] overflow-auto'
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='w-[60px]'>Rank</TableHead>
                  <TableHead>Wallet Address</TableHead>
                  <TableHead className='text-right'>Balance (USD)</TableHead>
                  <TableHead>First Buy Time</TableHead>
                  <TableHead className='text-right'>Amount (USD)</TableHead>
                  <TableHead className='text-center'>Txns</TableHead>
                  <TableHead className='text-right'>Avg Buy</TableHead>
                  <TableHead className='text-right'>Actions</TableHead>
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
                  <>
                    {paddingTop > 0 && (
                      <TableRow aria-hidden='true'>
                        <TableCell
                          colSpan={8}
                          className='p-0'
                          style={{ height: paddingTop }}
                        />
                      </TableRow>
                    )}
                    {visibleWallets.map((wallet) => {
                      const index = token.wallets.findIndex(
                        (w) => w.id === wallet.id
                      );
                      return (
                        <TableRow key={wallet.id}>
                          <TableCell className='text-primary font-semibold'>
                            #{index + 1}
                          </TableCell>
                          <TableCell>
                            <div className='flex flex-col gap-1'>
                              <div className='font-mono text-sm'>
                                {wallet.wallet_address}
                              </div>
                              <WalletTags
                                walletAddress={wallet.wallet_address}
                                compact
                              />
                            </div>
                          </TableCell>
                          <TableCell className='text-right font-mono text-sm'>
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
                          <TableCell className='text-right'>
                            <div className='flex items-center gap-2'>
                              <WalletTags
                                walletAddress={wallet.wallet_address}
                              />
                              <Button
                                variant='ghost'
                                size='sm'
                                onClick={() =>
                                  copyAddress(wallet.wallet_address)
                                }
                              >
                                <Copy className='h-4 w-4' />
                              </Button>
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
                        </TableRow>
                      );
                    })}
                    {paddingBottom > 0 && (
                      <TableRow aria-hidden='true'>
                        <TableCell
                          colSpan={8}
                          className='p-0'
                          style={{ height: paddingBottom }}
                        />
                      </TableRow>
                    )}
                  </>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Back Button */}
      <div>
        <Link href='/dashboard/tokens'>
          <Button variant='outline'>← Back to Tokens</Button>
        </Link>
      </div>
    </div>
  );
}
