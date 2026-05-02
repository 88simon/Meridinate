'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { useWalletNametag } from '@/contexts/wallet-nametags-context';
import {
  Undo2, Shield, ShieldAlert, Eye, Tag, RefreshCw,
  ChevronDown, ChevronRight, Bell, Radio, Search,
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
  monitor_wallet:              { label: 'Shadow Wallet (track live)',  icon: Radio,        color: 'text-emerald-400' },
  stop_monitor_wallet:         { label: 'Stop Shadowing',              icon: Radio,        color: 'text-yellow-400' },
  probe_wallet:                { label: 'Queue Bot Probe',             icon: Search,       color: 'text-purple-400' },
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
  overridden:     'border-purple-500/30 bg-purple-500/5 opacity-70',
  reverted:       'border-orange-500/30 bg-orange-500/5 opacity-70',
  failed:         'border-red-500/30 bg-red-500/5 opacity-60',
};

// TOXIC dropdown — three explicit deny types. Maps to backend operator_category +
// payload.deny_type for the executor. Kept tight on purpose; rare action.
const TOXIC_TYPES: { key: string; label: string; deny_type: string; operator_category: string }[] = [
  { key: 'deployer_linked', label: 'Deployer- / team-linked', deny_type: 'deployer_linked',     operator_category: 'deployer_or_team_link' },
  { key: 'sybil_cluster',   label: 'Sybil / cluster',         deny_type: 'sybil',                operator_category: 'missed_cluster_or_sybil' },
  { key: 'other_toxic',     label: 'Other adversarial flow',  deny_type: 'toxic_flow',           operator_category: 'other' },
];

function RecommendationCard({
  rec, onTrack, onToxic, onSkip, onRevert, isLatestRun,
}: {
  rec: Recommendation;
  onTrack: (rec: Recommendation) => Promise<void>;
  onToxic: (rec: Recommendation, denyType: string, operatorCategory: string, note: string) => Promise<void>;
  onSkip: (rec: Recommendation) => Promise<void>;
  onRevert: (rec: Recommendation) => Promise<void>;
  isLatestRun: boolean;
}) {
  const { openWIR } = useWalletIntelligence();
  const nametag = useWalletNametag(rec.target_type === 'wallet' ? rec.target_address : null);
  const meta = ACTION_LABELS[rec.action_type] || { label: rec.action_type, icon: Tag, color: 'text-muted-foreground' };
  const Icon = meta.icon;
  const [expanded, setExpanded] = useState(rec.status === 'proposed');
  const [toxicOpen, setToxicOpen] = useState(false);
  const [toxicType, setToxicType] = useState(TOXIC_TYPES[0].key);
  const [toxicNote, setToxicNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleTrack = async () => {
    setSubmitting(true);
    try { await onTrack(rec); } finally { setSubmitting(false); }
  };

  const handleSkip = async () => {
    setSubmitting(true);
    try { await onSkip(rec); } finally { setSubmitting(false); }
  };

  const submitToxic = async () => {
    const t = TOXIC_TYPES.find((x) => x.key === toxicType) || TOXIC_TYPES[0];
    if (t.key === 'other_toxic' && !toxicNote.trim()) return;
    setSubmitting(true);
    try {
      await onToxic(rec, t.deny_type, t.operator_category, toxicNote.trim());
      setToxicOpen(false);
      setToxicNote('');
    } finally {
      setSubmitting(false);
    }
  };

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
        {isLatestRun && (
          <span className='text-[9px] px-1 py-0.5 rounded bg-blue-500/20 text-blue-300 font-semibold uppercase tracking-wide'>
            new
          </span>
        )}
        <span className={cn('text-[10px] font-mono', confidenceColor)}>{rec.confidence}</span>
        <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-medium',
          rec.status === 'proposed' ? 'bg-yellow-500/20 text-yellow-400' :
          rec.status === 'active_for_bot' ? 'bg-green-500/20 text-green-400' :
          rec.status === 'rejected' ? 'bg-muted text-muted-foreground' :
          rec.status === 'overridden' ? 'bg-purple-500/20 text-purple-300' :
          rec.status === 'reverted' ? 'bg-orange-500/20 text-orange-400' :
          'bg-red-500/20 text-red-400'
        )}>
          {rec.status === 'active_for_bot' ? 'active' : rec.status}
        </span>
      </div>

      {/* Target address — clickable, shows nametag inline if set */}
      <button
        onClick={() => openWIR(rec.target_address)}
        className='text-left w-full hover:opacity-80 transition-opacity'
        title='Open Wallet Intelligence Report'
      >
        {nametag && (
          <div className='text-[11px] font-medium text-cyan-400 truncate'>{nametag}</div>
        )}
        <div className={cn(
          'text-[11px] font-mono break-all',
          nametag ? 'text-muted-foreground' : 'text-primary hover:underline'
        )}>
          {rec.target_address}
        </div>
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

          {/* Triage actions — collapsed to Track / Toxic / Skip. Track is the default
              for ~90% of recs (zero-cost shadow accumulation). Toxic is rare and requires
              an explicit type. Skip is silent (no learning signal). Allowlist promotion
              and Bot Probe live on the WIR, not here — those are decisions for AFTER the
              wallet has accumulated enough shadow data. */}
          <div className='flex gap-2 pt-1 flex-wrap'>
            {rec.status === 'proposed' && (
              <>
                <button
                  onClick={handleTrack}
                  disabled={submitting}
                  title='Add wallet to Wallet Shadow for live trade tracking'
                  className='flex items-center gap-1 text-[11px] px-3 py-1 rounded bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-40 transition-colors font-medium'
                >
                  <Radio className='h-3 w-3' /> Track
                </button>
                <button
                  onClick={() => setToxicOpen((v) => !v)}
                  disabled={submitting}
                  title='Mark wallet as toxic / adversarial — adds to denylist'
                  className={cn(
                    'flex items-center gap-1 text-[11px] px-2 py-1 rounded transition-colors',
                    toxicOpen
                      ? 'bg-red-500/30 text-red-300'
                      : 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                  )}
                >
                  <ShieldAlert className='h-3 w-3' /> Toxic
                </button>
                <button
                  onClick={handleSkip}
                  disabled={submitting}
                  title='Reject — no signal recorded, no system change'
                  className='text-[11px] px-2 py-1 text-muted-foreground hover:text-foreground transition-colors'
                >
                  Skip
                </button>
              </>
            )}
            {rec.status === 'active_for_bot' && (
              <button
                onClick={() => onRevert(rec)}
                className='flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-orange-500/10 text-orange-400 hover:bg-orange-500/20 transition-colors'
              >
                <Undo2 className='h-3 w-3' /> Revert
              </button>
            )}
          </div>

          {/* Toxic confirmation — small, focused. Three deny types. Note required only for "Other". */}
          {toxicOpen && rec.status === 'proposed' && (
            <div className='mt-2 space-y-2 rounded border border-red-500/30 bg-red-500/5 p-2'>
              <div className='text-[10px] font-semibold text-red-300 uppercase tracking-wide'>
                Mark as toxic
              </div>
              <div className='space-y-1'>
                <label className='text-[10px] text-muted-foreground'>Type</label>
                <select
                  value={toxicType}
                  onChange={(e) => setToxicType(e.target.value)}
                  className='w-full text-[11px] bg-background border border-border rounded px-2 py-1'
                >
                  {TOXIC_TYPES.map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </select>
              </div>
              {toxicType === 'other_toxic' && (
                <div className='space-y-1'>
                  <label className='text-[10px] text-muted-foreground'>One-line reason (required for &quot;Other&quot;)</label>
                  <input
                    type='text'
                    value={toxicNote}
                    onChange={(e) => setToxicNote(e.target.value)}
                    maxLength={200}
                    placeholder='What makes this adversarial?'
                    className='w-full text-[11px] bg-background border border-border rounded px-2 py-1'
                  />
                </div>
              )}
              <div className='flex gap-2'>
                <button
                  onClick={submitToxic}
                  disabled={submitting || (toxicType === 'other_toxic' && !toxicNote.trim())}
                  className='flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-red-500/20 text-red-300 hover:bg-red-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors'
                >
                  <ShieldAlert className='h-3 w-3' /> {submitting ? 'Applying…' : 'Confirm toxic'}
                </button>
                <button
                  onClick={() => { setToxicOpen(false); setToxicNote(''); }}
                  className='text-[11px] px-2 py-1 rounded text-muted-foreground hover:text-foreground transition-colors'
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


export function IntelRecommendationsPanel() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [counts, setCounts] = useState({ proposed: 0, active: 0, total: 0 });
  const [filter, setFilter] = useState<string | null>(null);

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

  // Poll for new recommendations. Skip while tab hidden — recs accumulate
  // server-side; we only refresh visuals on user-visible polls.
  useEffect(() => {
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      loadRecommendations();
    }, 15000);
    return () => clearInterval(interval);
  }, [loadRecommendations]);

  // Generic dispatcher to the existing endpoints. Track/Toxic/Skip wrap these.
  const callApprove = async (id: number) =>
    fetch(`${API_BASE_URL}/api/intel/recommendations/${id}/approve`, { method: 'POST' });
  const callReject = async (id: number) =>
    fetch(`${API_BASE_URL}/api/intel/recommendations/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: '' }),
    });
  const callReclassify = async (id: number, body: object) =>
    fetch(`${API_BASE_URL}/api/intel/recommendations/${id}/reclassify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

  // TRACK = "shadow this wallet, regardless of what Intel proposed."
  // - If Intel already proposed monitor_wallet: approve (Intel was right; no learning needed).
  // - Otherwise: reclassify to monitor_wallet so the wallet gets shadowed AND the Override
  //   Analyst extracts a rule for the next Intel run.
  const handleTrack = async (rec: Recommendation) => {
    try {
      let res: Response;
      let toastMsg = `Tracking ${rec.target_address.slice(0, 8)}…`;
      if (rec.action_type === 'monitor_wallet') {
        res = await callApprove(rec.id);
      } else {
        // Auto-derive an operator_category appropriate to what Intel proposed.
        const category =
          rec.action_type === 'add_bot_denylist_wallet' ? 'profitable_bot_misread_as_toxic'
          : rec.action_type === 'add_bot_allowlist_wallet' ? 'wrong_category_strength'
          : 'wrong_category_strength';
        res = await callReclassify(rec.id, {
          action_type: 'monitor_wallet',
          reason: 'Operator chose Track over Intel default',
          payload: {},
          operator_category: category,
          operator_note: '',
        });
      }
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          toast.success(
            data.rule_text
              ? `Tracking. Learned: "${data.rule_text.slice(0, 80)}${data.rule_text.length > 80 ? '…' : ''}"`
              : toastMsg
          );
        } else {
          toast.error(data.message || 'Track failed');
        }
      } else {
        toast.error('Track failed');
      }
    } catch {
      toast.error('Track failed');
    } finally {
      loadRecommendations();
    }
  };

  // TOXIC = "denylist this wallet with a specific type."
  // - If Intel already proposed add_bot_denylist_wallet: approve (analyst doesn't fire — Intel was right).
  // - Otherwise: reclassify to denylist with payload.deny_type so the executor stamps the right type.
  const handleToxic = async (rec: Recommendation, denyType: string, operatorCategory: string, note: string) => {
    try {
      let res: Response;
      if (rec.action_type === 'add_bot_denylist_wallet') {
        res = await callApprove(rec.id);
      } else {
        res = await callReclassify(rec.id, {
          action_type: 'add_bot_denylist_wallet',
          reason: note || `Marked toxic (${denyType})`,
          payload: { deny_type: denyType },
          operator_category: operatorCategory,
          operator_note: note,
        });
      }
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          toast.success(
            data.rule_text
              ? `Marked toxic. Learned: "${data.rule_text.slice(0, 80)}${data.rule_text.length > 80 ? '…' : ''}"`
              : `Marked ${rec.target_address.slice(0, 8)}… as toxic`
          );
        } else {
          toast.error(data.message || 'Toxic failed');
        }
      } else {
        toast.error('Toxic failed');
      }
    } catch {
      toast.error('Toxic failed');
    } finally {
      loadRecommendations();
    }
  };

  // SKIP = reject. Silent — no rule, no tag, no shadow change.
  const handleSkip = async (rec: Recommendation) => {
    try {
      const res = await callReject(rec.id);
      if (res.ok) toast.success('Skipped');
      else toast.error('Skip failed');
    } catch {
      toast.error('Skip failed');
    } finally {
      loadRecommendations();
    }
  };

  // REVERT for already-active recs. Same as before — undoes the executor side effect.
  const handleRevert = async (rec: Recommendation) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/intel/recommendations/${rec.id}/revert`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.success) toast.success(data.message);
        else toast.error(data.message);
      }
    } catch {
      toast.error('Revert failed');
    } finally {
      loadRecommendations();
    }
  };

  const proposed = recommendations.filter(r => r.status === 'proposed');
  const applied = recommendations.filter(r => r.status !== 'proposed');

  // Highest report_id among proposed cards = "the latest run." Used to badge new cards
  // so they're visually distinct from older still-pending recommendations.
  const latestReportId = proposed.length > 0
    ? Math.max(...proposed.map(r => r.report_id || 0))
    : 0;

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
          { key: 'overridden', label: 'Overridden' },
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
            <RecommendationCard
                key={rec.id}
                rec={rec}
                onTrack={handleTrack}
                onToxic={handleToxic}
                onSkip={handleSkip}
                onRevert={handleRevert}
                isLatestRun={rec.report_id === latestReportId}
              />
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
            <RecommendationCard
                key={rec.id}
                rec={rec}
                onTrack={handleTrack}
                onToxic={handleToxic}
                onSkip={handleSkip}
                onRevert={handleRevert}
                isLatestRun={rec.report_id === latestReportId}
              />
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
