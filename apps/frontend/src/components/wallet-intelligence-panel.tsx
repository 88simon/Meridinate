'use client';

import { useEffect, useState, useCallback } from 'react';
import { useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { StarButton } from '@/components/star-button';
import { API_BASE_URL, traceFundingChains, traceForward, type FundingTrace, type ForwardTraceNode, type ForwardTraceResponse } from '@/lib/api';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { Button } from '@/components/ui/button';
import { TokenAddressCell } from '@/components/token-address-cell';
import { X, Copy, ChevronDown, ChevronRight, Loader2, ExternalLink, Pencil, Check, Trash2, Shield, Search } from 'lucide-react';
import { useWalletNametag, useWalletNametags } from '@/contexts/wallet-nametags-context';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { getTagStyle } from '@/lib/wallet-tags';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';

interface WalletIntelligence {
  wallet_address: string;
  profile: {
    tags: { tag: string; tier: number; source: string }[];
    identity: { name: string; type: string } | null;
    funded_by: { funder: string; funderName: string | null; funderType: string | null } | null;
    wallet_created_at: string | null;
    wallet_age_at_first_buy_hours: number | null;
    is_deployer: boolean;
    tokens_deployed: number;
  };
  performance: {
    tokens_bought_early: number;
    avg_entry_seconds: number | null;
    pct_entries_under_60s: number | null;
    total_bought_usd: number;
    total_sold_usd: number;
    total_realized_pnl: number;
    win_rate: number | null;
    wins: number;
    losses: number;
    still_holding: number;
    real_pnl_count: number;
    best_trade: { token_id?: number; token_name: string; realized_pnl: number } | null;
    worst_trade: { token_id?: number; token_name: string; realized_pnl: number } | null;
  };
  trades: {
    token_id: number;
    token_name: string;
    token_symbol: string;
    token_address: string;
    first_buy_timestamp: string | null;
    total_usd: number | null;
    entry_seconds?: number;
    verdict: string | null;
    win_multiplier: string | null;
    loss_tier: string | null;
    realized_pnl: number | null;
    total_bought_usd: number | null;
    total_sold_usd: number | null;
    still_holding: boolean | null;
    pnl_source: string;
  }[];
}

// ============================================================================
// Compact Funding Tree (inline in WIR)
// ============================================================================

interface FundingNode {
  address: string;
  name: string | null;
  type: string | null;
  fundedDate: string | null;
  fundedAmount: number | null;
  txSignature: string | null;
  children: FundingNode[];
  isTarget: boolean;
}

function buildSingleWalletTree(trace: FundingTrace): FundingNode[] {
  // Build a linear chain from terminal → ... → target wallet
  const nodes: FundingNode[] = [];

  // Walk chain in reverse (deepest funder first)
  const chain = [...trace.chain];
  let currentNode: FundingNode | null = null;

  for (let i = chain.length - 1; i >= 0; i--) {
    const hop = chain[i];
    const node: FundingNode = {
      address: hop.funder || '',
      name: hop.funder_name || null,
      type: hop.funder_type || null,
      fundedDate: hop.date || null,
      fundedAmount: hop.amount ?? null,
      txSignature: hop.tx_signature || null,
      children: currentNode ? [currentNode] : [],
      isTarget: false,
    };
    currentNode = node;
  }

  // The leaf is the target wallet
  const leaf: FundingNode = {
    address: trace.wallet_address,
    name: null,
    type: null,
    fundedDate: chain.length > 0 ? (chain[0].date || null) : null,
    fundedAmount: chain.length > 0 ? (chain[0].amount ?? null) : null,
    txSignature: chain.length > 0 ? (chain[0].tx_signature || null) : null,
    children: [],
    isTarget: true,
  };

  if (currentNode) {
    // Find deepest child-less node and attach leaf
    let deepest = currentNode;
    while (deepest.children.length > 0) deepest = deepest.children[0];
    deepest.children.push(leaf);
    nodes.push(currentNode);
  } else {
    nodes.push(leaf);
  }

  return nodes;
}

function formatFundingDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
  } catch { return dateStr; }
}

function FundingNodeRow({ node, depth, isLast }: { node: FundingNode; depth: number; isLast: boolean }) {
  return (
    <div className='relative'>
      {depth > 0 && (
        <div className='pointer-events-none absolute top-0 left-0 h-full' style={{ width: depth * 20 }}>
          <div className='border-muted-foreground/30 absolute border-l'
            style={{ left: (depth - 1) * 20 + 6, top: 0, height: isLast ? 12 : '100%' }} />
          <div className='border-muted-foreground/30 absolute border-t'
            style={{ left: (depth - 1) * 20 + 6, top: 12, width: 10 }} />
        </div>
      )}
      <div className='group flex items-center gap-1.5 rounded py-1 pr-2'
        style={{ paddingLeft: depth * 20 + (depth > 0 ? 20 : 2) }}>
        <div className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          node.isTarget ? 'bg-amber-400' :
          node.type === 'exchange' ? 'bg-blue-400' :
          node.type === 'protocol' ? 'bg-purple-400' : 'bg-muted-foreground'
        }`} />
        <div className='flex min-w-0 flex-1 flex-col'>
          <div className='flex items-center gap-1'>
            {node.name && <span className='text-[11px] font-medium'>{node.name}</span>}
            {node.type && (
              <span className={`rounded px-1 py-0.5 text-[8px] font-medium uppercase ${
                node.type === 'exchange' ? 'bg-blue-500/20 text-blue-400' :
                node.type === 'protocol' ? 'bg-purple-500/20 text-purple-400' :
                'bg-muted text-muted-foreground'
              }`}>{node.type}</span>
            )}
            {node.isTarget && (
              <span className='rounded bg-amber-500/20 px-1 py-0.5 text-[8px] font-medium text-amber-400'>TARGET</span>
            )}
          </div>
          <code className='text-muted-foreground font-mono text-[10px]'>{node.address}</code>
          {(node.fundedDate || node.fundedAmount != null) && (
            <span className='text-muted-foreground text-[9px]'>
              {node.fundedDate && formatFundingDate(node.fundedDate)}
              {node.fundedDate && node.fundedAmount != null && ' · '}
              {node.fundedAmount != null && `${node.fundedAmount.toFixed(3)} SOL`}
              {node.txSignature && (
                <>
                  {' · '}
                  <a
                    href={`https://solscan.io/tx/${node.txSignature}`}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-blue-400 hover:text-blue-300 underline'
                    onClick={(e) => e.stopPropagation()}
                  >
                    tx
                  </a>
                </>
              )}
            </span>
          )}
        </div>
        <div className='flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100'>
          <button onClick={() => { navigator.clipboard.writeText(node.address); toast.success('Copied'); }}
            className='text-muted-foreground hover:text-foreground rounded p-0.5' title='Copy'>
            <Copy className='h-2.5 w-2.5' />
          </button>
          <a href={`https://gmgn.ai/sol/address/${node.address}`} target='_blank' rel='noopener noreferrer'
            className='rounded p-0.5 opacity-70 hover:opacity-100' title='GMGN' onClick={(e) => e.stopPropagation()}>
            <img src='/gmgn-logo.png' alt='GMGN' className='h-2.5 w-2.5' />
          </a>
          <a href={`https://solscan.io/account/${node.address}`} target='_blank' rel='noopener noreferrer'
            className='text-muted-foreground hover:text-foreground rounded p-0.5' title='Solscan'>
            <ExternalLink className='h-2.5 w-2.5' />
          </a>
        </div>
      </div>
      {node.children.map((child, i) => (
        <FundingNodeRow key={child.address} node={child} depth={depth + 1} isLast={i === node.children.length - 1} />
      ))}
    </div>
  );
}

function truncateAddr(addr: string): string {
  if (addr.length <= 12) return addr;
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

function relativeTime(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    if (isNaN(d.getTime())) return '';
    const diff = Date.now() - d.getTime();
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.floor(days / 30);
    return `${months}mo ago`;
  } catch { return ''; }
}

function ForwardNodeRow({
  node,
  depth,
  isLast,
  onWalletClick,
}: {
  node: ForwardTraceNode;
  depth: number;
  isLast: boolean;
  onWalletClick: (addr: string) => void;
}) {
  const displayName = node.identity_name || null;
  const isKnown = node.is_known === true;

  return (
    <div className='relative'>
      {depth > 0 && (
        <div className='pointer-events-none absolute top-0 left-0 h-full' style={{ width: depth * 20 }}>
          <div className='border-muted-foreground/30 absolute border-l'
            style={{ left: (depth - 1) * 20 + 6, top: 0, height: isLast ? 12 : '100%' }} />
          <div className='border-muted-foreground/30 absolute border-t'
            style={{ left: (depth - 1) * 20 + 6, top: 12, width: 10 }} />
        </div>
      )}
      <div className='group flex items-center gap-1.5 rounded py-1 pr-2'
        style={{ paddingLeft: depth * 20 + (depth > 0 ? 20 : 2) }}>
        <div className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          isKnown ? 'bg-blue-400' : 'bg-muted-foreground'
        }`} />
        <div className='flex min-w-0 flex-1 flex-col'>
          <div className='flex items-center gap-1'>
            {displayName ? (
              <button
                onClick={() => onWalletClick(node.address)}
                className='text-[11px] font-medium text-blue-400 hover:text-blue-300 hover:underline cursor-pointer'
              >
                {displayName}
              </button>
            ) : (
              <button
                onClick={() => onWalletClick(node.address)}
                className='font-mono text-[10px] text-muted-foreground hover:text-blue-400 hover:underline cursor-pointer'
              >
                {truncateAddr(node.address)}
              </button>
            )}
            {isKnown && (
              <span className='rounded bg-blue-500/20 px-1 py-0.5 text-[8px] font-medium text-blue-400'>
                In DB
              </span>
            )}
          </div>
          {(node.amount != null || node.timestamp) && (
            <span className='text-muted-foreground text-[9px]'>
              {node.amount != null && `${node.amount.toFixed(3)} SOL`}
              {node.amount != null && node.timestamp && ' · '}
              {node.timestamp && relativeTime(node.timestamp)}
            </span>
          )}
        </div>
        <div className='flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100'>
          <button onClick={() => { navigator.clipboard.writeText(node.address); toast.success('Copied'); }}
            className='text-muted-foreground hover:text-foreground rounded p-0.5' title='Copy'>
            <Copy className='h-2.5 w-2.5' />
          </button>
          <a href={`https://gmgn.ai/sol/address/${node.address}`} target='_blank' rel='noopener noreferrer'
            className='rounded p-0.5 opacity-70 hover:opacity-100' title='GMGN' onClick={(e) => e.stopPropagation()}>
            <img src='/gmgn-logo.png' alt='GMGN' className='h-2.5 w-2.5' />
          </a>
          <a href={`https://solscan.io/account/${node.address}`} target='_blank' rel='noopener noreferrer'
            className='text-muted-foreground hover:text-foreground rounded p-0.5' title='Solscan'>
            <ExternalLink className='h-2.5 w-2.5' />
          </a>
        </div>
      </div>
      {node.children && node.children.map((child, i) => (
        <ForwardNodeRow key={child.address} node={child} depth={depth + 1} isLast={i === node.children.length - 1} onWalletClick={onWalletClick} />
      ))}
    </div>
  );
}

function CompactFundingTree({ walletAddress }: { walletAddress: string }) {
  const { openWIR } = useWalletIntelligence();
  const { openTIP } = useTokenIntelligence();

  const [expanded, setExpanded] = useState(false);
  // Direction: 'back' = existing backward trace, 'forward' = new forward trace
  const [direction, setDirection] = useState<'back' | 'forward'>('back');

  // Backward trace state
  const [loading, setLoading] = useState(false);
  const [tree, setTree] = useState<FundingNode[] | null>(null);
  const [credits, setCredits] = useState<number | null>(null);

  // Forward trace state
  const [fwdLoading, setFwdLoading] = useState(false);
  const [fwdData, setFwdData] = useState<ForwardTraceResponse | null>(null);
  const [fwdFetched, setFwdFetched] = useState(false);

  // Reset when wallet changes
  useEffect(() => {
    setTree(null);
    setCredits(null);
    setFwdData(null);
    setFwdFetched(false);
    setExpanded(false);
    setDirection('back');
  }, [walletAddress]);

  const loadTree = useCallback(async () => {
    if (tree || loading) return; // already loaded or in progress
    setLoading(true);
    try {
      const result = await traceFundingChains([walletAddress], 3, true);
      const trace = result.traces[walletAddress];
      if (trace && trace.chain.length > 0) {
        setTree(buildSingleWalletTree(trace));
      } else {
        setTree([]);
      }
      setCredits(result.total_credits);
    } catch {
      toast.error('Funding trace failed');
      setTree([]);
    } finally {
      setLoading(false);
    }
  }, [walletAddress, tree]);

  const loadForward = useCallback(async () => {
    if (fwdData) return; // already loaded
    setFwdLoading(true);
    try {
      const result = await traceForward(walletAddress, 2, 10);
      setFwdData(result);
      setFwdFetched(true);
    } catch {
      toast.error('Forward trace failed');
      setFwdFetched(true);
    } finally {
      setFwdLoading(false);
    }
  }, [walletAddress, fwdData]);

  return (
    <div className='rounded-lg border p-3'>
      <button
        onClick={() => setExpanded(!expanded)}
        className='flex w-full items-center gap-1.5 text-xs font-medium hover:text-foreground'
      >
        {expanded ? <ChevronDown className='h-3 w-3' /> : <ChevronRight className='h-3 w-3' />}
        Funding Tree
        {direction === 'back' && credits !== null && (
          <span className='text-muted-foreground text-[9px] font-normal ml-auto'>{credits} credits</span>
        )}
        {direction === 'forward' && fwdData && (
          <span className='text-muted-foreground text-[9px] font-normal ml-auto'>{fwdData.credits_used} credits</span>
        )}
        {!expanded && !tree && !fwdFetched && !loading && !fwdLoading && (
          <span className='text-muted-foreground text-[9px] font-normal ml-auto'>click to trace (uses credits)</span>
        )}
      </button>
      {expanded && (
        <div className='mt-2'>
          {/* Direction toggle */}
          <div className='flex items-center gap-1 mb-2'>
            <button
              onClick={() => setDirection('back')}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                direction === 'back'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              &larr; Trace Back
            </button>
            <button
              onClick={() => { setDirection('forward'); setExpanded(true); }}
              className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                direction === 'forward'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              Trace Forward &rarr;
            </button>
          </div>

          {/* Backward trace content */}
          {direction === 'back' && (
            <>
              {!tree && !loading && (
                <button
                  onClick={loadTree}
                  className='w-full rounded border border-dashed border-muted-foreground/30 py-2 text-[11px] text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors'
                >
                  Trace Back (est. ~300 credits)
                </button>
              )}
              {loading && (
                <div className='flex items-center gap-2 py-3 text-muted-foreground text-[11px]'>
                  <Loader2 className='h-3 w-3 animate-spin' /> Tracing funding chain...
                </div>
              )}
              {tree && tree.length > 0 && (
                <div className='space-y-0'>
                  {tree.map((root, i) => (
                    <FundingNodeRow key={root.address} node={root} depth={0} isLast={i === tree.length - 1} />
                  ))}
                </div>
              )}
              {tree && tree.length === 0 && !loading && (
                <p className='text-muted-foreground text-[11px] py-2'>No funding data available.</p>
              )}
            </>
          )}

          {/* Forward trace content */}
          {direction === 'forward' && (
            <>
              {!fwdFetched && !fwdLoading && (
                <button
                  onClick={loadForward}
                  className='w-full rounded border border-dashed border-muted-foreground/30 py-2 text-[11px] text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors'
                >
                  Trace Forward (est. ~200 credits)
                </button>
              )}
              {fwdLoading && (
                <div className='flex items-center gap-2 py-3 text-muted-foreground text-[11px]'>
                  <Loader2 className='h-3 w-3 animate-spin' /> Tracing forward recipients...
                </div>
              )}
              {fwdData && fwdData.tree && (
                <>
                  <div className='text-muted-foreground text-[9px] mb-1.5'>
                    {fwdData.total_recipients} recipient{fwdData.total_recipients !== 1 ? 's' : ''} found
                  </div>
                  <div className='space-y-0'>
                    <ForwardNodeRow
                      node={fwdData.tree}
                      depth={0}
                      isLast={true}
                      onWalletClick={openWIR}
                    />
                  </div>
                  {/* Cluster Activity */}
                  {fwdData.cluster_tokens && fwdData.cluster_tokens.length > 0 && (
                    <div className='mt-3 rounded border p-2'>
                      <h4 className='text-[10px] font-medium mb-1'>Cluster Activity</h4>
                      <div className='space-y-1'>
                        {fwdData.cluster_tokens.map((ct) => (
                          <div key={ct.token_id} className='flex items-center gap-1 text-[10px] text-muted-foreground'>
                            <span>{ct.buyer_count} wallet{ct.buyer_count !== 1 ? 's' : ''} in this tree bought</span>
                            <button
                              onClick={() => openTIP({ id: ct.token_id })}
                              className='text-blue-400 hover:text-blue-300 hover:underline font-medium'
                            >
                              {ct.token_name || ct.token_symbol}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {fwdFetched && !fwdData && !fwdLoading && (
                <p className='text-muted-foreground text-[11px] py-2'>No forward trace data available.</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function formatUsd(n: number | null): string {
  if (n === null || n === undefined) return '—';
  const abs = Math.abs(n);
  const sign = n >= 0 ? '+' : '-';
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatTime(seconds: number | null): string {
  if (seconds === null) return '—';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

// ============================================================================
// Main Panel
// ============================================================================

interface Props {
  open: boolean;
  onClose: () => void;
  walletAddress: string | null;
}

export function WalletIntelligencePanel({ open, onClose, walletAddress }: Props) {
  const { openTIP } = useTokenIntelligence();
  const [data, setData] = useState<WalletIntelligence | null>(null);
  const [loading, setLoading] = useState(false);
  const nametag = useWalletNametag(walletAddress);
  const { setNametag, clearNametag } = useWalletNametags();
  const [renaming, setRenaming] = useState(false);
  const [draftNametag, setDraftNametag] = useState('');
  const [saving, setSaving] = useState(false);

  // Reset rename UI whenever the panel switches to a different wallet.
  useEffect(() => {
    setRenaming(false);
    setDraftNametag(nametag || '');
  }, [walletAddress, nametag]);

  const startRename = () => { setDraftNametag(nametag || ''); setRenaming(true); };
  const cancelRename = () => { setRenaming(false); setDraftNametag(nametag || ''); };
  const saveNametag = async () => {
    if (!walletAddress) return;
    const trimmed = draftNametag.trim();
    if (!trimmed) return;
    setSaving(true);
    const ok = await setNametag(walletAddress, trimmed);
    setSaving(false);
    if (ok) { setRenaming(false); toast.success(`Saved as "${trimmed}"`); }
    else { toast.error('Failed to save nametag'); }
  };
  const removeNametag = async () => {
    if (!walletAddress) return;
    setSaving(true);
    const ok = await clearNametag(walletAddress);
    setSaving(false);
    if (ok) { setRenaming(false); setDraftNametag(''); toast.success('Nametag cleared'); }
    else { toast.error('Failed to clear nametag'); }
  };

  // Direct WIR actions — surfaced here because Allowlist promotion and Bot Probe
  // are deliberate decisions the operator makes after observing shadow data,
  // not triage-time choices on Intel recommendations.
  const [promoting, setPromoting] = useState(false);
  const [probing, setProbing] = useState(false);
  const promoteToAllowlist = async () => {
    if (!walletAddress) return;
    setPromoting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/wallets/${walletAddress}/promote-to-allowlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: '' }),
      });
      const data = await res.json();
      if (res.ok && data.success) toast.success('Promoted to allowlist (auto-shadowed)');
      else toast.error(data.message || 'Promote failed');
    } catch {
      toast.error('Promote failed');
    } finally {
      setPromoting(false);
    }
  };
  const queueBotProbe = async () => {
    if (!walletAddress) return;
    setProbing(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/wallets/${walletAddress}/queue-bot-probe`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.success) toast.success(data.message || 'Bot Probe queued');
      else toast.error(data.message || 'Queue failed');
    } catch {
      toast.error('Queue failed');
    } finally {
      setProbing(false);
    }
  };

  useEffect(() => {
    if (!open || !walletAddress) { setData(null); return; }
    setLoading(true);
    fetch(`${API_BASE_URL}/wallets/intelligence/${walletAddress}`)
      .then((r) => r.ok ? r.json() : null)
      .then(setData)
      .catch(() => toast.error('Failed to load wallet intelligence'))
      .finally(() => setLoading(false));
  }, [open, walletAddress]);

  if (!open) return null;

  const p = data?.profile;
  const perf = data?.performance;

  return (
    <TooltipProvider delayDuration={200}>
        <div
          className='flex h-full w-full flex-col border-l bg-background shadow-xl'
        >
          {/* Header */}
          <div className='flex items-center justify-between border-b px-4 py-3'>
            <div className='min-w-0 flex-1'>
              <div className='flex items-center gap-2'>
                <h3 className='text-sm font-semibold'>Wallet Intelligence Report</h3>
                {walletAddress && <StarButton type='wallet' address={walletAddress} size='md' />}
              </div>
              {walletAddress && (
                <div className='mt-1 flex items-center gap-1.5'>
                  {renaming ? (
                    <>
                      <input
                        type='text'
                        autoFocus
                        value={draftNametag}
                        onChange={(e) => setDraftNametag(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveNametag();
                          if (e.key === 'Escape') cancelRename();
                        }}
                        placeholder='Nametag (e.g. profitable scalper #1)'
                        maxLength={64}
                        disabled={saving}
                        className='flex-1 rounded border border-border bg-background px-2 py-0.5 text-[12px] focus:outline-none focus:ring-1 focus:ring-primary'
                      />
                      <button
                        onClick={saveNametag}
                        disabled={saving || !draftNametag.trim()}
                        title='Save (Enter)'
                        className='rounded bg-green-500/20 px-1.5 py-1 text-green-400 hover:bg-green-500/30 disabled:opacity-40'
                      >
                        <Check className='h-3 w-3' />
                      </button>
                      {nametag && (
                        <button
                          onClick={removeNametag}
                          disabled={saving}
                          title='Clear nametag'
                          className='rounded bg-red-500/10 px-1.5 py-1 text-red-400 hover:bg-red-500/20 disabled:opacity-40'
                        >
                          <Trash2 className='h-3 w-3' />
                        </button>
                      )}
                      <button
                        onClick={cancelRename}
                        disabled={saving}
                        title='Cancel (Esc)'
                        className='rounded px-1.5 py-1 text-muted-foreground hover:text-foreground'
                      >
                        <X className='h-3 w-3' />
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={startRename}
                      title={nametag ? 'Edit nametag' : 'Add nametag'}
                      className='group flex items-center gap-1 rounded px-1.5 py-0.5 text-[12px] hover:bg-muted/50'
                    >
                      {nametag ? (
                        <span className='font-medium text-cyan-400'>{nametag}</span>
                      ) : (
                        <span className='text-muted-foreground italic'>+ add nametag</span>
                      )}
                      <Pencil className='h-3 w-3 text-muted-foreground opacity-50 group-hover:opacity-100' />
                    </button>
                  )}
                </div>
              )}
              {walletAddress && (
                <div className='flex items-center gap-2 mt-0.5'>
                  <code className='text-muted-foreground text-[10px]'>{walletAddress}</code>
                  <button onClick={() => { navigator.clipboard.writeText(walletAddress); toast.success('Copied'); }}
                    className='opacity-50 hover:opacity-100'>
                    <Copy className='h-2.5 w-2.5' />
                  </button>
                  <a href={`https://gmgn.ai/sol/address/${walletAddress}`} target='_blank' rel='noopener noreferrer'
                    className='opacity-50 hover:opacity-100'>
                    <img src='/gmgn-logo.png' alt='GMGN' className='h-3.5 w-3.5' />
                  </a>
                  <a href={`https://solscan.io/account/${walletAddress}#transfers`} target='_blank' rel='noopener noreferrer'
                    className='opacity-50 hover:opacity-100'>
                    <img src='/solscan-logo.svg' alt='Solscan' className='h-3.5 w-3.5' />
                  </a>
                </div>
              )}
              {/* Direct actions — Promote to Allowlist + Bot Probe live here, not on the
                  Intel rec card, because they are deliberate post-observation decisions. */}
              {walletAddress && (
                <div className='mt-2 flex flex-wrap gap-1.5'>
                  <button
                    onClick={promoteToAllowlist}
                    disabled={promoting}
                    title='Add to Intel Allowlist (counts as anti-rug confluence + auto-shadowed)'
                    className='flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-green-500/15 text-green-400 hover:bg-green-500/25 disabled:opacity-40 transition-colors'
                  >
                    <Shield className='h-3 w-3' />
                    {promoting ? 'Promoting…' : 'Promote to Allowlist'}
                  </button>
                  <button
                    onClick={queueBotProbe}
                    disabled={probing}
                    title='Queue a deep historical Helius probe — costs credits, runs from Bot Probe page'
                    className='flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 disabled:opacity-40 transition-colors'
                  >
                    <Search className='h-3 w-3' />
                    {probing ? 'Queuing…' : 'Queue Bot Probe'}
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
            {loading && <div className='py-8 text-center text-muted-foreground text-sm'>Loading intelligence report...</div>}

            {data && !loading && (
              <>
                {/* Tags */}
                {p && p.tags.length > 0 && (
                  <div className='flex flex-wrap gap-1'>
                    {p.tags.map((t) => {
                      const style = getTagStyle(t.tag);
                      return (
                        <span key={t.tag} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${style.bg} ${style.text}`}>
                          {t.tag}
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Profile */}
                <div className='rounded-lg border p-3'>
                  <div className='text-xs font-medium mb-2'>Profile</div>
                  <div className='space-y-1.5 text-[11px]'>
                    {p?.identity && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Identity</span>
                        <span className='text-blue-400'>{p.identity.name} ({p.identity.type})</span>
                      </div>
                    )}
                    {p?.wallet_age_at_first_buy_hours !== null && p?.wallet_age_at_first_buy_hours !== undefined && (
                      <div className='flex justify-between'>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className='text-muted-foreground cursor-help border-b border-dotted border-muted-foreground/30'>
                              Wallet Age at First Buy
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>How old the wallet was when it first bought a token in our database. Under 24h = fresh wallet.</TooltipContent>
                        </Tooltip>
                        <span className={p!.wallet_age_at_first_buy_hours! < 1 ? 'text-red-400 font-medium' :
                          p!.wallet_age_at_first_buy_hours! < 24 ? 'text-orange-400' :
                          p!.wallet_age_at_first_buy_hours! < 168 ? 'text-yellow-400' : ''}>
                          {p!.wallet_age_at_first_buy_hours! < 1 ? `${(p!.wallet_age_at_first_buy_hours! * 60).toFixed(0)} minutes` :
                           p!.wallet_age_at_first_buy_hours! < 24 ? `${p!.wallet_age_at_first_buy_hours!.toFixed(1)} hours` :
                           `${(p!.wallet_age_at_first_buy_hours! / 24).toFixed(0)} days`}
                        </span>
                      </div>
                    )}
                    {p?.funded_by && (
                      <div className='flex justify-between'>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className='text-muted-foreground cursor-help border-b border-dotted border-muted-foreground/30'>
                              Funded By
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>Where this wallet received its initial SOL from.</TooltipContent>
                        </Tooltip>
                        <span className='font-mono text-[10px] break-all'>
                          {p.funded_by.funderName || p.funded_by.funder}
                          {p.funded_by.funderType && ` (${p.funded_by.funderType})`}
                        </span>
                      </div>
                    )}
                    {p?.is_deployer && (
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Tokens Deployed</span>
                        <span className='text-purple-400'>{p.tokens_deployed}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Funding Tree (lazy-loaded, costs credits) */}
                {walletAddress && <CompactFundingTree walletAddress={walletAddress} />}

                {/* Performance */}
                {perf && (
                  <div className='rounded-lg border p-3'>
                    <div className='text-xs font-medium mb-2'>Early Buyer Performance</div>
                    <div className='grid grid-cols-3 gap-2 mb-3'>
                      <div className='rounded bg-muted/50 p-2 text-center'>
                        <div className='text-lg font-bold'>{perf.tokens_bought_early}</div>
                        <div className='text-muted-foreground text-[9px]'>Tokens Bought Early</div>
                      </div>
                      <div className='rounded bg-muted/50 p-2 text-center'>
                        <div className={cn('text-lg font-bold', perf.win_rate !== null && perf.win_rate >= 50 ? 'text-green-400' : 'text-red-400')}>
                          {perf.win_rate !== null ? `${perf.win_rate}%` : '—'}
                        </div>
                        <div className='text-muted-foreground text-[9px]'>Win Rate (Real PnL)</div>
                      </div>
                      <div className='rounded bg-muted/50 p-2 text-center'>
                        <div className={cn('text-lg font-bold', perf.total_realized_pnl > 0 ? 'text-green-400' : perf.total_realized_pnl < 0 ? 'text-red-400' : '')}>
                          {formatUsd(perf.total_realized_pnl)}
                        </div>
                        <div className='text-muted-foreground text-[9px]'>Realized PnL</div>
                      </div>
                    </div>
                    <div className='space-y-1.5 text-[11px]'>
                      <div className='flex justify-between'>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className='text-muted-foreground cursor-help border-b border-dotted border-muted-foreground/30'>
                              Avg Entry Timing
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>Average seconds after token creation when this wallet bought. Under 30s consistently = likely a bot.</TooltipContent>
                        </Tooltip>
                        <span className={perf.avg_entry_seconds !== null && perf.avg_entry_seconds < 30 ? 'text-sky-400' : ''}>
                          {perf.avg_entry_seconds !== null ? formatTime(perf.avg_entry_seconds) : '—'}
                          {perf.pct_entries_under_60s !== null && ` (${perf.pct_entries_under_60s.toFixed(0)}% under 60s)`}
                        </span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Total Bought / Sold</span>
                        <span>${perf.total_bought_usd.toLocaleString(undefined, {maximumFractionDigits: 0})} / ${perf.total_sold_usd.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>Record</span>
                        <span>
                          <span className='text-green-400'>{perf.wins}W</span>
                          {' / '}
                          <span className='text-red-400'>{perf.losses}L</span>
                          {perf.still_holding > 0 && <span className='text-muted-foreground'> / {perf.still_holding} holding</span>}
                        </span>
                      </div>
                      {perf.best_trade && (
                        <div className='flex justify-between'>
                          <span className='text-muted-foreground'>Best Trade</span>
                          <span className='text-green-400'>
                            {formatUsd(perf.best_trade.realized_pnl)} on{' '}
                            {perf.best_trade.token_id ? (
                              <button className='underline decoration-dotted hover:text-green-300 transition-colors'
                                onClick={() => openTIP({ id: perf.best_trade!.token_id })}
                              >{perf.best_trade.token_name}</button>
                            ) : perf.best_trade.token_name}
                          </span>
                        </div>
                      )}
                      {perf.worst_trade && perf.worst_trade.realized_pnl < 0 && (
                        <div className='flex justify-between'>
                          <span className='text-muted-foreground'>Worst Trade</span>
                          <span className='text-red-400'>
                            {formatUsd(perf.worst_trade.realized_pnl)} on{' '}
                            {perf.worst_trade.token_id ? (
                              <button className='underline decoration-dotted hover:text-red-300 transition-colors'
                                onClick={() => openTIP({ id: perf.worst_trade!.token_id })}
                              >{perf.worst_trade.token_name}</button>
                            ) : perf.worst_trade.token_name}
                          </span>
                        </div>
                      )}
                      <div className='flex justify-between text-muted-foreground text-[9px]'>
                        <span>Real PnL data from {perf.real_pnl_count} positions</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Trade History */}
                {data.trades.length > 0 && (
                  <div className='rounded-lg border p-3'>
                    <div className='text-xs font-medium mb-2'>Token Trades ({data.trades.length})</div>
                    <div className='space-y-1'>
                      {data.trades.map((trade) => (
                        <div key={trade.token_id}
                          className={cn(
                            'flex items-center justify-between rounded px-2 py-1.5 hover:bg-blue-500/10 transition-colors cursor-pointer',
                            trade.verdict === 'verified-win' ? 'border-l-2 border-green-500/50' :
                            trade.verdict === 'verified-loss' ? 'border-l-2 border-red-500/50' :
                            'border-l-2 border-transparent'
                          )}
                          onClick={() => openTIP({ id: trade.token_id })}
                        >
                          <div className='min-w-0 flex-1'>
                            <div className='flex items-center gap-2'>
                              <span className='text-xs font-medium'>{trade.token_symbol || trade.token_name || '—'}</span>
                              {trade.entry_seconds !== undefined && (
                                <span className={cn(
                                  'text-[9px]',
                                  trade.entry_seconds < 30 ? 'text-sky-400' :
                                  trade.entry_seconds < 60 ? 'text-yellow-400' : 'text-muted-foreground'
                                )}>
                                  {formatTime(trade.entry_seconds)}
                                </span>
                              )}
                              {trade.verdict === 'verified-win' && (
                                <span className={`text-[9px] font-medium ${
                                  trade.win_multiplier && parseInt(trade.win_multiplier.replace('win:', '')) >= 25
                                    ? 'text-yellow-300' : 'text-green-400'
                                }`}>
                                  TOKEN WIN{trade.win_multiplier ? ` ${trade.win_multiplier.replace('win:', '').toUpperCase()}` : ''}
                                </span>
                              )}
                              {trade.verdict === 'verified-loss' && (
                                <span className={`text-[9px] font-medium ${
                                  trade.loss_tier === 'loss:rug' ? 'text-red-500' :
                                  trade.loss_tier === 'loss:dead' ? 'text-red-500' :
                                  trade.loss_tier === 'loss:90' ? 'text-red-400' :
                                  trade.loss_tier === 'loss:70' ? 'text-orange-400' :
                                  trade.loss_tier === 'loss:stale' ? 'text-muted-foreground' : 'text-red-400'
                                }`}>
                                  {trade.loss_tier === 'loss:rug' ? 'RUG PULL' :
                                   trade.loss_tier === 'loss:90' ? 'TOKEN LOSS 90%+' :
                                   trade.loss_tier === 'loss:70' ? 'TOKEN LOSS 70%+' :
                                   trade.loss_tier === 'loss:dead' ? 'TOKEN DEAD' :
                                   trade.loss_tier === 'loss:stale' ? 'TOKEN STALE' : 'TOKEN LOSS'}
                                </span>
                              )}
                            </div>
                            <div className='text-[9px] text-muted-foreground'>
                              <TokenAddressCell address={trade.token_address} compact showTwitter={false} />
                            </div>
                          </div>
                          <div className='text-right shrink-0'>
                            {trade.pnl_source === 'real' && trade.realized_pnl !== null ? (
                              <span className={cn('text-xs font-medium',
                                trade.realized_pnl > 0 ? 'text-green-400' : trade.realized_pnl < 0 ? 'text-red-400' : ''
                              )}>
                                {formatUsd(trade.realized_pnl)}
                              </span>
                            ) : (
                              <span className='text-[9px] text-muted-foreground'>No PnL data</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {!data && !loading && (
              <div className='py-8 text-center text-muted-foreground text-sm'>
                No intelligence data found for this wallet.
              </div>
            )}
          </div>
        </div>
    </TooltipProvider>
  );
}
