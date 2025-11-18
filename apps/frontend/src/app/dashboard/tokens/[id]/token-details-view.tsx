'use client';

import { TokenDetail, formatTimestamp, downloadAxiomJson } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Download, ExternalLink, Copy } from 'lucide-react';
import { useState } from 'react';
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
              href={`https://solscan.io/token/${token.token_address}`}
              target='_blank'
              rel='noopener noreferrer'
              className='text-primary mt-2 flex items-center text-xs hover:underline'
            >
              View on Solscan <ExternalLink className='ml-1 h-3 w-3' />
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
                token.wallets.map((wallet, index) => (
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
                      {wallet.wallet_balance_usd !== null &&
                      wallet.wallet_balance_usd !== undefined
                        ? `$${Math.round(wallet.wallet_balance_usd)}`
                        : 'N/A'}
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
                        <WalletTags walletAddress={wallet.wallet_address} />
                        <Button
                          variant='ghost'
                          size='sm'
                          onClick={() => copyAddress(wallet.wallet_address)}
                        >
                          <Copy className='h-4 w-4' />
                        </Button>
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
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
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
