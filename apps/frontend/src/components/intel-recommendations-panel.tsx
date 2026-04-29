'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import {
  Check, X, Undo2, Shield, ShieldAlert, Eye, Tag, RefreshCw,
  ChevronDown, ChevronRight, Bell,
} from 'lucide-react';
import { toast } from 'sonner';

interface Recommendation {
  id: number;
  report_id: number;
  action_type: string;
  target_type: string;
  target_address: string;
  payload: string;
  reason: string;
  confidence: string;
  expected_bot_effect: string;
  status: string;
  created_at: string;
  approved_at: string | null;
  reverted_at: string | null;
  rejected_at: string | null;
}

const ACTION_LABELS: Record<string, { label: string; icon: typeof Shield; color: string }> = {
  add_bot_allowlist_wallet:    { label: 'Add to Bot Allowlist',        icon: Shield,      color: 'text-green-400' },
  remove_bot_allowlist_wallet: { label: 'Remove from Bot Allowlist',   icon: Shield,      color: 'text-yellow-400' },
  add_bot_denylist_wallet:     { label: 'Add to Bot Denylist',         icon: ShieldAlert,  color: 'text-red-400' },
  remove_bot_denylist_wallet:  { label: 'Remove from Bot Denylist',    icon: ShieldAlert,  color: 'text-yellow-400' },
  add_watch_wallet:            { label: 'Add to Watchlist',            icon: Eye,          color: 'text-blue-400' },
  remove_watch_wallet:         { label: 'Remove from Watchlist',       icon: Eye,          color: 'text-yellow-400' },
  add_intel_tag:               { label: 'Add Intel Tag',               icon: Tag,          color: 'text-purple-400' },
  remove_intel_tag:            { label: 'Remove Intel Tag',            icon: Tag,          color: 'text-yellow-400' },
  add_nametag:                 { label: 'Set Nametag',                 icon: Tag,          color: 'text-cyan-400' },
  queue_wallet_pnl_refresh:    { label: 'Queue PnL Refresh',           icon: RefreshCw,    color: 'text-muted-foreground' },
  queue_wallet_funding_refresh:{ label: 'Queue Funding Refresh',       icon: RefreshCw,    color: 'text-muted-foreground' },
};

const STATUS_STYLES: Record<string, string> = {
  proposed:       'border-yellow-500/30 bg-yellow-500/5',
  active_for_bot: 'border-green-500/30 bg-green-500/5',
  rejected:       'border-muted bg-muted/20 opacity-60',
  reverted:       'border-orange-500/30 bg-orange-500/5 opacity-70',
  failed:         'border-red-500/30 bg-red-500/5 opacity-60',
};

function RecommendationCard({
  rec, onAction,
}: {
  rec: Recommendation;
  onAction: (id: number, action: 'approve' | 'reject' | 'revert') => void;
}) {
  const { openWIR } = useWalletIntelligence();
  const meta = ACTION_LABELS[rec.action_type] || { label: rec.action_type, icon: Tag, color: 'text-muted-foreground' };
  const Icon = meta.icon;
  const [expanded, setExpanded] = useState(rec.status === 'proposed');

  const confidenceColor = rec.confidence === 'high' ? 'text-green-400' :
    rec.confidence === 'medium' ? 'text-yellow-400' : 'text-red-400';

  return (
    <div className={cn('rounded-lg border p-3 space-y-2 transition-all', STATUS_STYLES[rec.status] || 'border-muted')}>
      {/* Header */}
      <div className='flex items-center gap-2'>
        <button onClick={() => setExpanded(!expanded)} className='shrink-0'>
          {expanded ? <ChevronDown className='h-3 w-3 text-muted-foreground' /> : <ChevronRight className='h-3 w-3 text-muted-foreground' />}
        </button>
        <Icon className={cn('h-4 w-4 shrink-0', meta.color)} />
        <span className='text-xs font-medium flex-1'>{meta.label}</span>
        <span className={cn('text-[10px] font-mono', confidenceColor)}>{rec.confidence}</span>
        <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium',
          rec.status === 'proposed' ? 'bg-yellow-500/20 text-yellow-400' :
          rec.status === 'active_for_bot' ? 'bg-green-500/20 text-green-400' :
          rec.status === 'rejected' ? 'bg-muted text-muted-foreground' :
          rec.status === 'reverted' ? 'bg-orange-500/20 text-orange-400' :
          'bg-red-500/20 text-red-400'
        )}>
          {rec.status === 'active_for_bot' ? 'active' : rec.status}
        </span>
      </div>

      {/* Target address — clickable */}
      <button
        onClick={() => openWIR(rec.target_address)}
        className='text-[11px] font-mono text-primary hover:text-primary/80 hover:underline break-all text-left w-full'
        title='Open Wallet Intelligence Report'
      >
        {rec.target_address}
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className='space-y-1.5 pt-1'>
          <div className='text-[11px] text-muted-foreground'>
            <span className='font-medium text-foreground/70'>Reason:</span> {rec.reason}
          </div>
          {rec.expected_bot_effect && (
            <div className='text-[11px] text-muted-foreground'>
              <span className='font-medium text-foreground/70'>Bot effect:</span> {rec.expected_bot_effect}
            </div>
          )}
          <div className='text-[10px] text-muted-foreground'>
            Report #{rec.report_id} · {rec.created_at}
            {rec.approved_at && ` · Approved: ${rec.approved_at}`}
            {rec.reverted_at && ` · Reverted: ${rec.reverted_at}`}
          </div>

          {/* Action buttons */}
          <div className='flex gap-2 pt-1'>
            {rec.status === 'proposed' && (
              <>
                <button
                  onClick={() => onAction(rec.id, 'approve')}
                  className='flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors'
                >
                  <Check className='h-3 w-3' /> Approve
                </button>
                <button
                  onClick={() => onAction(rec.id, 'reject')}
                  className='flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors'
                >
                  <X className='h-3 w-3' /> Reject
                </button>
              </>
            )}
            {rec.status === 'active_for_bot' && (
              <button
                onClick={() => onAction(rec.id, 'revert')}
                className='flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-orange-500/10 text-orange-400 hover:bg-orange-500/20 transition-colors'
              >
                <Undo2 className='h-3 w-3' /> Revert
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


export function IntelRecommendationsPanel() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [counts, setCounts] = useState({ proposed: 0, active: 0, total: 0 });
  const [filter, setFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadRecommendations = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filter) params.set('status', filter);
      params.set('limit', '50');
      const res = await fetch(`${API_BASE_URL}/api/intel/recommendations?${params}`);
      if (res.ok) {
        const data = await res.json();
        setRecommendations(data.recommendations || []);
        setCounts(data.counts || { proposed: 0, active: 0, total: 0 });
      }
    } catch { /* silent */ }
  }, [filter]);

  useEffect(() => { loadRecommendations(); }, [loadRecommendations]);

  // Poll for new recommendations
  useEffect(() => {
    const interval = setInterval(loadRecommendations, 15000);
    return () => clearInterval(interval);
  }, [loadRecommendations]);

  const handleAction = async (id: number, action: 'approve' | 'reject' | 'revert') => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/intel/recommendations/${id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: action === 'reject' ? JSON.stringify({ reason: '' }) : undefined,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          toast.success(data.message);
        } else {
          toast.error(data.message);
        }
        loadRecommendations();
      }
    } catch {
      toast.error(`Failed to ${action} recommendation`);
    } finally {
      setLoading(false);
    }
  };

  const proposed = recommendations.filter(r => r.status === 'proposed');
  const applied = recommendations.filter(r => r.status !== 'proposed');

  return (
    <div className='space-y-3'>
      {/* Header */}
      <div className='flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <Bell className='h-4 w-4 text-muted-foreground' />
          <h3 className='text-xs font-semibold'>Intel Recommendations</h3>
          {counts.proposed > 0 && (
            <span className='text-[10px] px-1.5 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 font-medium'>
              {counts.proposed} pending
            </span>
          )}
        </div>
      </div>

      {/* Filter tabs */}
      <div className='flex gap-1'>
        {[
          { key: null, label: 'All' },
          { key: 'proposed', label: 'Pending' },
          { key: 'active_for_bot', label: 'Active' },
          { key: 'rejected', label: 'Rejected' },
          { key: 'reverted', label: 'Reverted' },
        ].map((f) => (
          <button
            key={f.key || 'all'}
            onClick={() => setFilter(f.key)}
            className={cn(
              'text-[10px] px-2 py-1 rounded transition-colors',
              filter === f.key
                ? 'bg-primary/10 text-primary font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Proposed section */}
      {proposed.length > 0 && (
        <div className='space-y-2'>
          <h4 className='text-[10px] font-semibold text-yellow-400 uppercase tracking-wide'>
            Awaiting Review ({proposed.length})
          </h4>
          {proposed.map((rec) => (
            <RecommendationCard key={rec.id} rec={rec} onAction={handleAction} />
          ))}
        </div>
      )}

      {/* Applied/other section */}
      {applied.length > 0 && (
        <div className='space-y-2'>
          <h4 className='text-[10px] font-semibold text-muted-foreground uppercase tracking-wide'>
            History ({applied.length})
          </h4>
          {applied.map((rec) => (
            <RecommendationCard key={rec.id} rec={rec} onAction={handleAction} />
          ))}
        </div>
      )}

      {recommendations.length === 0 && (
        <p className='text-[11px] text-muted-foreground py-4 text-center'>
          No recommendations yet. Run an Intel report to generate proposals.
        </p>
      )}
    </div>
  );
}
