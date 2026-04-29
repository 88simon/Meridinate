'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  traceFundingChains,
  FundingTrace,
  FundingTraceResponse
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { X, Copy, ExternalLink, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

// ============================================================================
// Types
// ============================================================================

export interface ClusterData {
  funder: string;
  funder_name: string | null;
  funder_type: string | null;
  wallets: string[];
}

interface FundingTreePanelProps {
  open: boolean;
  onClose: () => void;
  cluster: ClusterData | null;
  identities?: Record<
    string,
    { name: string; type: string | null; category: string | null; tags: string[] }
  >;
}

interface TreeNode {
  address: string;
  name: string | null;
  type: string | null;
  /** Date this wallet was funded (ISO string from Helius) */
  fundedDate: string | null;
  /** Unix timestamp of funding */
  fundedTimestamp: number | null;
  /** SOL amount of funding transfer */
  fundedAmount: number | null;
  /** Transaction signature for the funding transfer */
  txSignature: string | null;
  children: TreeNode[];
  isLeaf: boolean;
}

// ============================================================================
// Tree builder — merges per-wallet traces into a unified tree
// ============================================================================

function buildFundingTree(
  traces: Record<string, FundingTrace>,
  clusterWallets: string[]
): TreeNode[] {
  const nodes = new Map<string, TreeNode>();
  const hasParent = new Set<string>();
  const leafSet = new Set(clusterWallets);

  const getOrCreate = (addr: string): TreeNode => {
    let node = nodes.get(addr);
    if (!node) {
      node = {
        address: addr,
        name: null,
        type: null,
        fundedDate: null,
        fundedTimestamp: null,
        fundedAmount: null,
        txSignature: null,
        children: [],
        isLeaf: false
      };
      nodes.set(addr, node);
    }
    return node;
  };

  for (const trace of Object.values(traces)) {
    const leaf = getOrCreate(trace.wallet_address);
    if (leafSet.has(trace.wallet_address)) leaf.isLeaf = true;

    const termNode = getOrCreate(trace.terminal_wallet);
    if (trace.terminal_name && !termNode.name)
      termNode.name = trace.terminal_name;

    for (const hop of trace.chain) {
      const child = getOrCreate(hop.wallet);
      // The hop says "wallet was funded by funder" — date/amount describe when/how much
      if (hop.date && !child.fundedDate) child.fundedDate = hop.date;
      if (hop.timestamp && !child.fundedTimestamp) child.fundedTimestamp = hop.timestamp;
      if (hop.amount != null && child.fundedAmount == null) child.fundedAmount = hop.amount;
      if (hop.tx_signature && !child.txSignature) child.txSignature = hop.tx_signature;

      if (hop.funder) {
        const parent = getOrCreate(hop.funder);
        if (hop.funder_name && !parent.name) parent.name = hop.funder_name;
        if (hop.funder_type && !parent.type) parent.type = hop.funder_type;

        if (!parent.children.some((c) => c.address === child.address)) {
          parent.children.push(child);
        }
        hasParent.add(child.address);
      }
    }
  }

  const roots: TreeNode[] = [];
  nodes.forEach((node) => {
    if (!hasParent.has(node.address) && (node.children.length > 0 || node.isLeaf)) {
      roots.push(node);
    }
  });

  return roots;
}

// ============================================================================
// Fallback tree from 1-hop cluster data (no trace needed)
// ============================================================================

function buildFallbackTree(cluster: ClusterData): TreeNode[] {
  const root: TreeNode = {
    address: cluster.funder,
    name: cluster.funder_name,
    type: cluster.funder_type,
    fundedDate: null,
    fundedTimestamp: null,
    fundedAmount: null,
    txSignature: null,
    children: cluster.wallets.map((addr) => ({
      address: addr,
      name: null,
      type: null,
      fundedDate: null,
      fundedTimestamp: null,
      fundedAmount: null,
      txSignature: null,
      children: [],
      isLeaf: true
    })),
    isLeaf: false
  };
  return [root];
}

// ============================================================================
// Date formatting
// ============================================================================

function formatFundingDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  } catch {
    return dateStr;
  }
}

// ============================================================================
// Recursive tree node renderer
// ============================================================================

function TreeNodeRow({
  node,
  isLast,
  depth,
  identities
}: {
  node: TreeNode;
  isLast: boolean;
  depth: number;
  identities?: FundingTreePanelProps['identities'];
}) {
  const identity = identities?.[node.address];
  const displayName = node.name || identity?.name || null;
  const displayType = node.type || identity?.type || null;

  const copyAddr = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(node.address);
    toast.success('Address copied');
  };

  return (
    <div className='relative'>
      {/* Connector lines */}
      {depth > 0 && (
        <div
          className='pointer-events-none absolute top-0 left-0 h-full'
          style={{ width: depth * 24 }}
        >
          {/* Vertical line from parent */}
          <div
            className='border-muted-foreground/30 absolute border-l'
            style={{
              left: (depth - 1) * 24 + 8,
              top: 0,
              height: isLast ? 16 : '100%'
            }}
          />
          {/* Horizontal branch */}
          <div
            className='border-muted-foreground/30 absolute border-t'
            style={{
              left: (depth - 1) * 24 + 8,
              top: 16,
              width: 12
            }}
          />
        </div>
      )}

      {/* Node content */}
      <div
        className='group hover:bg-muted/40 flex items-center gap-2 rounded py-1.5 pr-2 transition-colors'
        style={{ paddingLeft: depth * 24 + (depth > 0 ? 24 : 4) }}
      >
        {/* Dot */}
        <div
          className={`h-2 w-2 shrink-0 rounded-full ${
            node.isLeaf
              ? 'bg-amber-400'
              : displayType === 'exchange'
                ? 'bg-blue-400'
                : displayType === 'protocol'
                  ? 'bg-purple-400'
                  : 'bg-muted-foreground'
          }`}
        />

        {/* Label area */}
        <div className='flex min-w-0 flex-1 flex-col'>
          <div className='flex items-center gap-1.5'>
            {displayName && (
              <span className='text-foreground text-sm font-medium'>
                {displayName}
              </span>
            )}
            {displayType && (
              <span
                className={`rounded px-1 py-0.5 text-[9px] font-medium uppercase ${
                  displayType === 'exchange'
                    ? 'bg-blue-500/20 text-blue-400'
                    : displayType === 'protocol'
                      ? 'bg-purple-500/20 text-purple-400'
                      : 'bg-muted text-muted-foreground'
                }`}
              >
                {displayType}
              </span>
            )}
            {node.isLeaf && (
              <span className='rounded bg-amber-500/20 px-1 py-0.5 text-[9px] font-medium text-amber-400'>
                EARLY BIDDER
              </span>
            )}
            {!node.isLeaf && node.children.length > 0 && !displayType && (
              <span className='bg-muted text-muted-foreground rounded px-1 py-0.5 text-[9px]'>
                intermediary
              </span>
            )}
          </div>
          <code className='text-muted-foreground select-all font-mono text-[11px]'>
            {node.address}
          </code>
          {/* Funding date and amount */}
          {(node.fundedDate || node.fundedAmount != null) && (
            <span className='text-muted-foreground text-[10px]'>
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

        {/* Actions (visible on hover) */}
        <div className='flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100'>
          <button
            onClick={copyAddr}
            className='text-muted-foreground hover:text-foreground rounded p-0.5'
            title='Copy address'
          >
            <Copy className='h-3 w-3' />
          </button>
          <a
            href={`https://gmgn.ai/sol/address/${node.address}`}
            target='_blank'
            rel='noopener noreferrer'
            className='text-muted-foreground hover:text-foreground rounded p-0.5'
            title='View on GMGN'
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className='h-3 w-3' />
          </a>
        </div>
      </div>

      {/* Children */}
      {node.children.length > 0 && (
        <div className='relative'>
          {node.children.map((child, i) => (
            <TreeNodeRow
              key={child.address}
              node={child}
              isLast={i === node.children.length - 1}
              depth={depth + 1}
              identities={identities}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Main Panel
// ============================================================================

export function FundingTreePanel({
  open,
  onClose,
  cluster,
  identities
}: FundingTreePanelProps) {
  const [loading, setLoading] = useState(false);
  const [traceData, setTraceData] = useState<FundingTraceResponse | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);

  const runTrace = useCallback(async () => {
    if (!cluster) return;
    setLoading(true);
    try {
      const result = await traceFundingChains(cluster.wallets, 3, true);
      setTraceData(result);
      setTree(buildFundingTree(result.traces, cluster.wallets));
    } catch {
      toast.error('Funding trace failed');
      // Fall back to 1-hop view
      if (cluster) setTree(buildFallbackTree(cluster));
    } finally {
      setLoading(false);
    }
  }, [cluster]);

  useEffect(() => {
    if (open && cluster) {
      setTree(buildFallbackTree(cluster));
      setTraceData(null);
      runTrace();
    }
    if (!open) {
      setTraceData(null);
      setTree([]);
    }
  }, [open, cluster, runTrace]);

  if (!open || !cluster) return null;

  return (
    <div
      className='fixed inset-0 z-50 flex justify-end bg-black/40'
      onClick={onClose}
    >
      <div
        className='bg-background flex h-full w-full max-w-xl flex-col border-l shadow-xl animate-in slide-in-from-right duration-200'
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-4 py-3'>
          <div>
            <h2 className='text-base font-semibold'>Funding Tree</h2>
            <p className='text-muted-foreground text-xs'>
              {cluster.wallets.length} wallets
              {cluster.funder_name
                ? ` funded by ${cluster.funder_name}`
                : ''}
              {traceData
                ? ` — ${traceData.total_credits} credits used`
                : ''}
            </p>
          </div>
          <div className='flex items-center gap-2'>
            {loading && (
              <Loader2 className='text-muted-foreground h-4 w-4 animate-spin' />
            )}
            <Button variant='ghost' size='sm' onClick={onClose}>
              <X className='h-4 w-4' />
            </Button>
          </div>
        </div>

        {/* Tree content */}
        <div className='flex-1 overflow-y-auto px-4 py-3'>
          {tree.length > 0 ? (
            <div className='space-y-0'>
              {tree.map((root, i) => (
                <TreeNodeRow
                  key={root.address}
                  node={root}
                  isLast={i === tree.length - 1}
                  depth={0}
                  identities={identities}
                />
              ))}
            </div>
          ) : loading ? (
            <div className='flex items-center justify-center py-16'>
              <Loader2 className='text-muted-foreground h-6 w-6 animate-spin' />
            </div>
          ) : (
            <p className='text-muted-foreground py-8 text-center text-sm'>
              No funding data available
            </p>
          )}

          {/* Deep clusters info */}
          {traceData && traceData.deep_clusters.length > 0 && (
            <div className='mt-4 rounded border p-3'>
              <h3 className='mb-1.5 text-xs font-medium'>
                Deep Clusters Found
              </h3>
              <div className='space-y-1'>
                {traceData.deep_clusters.map((dc) => (
                  <div
                    key={dc.terminal_wallet}
                    className='text-muted-foreground flex items-center justify-between text-xs'
                  >
                    <span>
                      {dc.terminal_name ||
                        `${dc.terminal_wallet.slice(0, 8)}...`}
                    </span>
                    <span className='rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-400'>
                      {dc.count} wallets converge
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className='flex items-center justify-between border-t px-4 py-2'>
          <p className='text-muted-foreground text-[10px]'>
            {traceData
              ? `Traced ${traceData.wallets_traced} wallets, ${traceData.total_credits} credits`
              : 'Showing 1-hop data'}
          </p>
          <Button
            variant='outline'
            size='sm'
            className='h-6 text-[10px]'
            onClick={runTrace}
            disabled={loading}
          >
            {loading ? 'Tracing...' : 'Re-trace'}
          </Button>
        </div>
      </div>
    </div>
  );
}
