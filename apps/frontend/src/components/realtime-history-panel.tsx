'use client';

import { useEffect, useState, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { TokenAddressCell } from '@/components/token-address-cell';
import { X, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface Detection {
  id: number;
  token_address: string;
  deployer_address: string | null;
  detected_at: string;
  conviction_score: number;
  deployer_score: number;
  safety_score: number;
  social_proof_score: number;
  deployer_token_count: number;
  deployer_win_rate: number | null;
  deployer_tags_json: string | null;
  status: string;
  rejection_reason: string | null;
  token_name: string | null;
  token_symbol: string | null;
  crime_risk_score: number;
  buys_in_first_3_blocks: number;
  fresh_buyer_pct: number;
  buyers_sharing_funder: number;
  deployer_linked_to_buyer: number;
  auto_scan_picked_up_at: string | null;
  auto_scan_token_id: number | null;
  time_to_migration_minutes: number | null;
}

interface HistoryResponse {
  total: number;
  showing: number;
  status_counts: Record<string, number>;
  linked_to_auto_scan: number;
  detections: Detection[];
}

interface Props {
  open: boolean;
  onClose: () => void;
}

function statusColor(status: string): string {
  switch (status) {
    case 'high_conviction': return 'text-green-400';
    case 'watching': return 'text-yellow-400';
    case 'weak': return 'text-zinc-400';
    case 'rejected': return 'text-red-400';
    default: return 'text-muted-foreground';
  }
}

function statusBg(status: string): string {
  switch (status) {
    case 'high_conviction': return 'bg-green-500/10';
    case 'watching': return 'bg-yellow-500/10';
    case 'weak': return 'bg-zinc-500/10';
    case 'rejected': return 'bg-red-500/10';
    default: return '';
  }
}

export function RealtimeHistoryPanel({ open, onClose }: Props) {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (filter) params.set('status', filter);
      const res = await fetch(`${API_BASE_URL}/api/ingest/realtime/history?${params}`);
      if (res.ok) setData(await res.json());
    } catch {
      toast.error('Failed to load detection history');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (open) fetchHistory();
  }, [open, fetchHistory]);

  const deleteDetection = async (tokenAddress: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/ingest/realtime/history/${tokenAddress}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success('Detection deleted');
        fetchHistory();
      }
    } catch {
      toast.error('Failed to delete');
    }
  };

  if (!open) return null;

  return (
    <div className='fixed inset-0 z-50 flex justify-end bg-black/40' onClick={onClose}>
      <div
        className='flex h-full w-[600px] flex-col border-l bg-background shadow-xl animate-in slide-in-from-right duration-200'
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-4 py-3'>
          <div>
            <h3 className='text-sm font-semibold'>Webhook Detection History</h3>
            <p className='text-muted-foreground text-[10px]'>
              Audit saved real-time detections · {data?.total ?? 0} total · {data?.linked_to_auto_scan ?? 0} linked to auto-scan
            </p>
          </div>
          <Button variant='ghost' size='sm' onClick={onClose} className='h-7 w-7 p-0'>
            <X className='h-4 w-4' />
          </Button>
        </div>

        {/* Filter tabs */}
        <div className='flex items-center gap-1 border-b px-4 py-2'>
          {[
            { key: null, label: 'All' },
            { key: 'high_conviction', label: `High Conviction (${data?.status_counts?.high_conviction ?? 0})` },
            { key: 'watching', label: `Watching (${data?.status_counts?.watching ?? 0})` },
            { key: 'weak', label: `Weak (${data?.status_counts?.weak ?? 0})` },
            { key: 'rejected', label: `Rejected (${data?.status_counts?.rejected ?? 0})` },
          ].map((tab) => (
            <Button
              key={tab.key ?? 'all'}
              variant={filter === tab.key ? 'default' : 'ghost'}
              size='sm'
              className='h-6 text-[10px]'
              onClick={() => setFilter(tab.key)}
            >
              {tab.label}
            </Button>
          ))}
        </div>

        {/* Detection list */}
        <div className='flex-1 overflow-y-auto'>
          {loading && (
            <div className='py-8 text-center text-muted-foreground text-sm'>Loading...</div>
          )}

          {data && !loading && data.detections.length === 0 && (
            <div className='py-8 text-center text-muted-foreground text-sm'>
              No detections found{filter ? ` with status "${filter}"` : ''}.
            </div>
          )}

          {data && !loading && data.detections.map((d) => {
            const tags = d.deployer_tags_json ? JSON.parse(d.deployer_tags_json) : [];
            return (
              <div
                key={d.id}
                className={cn(
                  'border-b px-4 py-2.5 hover:bg-blue-500/10 transition-colors',
                  statusBg(d.status)
                )}
              >
                <div className='flex items-start justify-between gap-2'>
                  <div className='min-w-0 flex-1'>
                    {/* Row 1: Name + score + status */}
                    <div className='flex items-center gap-2'>
                      <span className='text-sm font-medium'>
                        {d.token_symbol || d.token_name || d.token_address.slice(0, 12) + '...'}
                      </span>
                      <span className={cn('text-xs font-bold', d.conviction_score >= 70 ? 'text-green-400' : d.conviction_score >= 40 ? 'text-yellow-400' : 'text-red-400')}>
                        {d.conviction_score}
                      </span>
                      <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-medium', statusBg(d.status), statusColor(d.status))}>
                        {d.status.toUpperCase().replace('_', ' ')}
                      </span>
                      {d.auto_scan_token_id && (
                        <span className='rounded bg-blue-500/20 px-1.5 py-0.5 text-[9px] text-blue-400'>
                          Linked to #{d.auto_scan_token_id}
                        </span>
                      )}
                    </div>

                    {/* Row 2: Address + time */}
                    <div className='flex items-center gap-2 mt-0.5'>
                      <TokenAddressCell address={d.token_address} compact showTwitter={false} />
                      <span className='text-muted-foreground text-[10px] shrink-0'>
                        {new Date(d.detected_at).toLocaleString(undefined, {
                          month: 'short', day: 'numeric',
                          hour: '2-digit', minute: '2-digit', second: '2-digit'
                        })}
                      </span>
                    </div>

                    {/* Row 3: Score breakdown */}
                    <div className='flex items-center gap-3 mt-1 text-[10px] text-muted-foreground'>
                      <span>Deployer: {d.deployer_score}/40</span>
                      <span>Safety: {d.safety_score}/30</span>
                      <span>Social: {d.social_proof_score}/30</span>
                      {d.crime_risk_score > 0 && (
                        <span className={d.crime_risk_score >= 70 ? 'text-orange-400' : ''}>
                          Crime Risk: {d.crime_risk_score}
                        </span>
                      )}
                    </div>

                    {/* Row 4: Deployer info */}
                    <div className='flex items-center gap-2 mt-0.5 text-[10px]'>
                      {d.deployer_address && (
                        <span className='text-muted-foreground font-mono'>
                          Deployer: {d.deployer_address.slice(0, 12)}...
                        </span>
                      )}
                      {d.deployer_token_count > 0 && (
                        <span className='text-muted-foreground'>{d.deployer_token_count} tokens</span>
                      )}
                      {d.deployer_win_rate !== null && (
                        <span className={d.deployer_win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                          {(d.deployer_win_rate * 100).toFixed(0)}% win
                        </span>
                      )}
                      {tags.length > 0 && tags.map((tag: string) => (
                        <span key={tag} className='rounded bg-purple-500/20 px-1 py-0.5 text-[8px] text-purple-400'>
                          {tag}
                        </span>
                      ))}
                    </div>

                    {/* Row 5: Crime coin details if present */}
                    {(d.buys_in_first_3_blocks > 0 || d.fresh_buyer_pct > 0) && (
                      <div className='flex items-center gap-3 mt-0.5 text-[10px] text-muted-foreground'>
                        {d.buys_in_first_3_blocks > 0 && <span>Bundled buys: {d.buys_in_first_3_blocks}</span>}
                        {d.fresh_buyer_pct > 0 && <span>Fresh buyers: {d.fresh_buyer_pct.toFixed(0)}%</span>}
                        {d.buyers_sharing_funder > 0 && <span>Shared funder: {d.buyers_sharing_funder}</span>}
                        {d.deployer_linked_to_buyer && <span className='text-amber-400'>Deployer⟷Buyer</span>}
                      </div>
                    )}

                    {/* Row 6: Rejection reason */}
                    {d.rejection_reason && (
                      <div className='mt-0.5 text-[10px] text-red-400'>
                        Reason: {d.rejection_reason}
                      </div>
                    )}

                    {/* Row 7: Cross-system */}
                    {d.time_to_migration_minutes && (
                      <div className='mt-0.5 text-[10px] text-blue-400'>
                        Migration: {d.time_to_migration_minutes.toFixed(1)} min → Auto-scan token #{d.auto_scan_token_id}
                      </div>
                    )}
                  </div>

                  {/* Delete button */}
                  <Button
                    variant='ghost'
                    size='sm'
                    className='h-6 w-6 p-0 shrink-0 opacity-30 hover:opacity-100 hover:text-red-400'
                    onClick={() => deleteDetection(d.token_address)}
                    title='Delete this detection'
                  >
                    <Trash2 className='h-3 w-3' />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
