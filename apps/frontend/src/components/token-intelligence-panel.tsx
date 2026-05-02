'use client';

import { useEffect, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { X, Copy, ExternalLink, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { StarButton } from '@/components/star-button';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

function TipLabel({ label, tip }: { label: string; tip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className='text-muted-foreground cursor-help border-b border-dotted border-muted-foreground/30'>{label}</span>
      </TooltipTrigger>
      <TooltipContent className='max-w-xs text-xs'>{tip}</TooltipContent>
    </Tooltip>
  );
}

interface TokenData {
  id: number;
  token_address: string;
  token_name: string;
  token_symbol: string;
  dex_id: string | null;
  is_cashback: boolean | null;
  market_cap_usd: number | null;
  market_cap_usd_current: number | null;
  market_cap_ath: number | null;
  market_cap_usd_previous: number | null;
  liquidity_usd: number | null;
  analysis_timestamp: string | null;
  score_composite: number | null;
  score_momentum: number | null;
  score_smart_money: number | null;
  score_risk: number | null;
  verdict: string | null;
  win_multiplier: string | null;
  loss_tier: string | null;
  deployer_address: string | null;
  deployer_win_rate: number | null;
  deployer_tokens_deployed: number;
  wallets_found: number;
  credits_used: number | null;
  last_analysis_credits: number | null;
  mc_direction: string;
  mc_change_pct: number;
  fresh_wallet_pct: number | null;
  fresh_at_deploy_count: number | null;
  fresh_at_deploy_total: number | null;
  controlled_supply_score: number | null;
  bundle_cluster_count: number | null;
  bundle_cluster_size: number | null;
  stealth_holder_count: number | null;
  stealth_holder_pct: number | null;
  has_meteora_pool: boolean | null;
  meteora_pool_address: string | null;
  meteora_pool_created_at: string | null;
  meteora_pool_creator: string | null;
  meteora_creator_linked: boolean | null;
  meteora_link_type: string | null;
  meteora_lp_activity_json: string | null;
  aggregate_realized_pnl: number;
  real_pnl_wallets: number;
  holder_top1_pct: number | null;
  mint_authority_revoked: boolean | null;
  freeze_authority_active: boolean | null;
  hours_since_ath: number | null;
  clobr_score: number | null;
  clobr_support_usd: number | null;
  clobr_resistance_usd: number | null;
  clobr_sr_ratio: number | null;
  clobr_updated_at: string | null;
  rug_score: number | null;
  rug_score_json: string | null;
}

interface EarlyBuyer {
  wallet_address: string;
  total_usd: number;
  first_buy_timestamp: string | null;
  avg_entry_seconds: number | null;
  still_holding: number | null;
  realized_pnl: number | null;
  pnl_source: string | null;
}

function formatMC(v: number | null): string {
  if (!v) return '—';
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function formatUsd(v: number | null): string {
  if (v === null || v === undefined) return '—';
  const sign = v >= 0 ? '+' : '-';
  const abs = Math.abs(v);
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatUsdCompact(v: number | null): string {
  if (v === null || v === undefined) return '—';
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function relativeTime(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

interface Props {
  open: boolean;
  onClose: () => void;
  token: TokenData | null;
}

export function TokenIntelligencePanel({ open, onClose, token }: Props) {
  const { openWIR } = useWalletIntelligence();
  const [earlyBuyers, setEarlyBuyers] = useState<EarlyBuyer[]>([]);
  const [loadingBuyers, setLoadingBuyers] = useState(false);
  const [trackedWallets, setTrackedWallets] = useState<any[]>([]);
  const [loadingTracked, setLoadingTracked] = useState(false);

  useEffect(() => {
    if (!open || !token) { setEarlyBuyers([]); setTrackedWallets([]); return; }

    // Fetch early buyers
    setLoadingBuyers(true);
    fetch(`${API_BASE_URL}/api/tokens/${token.id}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.wallets) {
          setEarlyBuyers(data.wallets.slice(0, 20).map((w: any) => ({
            wallet_address: w.wallet_address,
            total_usd: w.total_usd || 0,
            first_buy_timestamp: w.first_buy_timestamp,
            avg_entry_seconds: w.avg_entry_seconds,
            still_holding: w.still_holding,
            realized_pnl: w.realized_pnl,
            pnl_source: w.pnl_source,
          })));
        }
      })
      .catch(() => {})
      .finally(() => setLoadingBuyers(false));

    // Fetch tracked wallet positions
    setLoadingTracked(true);
    fetch(`${API_BASE_URL}/api/tokens/${token.id}/wallet-pnl`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.positions) {
          setTrackedWallets(data.positions);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingTracked(false));
  }, [open, token]);

  if (!open || !token) return null;

  const meteora_lp = token.meteora_lp_activity_json
    ? (() => { try { return JSON.parse(token.meteora_lp_activity_json); } catch { return []; } })()
    : [];

  return (
    <TooltipProvider delayDuration={200}>
      <div
        className='flex h-full w-full flex-col border-l bg-background shadow-xl'
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-5 py-3'>
          <div>
            <div className='flex items-center gap-2'>
              <div className='flex items-center gap-2'>
                <h3 className='text-sm font-semibold'>Token Intelligence Report — {token.token_symbol || token.token_name || '—'}</h3>
                <StarButton type='token' address={token.token_address} size='md' />
              </div>
              {token.verdict === 'verified-win' && (
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                  token.win_multiplier && parseInt(token.win_multiplier.replace('win:', '')) >= 25
                    ? 'animate-shimmer bg-[length:200%_100%] bg-gradient-to-r from-yellow-600/30 via-amber-300/50 to-yellow-600/30 text-yellow-200'
                    : 'bg-green-500/20 text-green-400'
                }`}>
                  WIN{token.win_multiplier ? ` ${token.win_multiplier.replace('win:', '').toUpperCase()}` : ''}
                </span>
              )}
              {token.verdict === 'verified-loss' && (
                <span className='rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] font-bold text-red-400'>
                  {token.loss_tier === 'loss:rug' ? 'RUG PULL' :
                   token.loss_tier === 'loss:90' ? 'LOSS 90%+' :
                   token.loss_tier === 'loss:70' ? 'LOSS 70%+' :
                   token.loss_tier === 'loss:dead' ? 'DEAD' :
                   token.loss_tier === 'loss:stale' ? 'STALE' : 'LOSS'}
                </span>
              )}
              {token.mc_direction === 'up' && <TrendingUp className='h-4 w-4 text-green-400' />}
              {token.mc_direction === 'down' && <TrendingDown className='h-4 w-4 text-red-400' />}
              {token.mc_direction === 'flat' && <Minus className='h-4 w-4 text-muted-foreground' />}
            </div>
            <div className='flex items-center gap-2 mt-0.5'>
              <code className='text-muted-foreground text-[10px]'>{token.token_address}</code>
              <button onClick={() => { navigator.clipboard.writeText(token.token_address); toast.success('Copied'); }}
                className='opacity-50 hover:opacity-100'><Copy className='h-2.5 w-2.5' /></button>
              <a href={`https://gmgn.ai/sol/token/${token.token_address}`} target='_blank' rel='noopener noreferrer'
                className='opacity-50 hover:opacity-100'><img src='/gmgn-logo.png' alt='GMGN' className='h-3.5 w-3.5' /></a>
              <a href={`https://solscan.io/token/${token.token_address}`} target='_blank' rel='noopener noreferrer'
                className='opacity-50 hover:opacity-100'><img src='/solscan-logo.svg' alt='Solscan' className='h-3.5 w-3.5' /></a>
              <a href={`https://dexscreener.com/solana/${token.token_address}`} target='_blank' rel='noopener noreferrer'
                className='opacity-50 hover:opacity-100'><ExternalLink className='h-3 w-3' /></a>
            </div>
          </div>
          <Button variant='ghost' size='sm' onClick={onClose} className='h-7 w-7 p-0'>
            <X className='h-4 w-4' />
          </Button>
        </div>

        {/* Content */}
        <div className='flex-1 overflow-y-auto p-5 space-y-4'>

          {/* Market Data */}
          <div className='grid grid-cols-4 gap-3'>
            <div className='rounded-lg border p-3 text-center'>
              <div className='text-lg font-bold'>{formatMC(token.market_cap_usd_current)}</div>
              <div className='text-[9px]'><TipLabel label='Market Cap' tip='Current market cap from latest DexScreener refresh.' /></div>
              {token.mc_change_pct !== 0 && (
                <div className={`text-[10px] ${token.mc_change_pct > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {token.mc_change_pct > 0 ? '+' : ''}{token.mc_change_pct}%
                </div>
              )}
            </div>
            <div className='rounded-lg border p-3 text-center'>
              <div className='text-lg font-bold'>{formatMC(token.market_cap_ath)}</div>
              <div className='text-[9px]'><TipLabel label='ATH' tip='All-time high market cap. Estimated from price changes and PumpFun data.' /></div>
              {token.hours_since_ath !== null && (
                <div className='text-[10px] text-muted-foreground'>
                  {token.hours_since_ath < 1 ? 'Now' : token.hours_since_ath < 24 ? `${token.hours_since_ath.toFixed(0)}h ago` : `${(token.hours_since_ath / 24).toFixed(0)}d ago`}
                </div>
              )}
            </div>
            <div className='rounded-lg border p-3 text-center'>
              <div className='text-lg font-bold'>{formatMC(token.liquidity_usd)}</div>
              <div className='text-[9px]'><TipLabel label='Liquidity' tip='Total USD liquidity in the primary trading pool.' /></div>
            </div>
            <div className='rounded-lg border p-3 text-center'>
              <div className={cn('text-lg font-bold', token.aggregate_realized_pnl > 0 ? 'text-green-400' : token.aggregate_realized_pnl < 0 ? 'text-red-400' : '')}>
                {formatUsd(token.aggregate_realized_pnl)}
              </div>
              <div className='text-muted-foreground text-[9px]'>PnL ({token.real_pnl_wallets} wallets)</div>
            </div>
          </div>

          {/* Scores */}
          {token.score_composite !== null && (
            <div className='rounded-lg border p-3'>
              <div className='text-xs font-medium mb-2'>Scores</div>
              <div className='grid grid-cols-4 gap-3 text-center'>
                <div>
                  <div className='text-2xl font-bold'>{token.score_composite?.toFixed(0) ?? '—'}</div>
                  <div className='text-[9px]'><TipLabel label='Composite' tip='Weighted average of Momentum, Smart Money, and inverted Risk. Higher = better overall opportunity.' /></div>
                </div>
                <div>
                  <div className='text-lg font-mono'>{token.score_momentum?.toFixed(0) ?? '—'}</div>
                  <div className='text-[9px]'><TipLabel label='Momentum' tip='How well is the token performing? Based on MC growth, ATH proximity, and liquidity health. 0-100.' /></div>
                </div>
                <div>
                  <div className='text-lg font-mono'>{token.score_smart_money?.toFixed(0) ?? '—'}</div>
                  <div className='text-[9px]'><TipLabel label='Smart Money' tip='How many smart wallets bought early? Counts Consistent Winners, Snipers, Diversified, High SOL Balance. 0-100.' /></div>
                </div>
                <div>
                  <div className={cn('text-lg font-mono', (token.score_risk ?? 0) <= 30 ? 'text-green-400' : (token.score_risk ?? 0) <= 60 ? 'text-yellow-400' : 'text-red-400')}>
                    {token.score_risk?.toFixed(0) ?? '—'}
                  </div>
                  <div className='text-[9px]'><TipLabel label='Risk' tip='How risky? Factors: mint authority, freeze authority, holder concentration, liquidity ratio, Meteora pools. 0-100, lower = safer.' /></div>
                </div>
              </div>
            </div>
          )}

          {/* CLOBr Liquidity Profile */}
          {token.clobr_score !== null && token.clobr_score !== undefined && (
            <div className='rounded-lg border p-3'>
              <div className='flex items-center justify-between mb-2'>
                <div className='text-xs font-medium'>
                  <TipLabel label='CLOBr Liquidity' tip='Order-book liquidity profile from CLOBr. Measures buy support and sell resistance within 20% of current price.' />
                </div>
                {token.clobr_updated_at && (
                  <span className='text-[9px] text-muted-foreground'>{relativeTime(token.clobr_updated_at)}</span>
                )}
              </div>
              <div className={cn(
                'grid gap-3 text-center',
                token.clobr_support_usd !== null ? 'grid-cols-4' : 'grid-cols-1'
              )}>
                <div>
                  <div className={cn('text-lg font-bold',
                    token.clobr_score < 30 ? 'text-red-400' :
                    token.clobr_score < 60 ? 'text-yellow-400' : 'text-green-400'
                  )}>
                    {token.clobr_score}
                  </div>
                  <div className='text-[9px]'><TipLabel label='CLOBr Score' tip='Overall liquidity health score (0-100). Considers depth, spread, and support/resistance balance. Higher = healthier order book.' /></div>
                </div>
                {token.clobr_support_usd !== null && (
                  <>
                    <div>
                      <div className='text-lg font-mono text-green-400'>{formatUsdCompact(token.clobr_support_usd)}</div>
                      <div className='text-[9px]'><TipLabel label='Support' tip='Total USD buy orders within -20% of current price. Higher = stronger price floor.' /></div>
                    </div>
                    <div>
                      <div className='text-lg font-mono text-red-400'>{formatUsdCompact(token.clobr_resistance_usd)}</div>
                      <div className='text-[9px]'><TipLabel label='Resistance' tip='Total USD sell orders within +20% of current price. Higher = more selling pressure above.' /></div>
                    </div>
                    <div>
                      <div className={cn('text-lg font-mono',
                        (token.clobr_sr_ratio ?? 0) > 1.5 ? 'text-green-400' :
                        (token.clobr_sr_ratio ?? 0) >= 0.7 ? 'text-yellow-400' : 'text-red-400'
                      )}>
                        {token.clobr_sr_ratio !== null && token.clobr_sr_ratio !== undefined ? `${token.clobr_sr_ratio.toFixed(1)}x` : '—'}
                      </div>
                      <div className='text-[9px]'><TipLabel label='S/R Ratio' tip='Support-to-Resistance ratio. >1.5x = strong buy support (green). 0.7-1.5x = balanced (yellow). <0.7x = sell-heavy (red).' /></div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Rug Risk */}
          {token.rug_score != null && (() => {
            let signals: any[] = [];
            try {
              if (token.rug_score_json) {
                const parsed = JSON.parse(token.rug_score_json);
                signals = (parsed.signals || parsed || []).filter((s: any) => s.triggered);
              }
            } catch { /* ignore */ }
            const verdict = token.rug_score >= 60 ? 'HIGH RISK' : token.rug_score >= 40 ? 'MODERATE' : 'LOW';
            const color = token.rug_score >= 60 ? 'text-red-400' : token.rug_score >= 40 ? 'text-yellow-400' : 'text-green-400';
            const borderColor = token.rug_score >= 60 ? 'border-red-500/30' : token.rug_score >= 40 ? 'border-yellow-500/30' : 'border-green-500/30';
            return (
              <div className={cn('rounded-lg border p-3', borderColor)}>
                <div className='text-xs font-medium mb-2'>
                  <TipLabel label='Rug Risk' tip='Rug probability score based on volume/liquidity ratio, transaction density, holder patterns, and other on-chain signals.' />
                </div>
                <div className='flex items-center gap-2 mb-1'>
                  <span className={cn('text-lg font-bold', color)}>{token.rug_score}</span>
                  <span className={cn('text-[10px] font-medium', color)}>{verdict}</span>
                </div>
                {signals.length > 0 && (
                  <div className='space-y-0.5 mt-1'>
                    {signals.map((s: any, i: number) => (
                      <div key={i} className='text-[10px] text-muted-foreground'>
                        {s.label || s.name}: {s.detail || s.description}{s.points != null ? ` +${s.points}` : ''}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* Safety & Deployer */}
          <div className='rounded-lg border p-3'>
            <div className='text-xs font-medium mb-2'>Token Profile</div>
            <div className='space-y-1.5 text-[11px]'>
              <div className='flex justify-between'>
                <TipLabel label='Mint Authority' tip='Can the creator mint more tokens? Revoked = safe. Active = creator can inflate supply.' />
                <span className={token.mint_authority_revoked ? 'text-green-400' : 'text-red-400'}>
                  {token.mint_authority_revoked ? 'Revoked' : 'Active'}
                </span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Freeze Authority' tip='Can the creator freeze token transfers? Active = creator can lock your tokens.' />
                <span className={token.freeze_authority_active ? 'text-red-400' : 'text-green-400'}>
                  {token.freeze_authority_active ? 'Active' : 'None'}
                </span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Fees' tip='PumpFun fee type. Cashback = fees go to traders. Creator Fee = fees go to developer.' />
                <span>{token.is_cashback === true ? 'Cashback' : token.is_cashback === false ? 'Creator Fee' : '—'}</span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Top Holder' tip='% of total supply held by the single largest wallet. Lower = more distributed = healthier.' />
                <span>{token.holder_top1_pct ? `${token.holder_top1_pct.toFixed(1)}%` : '—'}</span>
              </div>
              {token.deployer_address && (
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>Deployer</span>
                  <div>
                    <span className='font-mono text-[10px] cursor-pointer hover:text-blue-400 break-all' onClick={() => openWIR(token.deployer_address!)}>
                      {token.deployer_address}
                    </span>
                    {token.deployer_win_rate !== null && (
                      <span className={cn('text-[10px] ml-1', token.deployer_win_rate >= 50 ? 'text-green-400' : 'text-red-400')}>
                        ({token.deployer_win_rate}% WR, {token.deployer_tokens_deployed} tokens)
                      </span>
                    )}
                  </div>
                </div>
              )}
              <div className='flex justify-between'>
                <span className='text-muted-foreground'>Early Buyers</span>
                <span>{token.wallets_found}</span>
              </div>
              <div className='flex justify-between'>
                <span className='text-muted-foreground'>Credits Used</span>
                <span>{token.credits_used ?? 0} total · {token.last_analysis_credits ?? 0} latest</span>
              </div>
            </div>
          </div>

          {/* Risk Signals */}
          <div className='rounded-lg border p-3'>
            <div className='text-xs font-medium mb-2'>Risk Signals</div>
            <div className='grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]'>
              <div className='flex justify-between'>
                <TipLabel label='Fresh %' tip='% of early buyers that were fresh wallets (created within 7 days). Higher = more suspicious.' />
                <span className={cn((token.fresh_wallet_pct ?? 0) > 50 ? 'text-red-400' : (token.fresh_wallet_pct ?? 0) > 30 ? 'text-yellow-400' : '')}>
                  {token.fresh_wallet_pct ? `${token.fresh_wallet_pct.toFixed(0)}%` : '—'}
                </span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Fresh@Deploy' tip='Fresh wallets that bought within 60 seconds of creation. Format: fresh/total early entries.' />
                <span className={cn((token.fresh_at_deploy_count ?? 0) > 0 ? 'text-orange-400' : '')}>
                  {token.fresh_at_deploy_total ? `${token.fresh_at_deploy_count}/${token.fresh_at_deploy_total}` : '—'}
                </span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Supply Control' tip='Controlled Supply Score (0-100). Combines fresh wallets near deploy, cluster overlap, and % of supply held by fresh wallets.' />
                <span className={cn((token.controlled_supply_score ?? 0) >= 50 ? 'text-red-400' : (token.controlled_supply_score ?? 0) >= 25 ? 'text-orange-400' : '')}>
                  {token.controlled_supply_score ? token.controlled_supply_score.toFixed(0) : '—'}
                </span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Bundle Clusters' tip='Same-second buy clustering. Format: clusters/largest. 3+ wallets buying at exact same second = likely coordinated.' />
                <span className={cn((token.bundle_cluster_size ?? 0) >= 5 ? 'text-red-400' : (token.bundle_cluster_count ?? 0) > 0 ? 'text-orange-400' : '')}>
                  {token.bundle_cluster_count ? `${token.bundle_cluster_count}/${token.bundle_cluster_size}` : '—'}
                </span>
              </div>
              <div className='flex justify-between'>
                <TipLabel label='Stealth Holders' tip='Top holders that made suspiciously small buys. Holds 1%+ supply but spent <$200. Indicates hidden supply control.' />
                <span className={cn((token.stealth_holder_pct ?? 0) >= 10 ? 'text-red-400' : (token.stealth_holder_count ?? 0) > 0 ? 'text-orange-400' : '')}>
                  {token.stealth_holder_count ? `${token.stealth_holder_count} (${token.stealth_holder_pct?.toFixed(0)}%)` : '—'}
                </span>
              </div>
            </div>
          </div>

          {/* Meteora Detection */}
          {!!token.has_meteora_pool && (
            <div className={cn('rounded-lg border p-3', token.meteora_creator_linked ? 'border-red-500/30' : 'border-purple-500/30')}>
              <div className='flex items-center gap-2 mb-2'>
                <div className='text-xs font-medium'>Meteora Analysis</div>
                <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-bold',
                  token.meteora_creator_linked ? 'bg-red-500/20 text-red-400' : 'bg-purple-500/20 text-purple-400'
                )}>
                  {token.meteora_creator_linked ? 'STEALTH SELL DETECTED' : 'POOL DETECTED'}
                </span>
              </div>

              {/* Pool Info */}
              <div className='space-y-1.5 text-[11px] mb-3'>
                {token.meteora_pool_address && (
                  <div className='flex justify-between'>
                    <TipLabel label='Pool Address' tip='The Meteora DLMM pool address for this token. This pool was created separately from PumpSwap — someone deliberately made it.' />
                    <div className='flex items-center gap-1'>
                      <code className='text-[10px] break-all'>{token.meteora_pool_address}</code>
                      <a href={`https://dexscreener.com/solana/${token.meteora_pool_address}`} target='_blank' rel='noopener noreferrer'
                        className='text-muted-foreground hover:text-foreground shrink-0' title='View on DexScreener'><ExternalLink className='h-2.5 w-2.5' /></a>
                    </div>
                  </div>
                )}
                {token.meteora_pool_created_at && (
                  <div className='flex justify-between'>
                    <TipLabel label='Pool Created' tip='When the Meteora pool was created. Compare with the token graduation time — pools created shortly after graduation are suspicious.' />
                    <span>{new Date(token.meteora_pool_created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                )}
                {token.meteora_pool_creator && (
                  <div className='flex justify-between'>
                    <TipLabel label='Pool Creator' tip='The wallet that created this Meteora pool. If connected to the deployer or early buyers, it suggests coordinated stealth selling.' />
                    <span className='font-mono text-[10px] cursor-pointer hover:text-blue-400 break-all'
                      onClick={() => token.meteora_pool_creator && openWIR(token.meteora_pool_creator)}>
                      {token.meteora_pool_creator}
                    </span>
                  </div>
                )}
              </div>

              {/* Linkage Explanation */}
              {token.meteora_creator_linked && token.meteora_link_type && (
                <div className='rounded bg-red-500/10 border border-red-500/20 p-2 mb-3'>
                  <div className='text-[10px] font-medium text-red-400 mb-1'>Insider Linkage Confirmed</div>
                  <p className='text-[10px] text-muted-foreground'>
                    {token.meteora_link_type === 'deployer_is_lp' && 'The deployer is directly providing liquidity on Meteora — they are stealth-selling their own token through LP provision.'}
                    {token.meteora_link_type === 'early_buyer_is_lp' && 'An early buyer is providing liquidity on Meteora. This wallet bought early and is now exiting through LP withdrawal.'}
                    {token.meteora_link_type === 'shared_funder' && 'The LP provider shares a funding source with the deployer — likely the same operator using different wallets.'}
                    {token.meteora_link_type === 'cluster_overlap' && 'The LP provider is in the same wallet cluster as early buyers — coordinated group controlling both buying and LP exits.'}
                    {token.meteora_link_type?.startsWith('coordinated_funding') && (
                      <>
                        Coordinated funding detected: multiple wallets involved in this token were funded from shared sources or within the same time window.
                        {token.meteora_link_type.includes('high') ? ' High confidence — shared unknown funders found.' : ' Medium confidence — temporal funding patterns match.'}
                      </>
                    )}
                  </p>
                </div>
              )}

              {/* LP Activity */}
              {meteora_lp.length > 0 && (
                <div className='border-t pt-2'>
                  <div className='text-[10px] font-medium mb-1.5'>
                    <TipLabel label={`LP Activity (${meteora_lp.length} events)`} tip='Liquidity pool add/remove events. "ADD (single)" = tokens deposited without SOL = sell wall setup. "REMOVE" = tokens/SOL withdrawn = profit extracted.' />
                  </div>
                  <div className='space-y-0.5 max-h-[200px] overflow-y-auto'>
                    {meteora_lp.map((evt: any, i: number) => (
                      <div key={i} className={cn(
                        'flex items-center justify-between text-[10px] rounded px-1.5 py-1 hover:bg-muted/50',
                        evt.type === 'add_single' ? 'border-l-2 border-orange-500/50' :
                        evt.type === 'add' ? 'border-l-2 border-green-500/50' :
                        evt.type === 'remove' ? 'border-l-2 border-red-500/50' :
                        'border-l-2 border-transparent'
                      )}>
                        <span className={cn('font-medium w-24',
                          evt.type === 'add_single' ? 'text-orange-400' :
                          evt.type === 'add' ? 'text-green-400' : 'text-red-400'
                        )}>
                          {evt.type === 'add_single' ? 'ADD (single-sided)' :
                           evt.type === 'add' ? 'ADD' :
                           evt.type === 'remove' ? 'REMOVE' :
                           evt.type === 'swap_sell' ? 'SWAP SELL' :
                           evt.type === 'swap' ? 'SWAP BUY' : evt.type.toUpperCase()}
                        </span>
                        <span className='text-muted-foreground font-mono cursor-pointer hover:text-blue-400'
                          onClick={(e) => { e.stopPropagation(); evt.wallet && openWIR(evt.wallet); }}>
                          {evt.wallet?.slice(0, 16)}...
                        </span>
                        <span className='text-right w-24'>
                          {evt.token_in > 0 ? `${evt.token_in.toLocaleString()} tok` : evt.token_out > 0 ? `+${evt.token_out.toLocaleString()} tok` : ''}
                        </span>
                        <span className='text-right w-16'>
                          {evt.sol_in > 0 ? `-${evt.sol_in.toFixed(2)} SOL` : evt.sol_out > 0 ? `+${evt.sol_out.toFixed(2)} SOL` : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* No LP data but pool exists */}
              {meteora_lp.length === 0 && (
                <div className='border-t pt-2'>
                  <p className='text-[10px] text-muted-foreground'>
                    Pool detected but no LP activity captured yet. Activity will be analyzed during the next MC tracker cycle.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Tracked Wallets — position status for this token */}
          <div className='rounded-lg border p-3'>
            <div className='text-xs font-medium mb-2'>
              <TipLabel
                label={`Tracked Wallets (${trackedWallets.length})`}
                tip='Wallets with position tracking data for this token. Shows buy/sell amounts, realized PnL, and current holding status.'
              />
            </div>
            {loadingTracked ? (
              <div className='py-4 text-center text-muted-foreground text-[11px]'>Loading...</div>
            ) : trackedWallets.length > 0 ? (
              <div className='space-y-0.5 max-h-[300px] overflow-y-auto'>
                {/* Summary bar */}
                <div className='flex items-center gap-4 text-[10px] text-muted-foreground mb-2 pb-2 border-b'>
                  <span className='text-green-400'>{trackedWallets.filter(w => w.status === 'holding').length} holding</span>
                  <span className='text-red-400'>{trackedWallets.filter(w => w.status === 'exited').length} exited</span>
                  <span>
                    Net PnL: <span className={cn(
                      trackedWallets.reduce((s, w) => s + (w.total_pnl_usd || 0), 0) > 0 ? 'text-green-400' : 'text-red-400'
                    )}>
                      {formatUsd(trackedWallets.reduce((s, w) => s + (w.total_pnl_usd || 0), 0))}
                    </span>
                  </span>
                </div>
                {trackedWallets.map((w) => (
                  <div
                    key={w.wallet_address}
                    className='flex items-center justify-between rounded px-1.5 py-1 hover:bg-blue-500/10 cursor-pointer text-[11px]'
                    onClick={() => openWIR(w.wallet_address)}
                  >
                    <div className='flex items-center gap-2'>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className={cn('h-2 w-2 rounded-full shrink-0',
                            w.status === 'holding' ? 'bg-green-400' : 'bg-red-400'
                          )} />
                        </TooltipTrigger>
                        <TooltipContent className='text-xs'>
                          {w.status === 'holding' ? `Holding ${w.current_holdings_usd > 0 ? `$${w.current_holdings_usd.toFixed(0)}` : ''}` : 'Exited'}
                        </TooltipContent>
                      </Tooltip>
                      <code className='font-mono text-[10px]'>{w.wallet_address.slice(0, 20)}...</code>
                    </div>
                    <div className='flex items-center gap-3 shrink-0 text-[10px]'>
                      {w.avg_entry_seconds !== null && w.avg_entry_seconds !== undefined && !isNaN(w.avg_entry_seconds) && (
                        <span className={cn(
                          w.avg_entry_seconds < 30 ? 'text-sky-400' :
                          w.avg_entry_seconds < 60 ? 'text-yellow-400' : 'text-muted-foreground'
                        )}>
                          {w.avg_entry_seconds < 60 ? `${w.avg_entry_seconds.toFixed(0)}s` : `${(w.avg_entry_seconds / 60).toFixed(0)}m`}
                        </span>
                      )}
                      <span className='text-muted-foreground'>
                        B: ${w.total_bought_usd >= 1000 ? `${(w.total_bought_usd / 1000).toFixed(1)}k` : (w.total_bought_usd || 0).toFixed(0)}
                      </span>
                      <span className='text-muted-foreground'>
                        S: ${w.total_sold_usd >= 1000 ? `${(w.total_sold_usd / 1000).toFixed(1)}k` : (w.total_sold_usd || 0).toFixed(0)}
                      </span>
                      <span className={cn('font-medium',
                        w.total_pnl_usd > 0 ? 'text-green-400' :
                        w.total_pnl_usd < 0 ? 'text-red-400' : 'text-muted-foreground'
                      )}>
                        {w.total_pnl_usd >= 0 ? '+' : '-'}${Math.abs(w.total_pnl_usd) >= 1000 ? `${(Math.abs(w.total_pnl_usd) / 1000).toFixed(1)}k` : Math.abs(w.total_pnl_usd).toFixed(0)}
                      </span>
                      {w.pnl_source !== 'helius_enhanced' && (
                        <span className='text-[8px] text-muted-foreground/50'>est</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className='py-4 text-center text-muted-foreground text-[11px]'>No tracked positions</div>
            )}
          </div>

          {/* Early Buyers (top 20) */}
          <div className='rounded-lg border p-3'>
            <div className='text-xs font-medium mb-2'>Early Buyers (Top 20)</div>
            {loadingBuyers ? (
              <div className='py-4 text-center text-muted-foreground text-[11px]'>Loading...</div>
            ) : earlyBuyers.length > 0 ? (
              <div className='space-y-0.5 max-h-[250px] overflow-y-auto'>
                {earlyBuyers.map((buyer, i) => (
                  <div key={buyer.wallet_address}
                    className='flex items-center justify-between rounded px-1.5 py-1 hover:bg-blue-500/10 cursor-pointer text-[11px]'
                    onClick={() => openWIR(buyer.wallet_address)}
                  >
                    <div className='flex items-center gap-2'>
                      <span className='text-muted-foreground w-5 text-right'>#{i + 1}</span>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className={cn('h-2 w-2 rounded-full shrink-0',
                            buyer.still_holding === 1 ? 'bg-green-400' :
                            buyer.still_holding === 0 ? 'bg-red-400' :
                            'bg-muted-foreground/30'
                          )} />
                        </TooltipTrigger>
                        <TooltipContent className='text-xs'>
                          {buyer.still_holding === 1 ? 'Still holding' :
                           buyer.still_holding === 0 ? 'Sold / Exited' :
                           'No position data'}
                        </TooltipContent>
                      </Tooltip>
                      <code className='font-mono text-[10px]'>{buyer.wallet_address}</code>
                    </div>
                    <div className='flex items-center gap-3 shrink-0'>
                      {buyer.avg_entry_seconds !== null && buyer.avg_entry_seconds !== undefined && !isNaN(buyer.avg_entry_seconds) && (
                        <span className={cn('text-[9px]',
                          buyer.avg_entry_seconds < 30 ? 'text-sky-400' :
                          buyer.avg_entry_seconds < 60 ? 'text-yellow-400' : 'text-muted-foreground'
                        )}>
                          {buyer.avg_entry_seconds < 60 ? `${buyer.avg_entry_seconds.toFixed(0)}s` : `${(buyer.avg_entry_seconds / 60).toFixed(0)}m`}
                        </span>
                      )}
                      {buyer.pnl_source === 'helius_enhanced' && buyer.realized_pnl !== null && (
                        <span className={cn('text-[9px] font-medium',
                          buyer.realized_pnl > 0 ? 'text-green-400' :
                          buyer.realized_pnl < 0 ? 'text-red-400' : 'text-muted-foreground'
                        )}>
                          {buyer.realized_pnl >= 0 ? '+' : '-'}${Math.abs(buyer.realized_pnl) >= 1000 ? `${(Math.abs(buyer.realized_pnl) / 1000).toFixed(1)}k` : Math.abs(buyer.realized_pnl).toFixed(0)}
                        </span>
                      )}
                      <span className='text-muted-foreground'>
                        {(() => {
                          // total_usd can be undefined for buyers we haven't enriched yet.
                          // Without this guard, toFixed throws and unmounts the whole panel.
                          const v = buyer.total_usd ?? 0;
                          return `$${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)}`;
                        })()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className='py-4 text-center text-muted-foreground text-[11px]'>No early buyer data</div>
            )}
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
