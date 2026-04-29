'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import {
  TooltipProvider,
  Tooltip,
  TooltipTrigger,
  TooltipContent
} from '@/components/ui/tooltip';
import { getTagStyle } from '@/lib/wallet-tags';
import { TokenAddressCell } from '@/components/token-address-cell';

interface TokenPnl {
  token_id: number;
  token_address: string;
  token_name: string | null;
  token_symbol: string | null;
  dex_id: string | null;
  analysis_mc: number | null;
  total_bought_usd: number;
  total_sold_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
  total_pnl_usd: number;
  current_holdings: number;
  current_holdings_usd: number;
  trade_count: number;
  first_buy_timestamp: string | null;
  last_trade_timestamp: string | null;
}

interface WalletProfileData {
  wallet_address: string;
  total_pnl_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
  tokens_traded: number;
  tokens_won: number;
  tokens_lost: number;
  win_rate: number;
  best_trade_pnl: number;
  best_trade_token: string | null;
  worst_trade_pnl: number;
  worst_trade_token: string | null;
  computed_at: string | null;
  tags: string[];
  trades: TokenPnl[];
}

export default function WalletProfilePage() {
  const params = useParams();
  const router = useRouter();
  const address = params.address as string;

  const [profile, setProfile] = useState<WalletProfileData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/wallets/${address}/profile`
      );
      if (res.ok) {
        setProfile(await res.json());
      } else {
        toast.error('Wallet profile not found');
      }
    } catch {
      toast.error('Failed to load wallet profile');
    } finally {
      setLoading(false);
    }
  }, [address]);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const formatPnl = (value: number | null) => {
    if (value === null || value === undefined) return '—';
    const sign = value >= 0 ? '+' : '';
    return `${sign}$${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const pnlColor = (value: number | null) => {
    if (value === null || value === undefined || value === 0)
      return 'text-muted-foreground';
    return value > 0 ? 'text-green-400' : 'text-red-400';
  };

  if (loading) {
    return (
      <div className='flex h-screen items-center justify-center'>
        <div className='text-muted-foreground'>Loading wallet profile...</div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className='flex h-screen flex-col items-center justify-center gap-4'>
        <p className='text-muted-foreground'>
          No profile data for this wallet yet.
        </p>
        <Button variant='outline' onClick={() => router.back()}>
          Go Back
        </Button>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className='container mx-auto space-y-6 p-6'>
        {/* Header */}
        <div className='flex items-center justify-between'>
          <div>
            <div className='flex items-center gap-3'>
              <Button
                variant='ghost'
                size='sm'
                onClick={() => router.push('/dashboard/wallets')}
              >
                ← Back
              </Button>
              <h1 className='text-2xl font-bold'>Wallet Profile</h1>
            </div>
            <div className='mt-1 flex items-center gap-2'>
              <code className='text-muted-foreground text-sm'>
                {address}
              </code>
              <Tooltip>
                <TooltipTrigger asChild>
                  <a
                    href={`https://gmgn.ai/sol/address/${address}`}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='shrink-0 opacity-70 hover:opacity-100 transition-opacity'
                    onClick={(e) => e.stopPropagation()}
                  >
                    <img src='/gmgn-logo.png' alt='GMGN' className='h-5 w-5' />
                  </a>
                </TooltipTrigger>
                <TooltipContent>View on GMGN.ai</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <a
                    href={`https://solscan.io/account/${address}#transfers`}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='shrink-0 opacity-70 hover:opacity-100 transition-opacity'
                    onClick={(e) => e.stopPropagation()}
                  >
                    <img src='/solscan-logo.svg' alt='Solscan' className='h-5 w-5' />
                  </a>
                </TooltipTrigger>
                <TooltipContent>View on Solscan</TooltipContent>
              </Tooltip>
            </div>
          </div>
          <div className='flex items-center gap-2'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => {
                navigator.clipboard.writeText(address);
                toast.success('Address copied');
              }}
            >
              Copy Address
            </Button>
          </div>
        </div>

        {/* Tags */}
        {profile.tags.length > 0 && (
          <div className='flex flex-wrap gap-1.5'>
            {profile.tags.map((tag) => {
              const style = getTagStyle(tag);
              return (
                <span
                  key={tag}
                  className={`rounded-full px-2.5 py-1 text-xs font-medium ${style.bg} ${style.text}`}
                >
                  {tag}
                </span>
              );
            })}
          </div>
        )}

        {/* Stats Grid */}
        <div className='grid grid-cols-2 gap-4 md:grid-cols-4'>
          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground text-xs'>Total PnL</div>
            <div
              className={`text-xl font-bold ${pnlColor(profile.total_pnl_usd)}`}
            >
              {formatPnl(profile.total_pnl_usd)}
            </div>
          </div>
          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground text-xs'>Realized</div>
            <div
              className={`text-xl font-bold ${pnlColor(profile.realized_pnl_usd)}`}
            >
              {formatPnl(profile.realized_pnl_usd)}
            </div>
          </div>
          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground text-xs'>Win Rate</div>
            <div className='text-xl font-bold'>
              {profile.win_rate !== null
                ? `${(profile.win_rate * 100).toFixed(0)}%`
                : '—'}
            </div>
            <div className='text-muted-foreground text-xs'>
              {profile.tokens_won}W / {profile.tokens_lost}L of{' '}
              {profile.tokens_traded}
            </div>
          </div>
          <div className='rounded-lg border p-4'>
            <div className='text-muted-foreground text-xs'>Unrealized</div>
            <div
              className={`text-xl font-bold ${pnlColor(profile.unrealized_pnl_usd)}`}
            >
              {formatPnl(profile.unrealized_pnl_usd)}
            </div>
          </div>
        </div>

        {/* Trades Table */}
        <div>
          <h2 className='mb-3 text-lg font-semibold'>
            Token Trades ({profile.trades.length})
          </h2>
          <div className='rounded-lg border'>
            <div className='overflow-x-auto'>
              <table className='w-full text-sm'>
                <thead className='bg-muted/50'>
                  <tr className='border-b'>
                    <th className='px-3 py-2 text-left text-xs font-medium'>
                      Token
                    </th>
                    <th className='px-3 py-2 text-left text-xs font-medium'>
                      Launchpad
                    </th>
                    <th className='px-3 py-2 text-right text-xs font-medium'>
                      Bought
                    </th>
                    <th className='px-3 py-2 text-right text-xs font-medium'>
                      Sold
                    </th>
                    <th className='px-3 py-2 text-right text-xs font-medium'>
                      Realized PnL
                    </th>
                    <th className='px-3 py-2 text-right text-xs font-medium'>
                      Unrealized PnL
                    </th>
                    <th className='px-3 py-2 text-right text-xs font-medium'>
                      Total PnL
                    </th>
                    <th className='px-3 py-2 text-left text-xs font-medium'>
                      Status
                    </th>
                    <th className='px-3 py-2 text-left text-xs font-medium'>
                      Entry
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {profile.trades.length === 0 ? (
                    <tr>
                      <td
                        colSpan={9}
                        className='text-muted-foreground py-8 text-center'
                      >
                        No trades computed yet
                      </td>
                    </tr>
                  ) : (
                    profile.trades.map((trade) => (
                      <tr
                        key={trade.token_id}
                        className='hover:bg-blue-500/10 border-b'
                      >
                        <td className='px-3 py-2'>
                          <div
                            className='font-medium cursor-pointer hover:text-blue-400 transition-colors'
                            onClick={() => router.push(`/dashboard/tokens?search=${encodeURIComponent(trade.token_address)}`)}
                            title='View in Token Pipeline'
                          >
                            {trade.token_symbol || trade.token_name || '—'}
                          </div>
                          <div className='text-muted-foreground text-[10px]'>
                            <TokenAddressCell address={trade.token_address} compact showTwitter={false} />
                          </div>
                        </td>
                        <td className='px-3 py-2 text-xs'>
                          <span className='bg-muted rounded px-1.5 py-0.5 text-[10px]'>
                            {trade.dex_id || '—'}
                          </span>
                        </td>
                        <td className='px-3 py-2 text-right font-mono text-xs'>
                          ${trade.total_bought_usd?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0'}
                        </td>
                        <td className='px-3 py-2 text-right font-mono text-xs'>
                          ${trade.total_sold_usd?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0'}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono text-xs ${pnlColor(trade.realized_pnl_usd)}`}
                        >
                          {formatPnl(trade.realized_pnl_usd)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono text-xs ${pnlColor(trade.unrealized_pnl_usd)}`}
                        >
                          {formatPnl(trade.unrealized_pnl_usd)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono text-xs font-semibold ${pnlColor(trade.total_pnl_usd)}`}
                        >
                          {formatPnl(trade.total_pnl_usd)}
                        </td>
                        <td className='px-3 py-2 text-xs'>
                          {trade.current_holdings > 0 ? (
                            <span className='text-blue-400'>Holding</span>
                          ) : (
                            <span className='text-muted-foreground'>Sold</span>
                          )}
                        </td>
                        <td className='px-3 py-2 text-xs text-muted-foreground'>
                          {trade.first_buy_timestamp
                            ? new Date(
                                trade.first_buy_timestamp
                              ).toLocaleDateString()
                            : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {profile.computed_at && (
          <p className='text-muted-foreground text-right text-[10px]'>
            PnL computed{' '}
            {new Date(profile.computed_at).toLocaleString()}
          </p>
        )}
      </div>
    </TooltipProvider>
  );
}
