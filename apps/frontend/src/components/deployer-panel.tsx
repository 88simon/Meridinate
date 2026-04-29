'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { X, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface DeployedToken {
  id: number;
  token_address: string;
  token_name: string | null;
  token_symbol: string | null;
  analysis_timestamp: string | null;
  market_cap_usd: number | null;
  market_cap_usd_current: number | null;
  market_cap_ath: number | null;
  verdict: string | null;
  win_multiplier: string | null;
}

interface DeployerProfile {
  deployer_address: string;
  tokens_deployed: number;
  wins: number;
  losses: number;
  pending: number;
  win_rate: number | null;
  avg_ath_multiple: number | null;
  tokens: DeployedToken[];
}

interface DeployerPanelProps {
  open: boolean;
  onClose: () => void;
  deployerAddress: string | null;
}

function formatMC(mc: number | null | undefined): string {
  if (!mc) return '—';
  if (mc >= 1_000_000) return `$${(mc / 1_000_000).toFixed(1)}M`;
  if (mc >= 1_000) return `$${(mc / 1_000).toFixed(1)}k`;
  return `$${mc.toFixed(0)}`;
}

export function DeployerPanel({ open, onClose, deployerAddress }: DeployerPanelProps) {
  const [profile, setProfile] = useState<DeployerProfile | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !deployerAddress) {
      setProfile(null);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/wallets/deployer-profile/${deployerAddress}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data) setProfile(data);
      })
      .catch(() => toast.error('Failed to load deployer profile'))
      .finally(() => setLoading(false));
  }, [open, deployerAddress]);

  if (!open) return null;

  return (
    <div
      className='fixed inset-0 z-50 flex justify-end bg-black/40'
      onClick={onClose}
    >
    <div
      className='flex h-full w-[420px] flex-col border-l bg-background shadow-xl animate-in slide-in-from-right duration-200'
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className='flex items-center justify-between border-b px-4 py-3'>
        <div>
          <h3 className='text-sm font-semibold'>Deployer Profile</h3>
          {deployerAddress && (
            <div className='flex items-center gap-1.5 mt-0.5'>
              <code className='text-muted-foreground text-[10px]'>
                {deployerAddress}
              </code>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(deployerAddress);
                  toast.success('Address copied');
                }}
                className='opacity-50 hover:opacity-100'
              >
                <Copy className='h-2.5 w-2.5' />
              </button>
            </div>
          )}
        </div>
        <Button variant='ghost' size='sm' onClick={onClose} className='h-7 w-7 p-0'>
          <X className='h-4 w-4' />
        </Button>
      </div>

      {/* Content */}
      <div className='flex-1 overflow-y-auto p-4 space-y-4'>
        {loading && (
          <div className='text-muted-foreground text-center text-sm py-8'>Loading...</div>
        )}

        {profile && !loading && (
          <>
            {/* Stats */}
            <div className='grid grid-cols-3 gap-2'>
              <div className='rounded-lg border p-2 text-center'>
                <div className='text-lg font-bold'>{profile.tokens_deployed}</div>
                <div className='text-muted-foreground text-[10px]'>Tokens Deployed</div>
              </div>
              <div className='rounded-lg border p-2 text-center'>
                <div className={cn('text-lg font-bold', profile.win_rate !== null && profile.win_rate >= 50 ? 'text-green-400' : 'text-red-400')}>
                  {profile.win_rate !== null ? `${profile.win_rate}%` : '—'}
                </div>
                <div className='text-muted-foreground text-[10px]'>Win Rate</div>
              </div>
              <div className='rounded-lg border p-2 text-center'>
                <div className='text-lg font-bold text-blue-400'>
                  {profile.avg_ath_multiple ? `${profile.avg_ath_multiple}x` : '—'}
                </div>
                <div className='text-muted-foreground text-[10px]'>Avg ATH Multiple</div>
              </div>
            </div>

            {/* Verdict Summary */}
            <div className='flex items-center gap-3 text-xs'>
              <span className='text-green-400'>{profile.wins} Wins</span>
              <span className='text-red-400'>{profile.losses} Losses</span>
              <span className='text-muted-foreground'>{profile.pending} Pending</span>
            </div>

            {/* Token List */}
            <div className='space-y-1.5'>
              <div className='text-xs font-medium'>Deployed Tokens</div>
              {profile.tokens.map((token) => (
                <div
                  key={token.id}
                  className={cn(
                    'flex items-center justify-between rounded-lg border p-2.5',
                    token.verdict === 'verified-win' ? 'border-green-500/20' :
                    token.verdict === 'verified-loss' ? 'border-red-500/20' : ''
                  )}
                >
                  <div className='min-w-0'>
                    <div className='text-sm font-medium truncate'>
                      {token.token_symbol || token.token_name || '—'}
                    </div>
                    <div className='text-muted-foreground text-[10px]'>
                      {token.token_name}
                      {token.analysis_timestamp && (
                        <span className='ml-1'>
                          · {new Date(token.analysis_timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className='flex items-center gap-2 shrink-0'>
                    <div className='text-right'>
                      <div className='text-[10px] text-muted-foreground'>
                        {formatMC(token.market_cap_usd_current)} / ATH {formatMC(token.market_cap_ath)}
                      </div>
                    </div>
                    {token.verdict === 'verified-win' ? (
                      <span className='rounded bg-green-500/20 px-1.5 py-0.5 text-[10px] font-medium text-green-400'>
                        WIN{token.win_multiplier ? ` ${token.win_multiplier.replace('win:', '').toUpperCase()}` : ''}
                      </span>
                    ) : token.verdict === 'verified-loss' ? (
                      <span className='rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] font-medium text-red-400'>
                        LOSS
                      </span>
                    ) : (
                      <span className='rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground'>
                        PENDING
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {!profile && !loading && (
          <div className='text-muted-foreground text-center text-sm py-8'>
            No deployer data found
          </div>
        )}
      </div>
    </div>
    </div>
  );
}
