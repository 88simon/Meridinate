'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { StatusBar } from '@/components/status-bar';
import { Button } from '@/components/ui/button';
import { Loader2, Brain, Zap, Users, ArrowRightLeft, Star, Download, FileText, Search } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { IntelRecommendationsPanel } from '@/components/intel-recommendations-panel';

interface IntelReport {
  id?: number;
  focus: string;
  report: string;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  duration_seconds: number;
  generated_at: string;
  // Saved transcript of agent dialogue from when this report was generated.
  // Backend stores it as a JSON string in the dialogue_json column.
  dialogue_json?: string | null;
  housekeeper?: {
    report: string;
    fixes_applied: number;
    tool_calls: number;
    skipped: boolean;
  };
}

interface DialogueEntry {
  agent: string;
  type: string;
  content: string;
  timestamp: string;
}

const FOCUS_OPTIONS = [
  { value: 'general', label: 'Full Scan', icon: Brain, desc: 'Comprehensive analysis across all categories' },
  { value: 'forensics', label: 'Forensics', icon: Search, desc: 'Top PnL forensics — classify leaderboard outliers, detect mirages, trace trails' },
  { value: 'convergence', label: 'Convergence', icon: Users, desc: 'Smart money clustering on new tokens' },
  { value: 'deployer', label: 'Deployers', icon: Zap, desc: 'High win-rate deployers and new launches' },
  { value: 'migrations', label: 'Migrations', icon: ArrowRightLeft, desc: 'Cold wallets funding new identities' },
  { value: 'starred', label: 'Starred', icon: Star, desc: 'Updates on your favorited wallets and tokens' },
];

export default function IntelPage() {
  const statusBarData = useStatusBarData();
  const [reports, setReports] = useState<IntelReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedFocus, setSelectedFocus] = useState('general');
  const [activeReport, setActiveReport] = useState<IntelReport | null>(null);
  const [status, setStatus] = useState<any>({ phase: '', detail: '', progress: 0, dialogue: [], usage: {} });

  // Track whether we need to select latest after loading
  const [selectLatestOnLoad, setSelectLatestOnLoad] = useState(false);

  // Poll status when running. Skip ticks while the tab is hidden — the run
  // continues server-side either way; we just resync visually on tab focus.
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/intel/status`);
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
          if (!data.running && data.phase === 'complete') {
            setSelectLatestOnLoad(true);
            setRunning(false);
            toast.success('Intel report complete');
          } else if (!data.running && data.phase === 'error') {
            setRunning(false);
            toast.error(`Agent error: ${data.detail}`);
          }
        }
      } catch { /* silent */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [running]);

  // When selectLatestOnLoad flips, reload and select
  useEffect(() => {
    if (selectLatestOnLoad) {
      loadReports(true);
      setSelectLatestOnLoad(false);
    }
  }, [selectLatestOnLoad]);

  const loadReports = async (selectLatest = false) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/intel/reports?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setReports(data.reports || []);
        if (data.reports?.length > 0 && (!activeReport || selectLatest)) {
          setActiveReport(data.reports[0]);
        }
      }
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  useEffect(() => { loadReports(); }, []);

  const runReport = async () => {
    setRunning(true);
    setStatus({ phase: 'starting', detail: 'Initializing pipeline...', progress: 0 });
    try {
      const res = await fetch(`${API_BASE_URL}/api/intel/run?focus=${selectedFocus}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'already_running') {
          toast.info('Analysis already in progress');
        } else {
          toast.info('Intel pipeline started — you can navigate away safely');
        }
      } else {
        toast.error('Failed to start analysis');
        setRunning(false);
      }
    } catch {
      toast.error('Failed to connect to backend');
      setRunning(false);
    }
  };

  const { openWIR } = useWalletIntelligence();

  // Solana address pattern: base58, 32-44 characters, not part of a longer word
  const SOLANA_ADDR_RE = /(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])/g;

  // Render a line with clickable Solana addresses
  const renderWithClickableAddresses = (text: string, className?: string) => {
    const parts: (string | React.ReactElement)[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    const re = new RegExp(SOLANA_ADDR_RE.source, 'g');

    while ((match = re.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      const addr = match[0];
      parts.push(
        <button
          key={`addr-${match.index}`}
          onClick={(e) => { e.stopPropagation(); openWIR(addr); }}
          className='font-mono text-primary hover:text-primary/80 hover:underline cursor-pointer transition-colors'
          title={`Open Wallet Intelligence Report for ${addr}`}
        >
          {addr}
        </button>
      );
      lastIndex = re.lastIndex;
    }
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }

    if (parts.length === 1 && typeof parts[0] === 'string') {
      return <span className={className}>{parts[0]}</span>;
    }
    return <span className={className}>{parts}</span>;
  };

  // Markdown-like rendering with clickable addresses
  const renderReport = (text: string) => {
    // Strip any ```json ... ``` blocks from display (structured data, not prose)
    const cleanText = text.replace(/```json\s*\{[\s\S]*?\}\s*```/g, '').trim();

    return cleanText.split('\n').map((line, i) => {
      // Headers
      if (line.startsWith('### ')) return <h3 key={i} className='text-base font-bold mt-4 mb-1'>{renderWithClickableAddresses(line.slice(4))}</h3>;
      if (line.startsWith('## ')) return <h2 key={i} className='text-lg font-bold mt-5 mb-2'>{renderWithClickableAddresses(line.slice(3))}</h2>;
      if (line.startsWith('# ')) return <h1 key={i} className='text-xl font-bold mt-6 mb-2'>{renderWithClickableAddresses(line.slice(2))}</h1>;

      // Bold sections with emoji
      if (line.match(/^[🔥👀⚠️🔄📊🎯💡🏆❌🔍🪙💰🔑]/)) {
        return <div key={i} className='text-sm font-semibold mt-4 mb-1'>{renderWithClickableAddresses(line)}</div>;
      }

      // Bullet points
      if (line.startsWith('- ') || line.startsWith('• ')) {
        return <div key={i} className='text-sm text-muted-foreground ml-4 my-0.5'>• {renderWithClickableAddresses(line.slice(2))}</div>;
      }

      // Lines with addresses — show full line with clickable addresses
      if (line.match(/[A-Za-z0-9]{32,}/)) {
        return <div key={i} className='text-xs text-muted-foreground my-0.5 break-all'>{renderWithClickableAddresses(line)}</div>;
      }

      // Empty lines
      if (!line.trim()) return <div key={i} className='h-2' />;

      // Regular text
      return <div key={i} className='text-sm text-foreground/90 my-0.5'>{renderWithClickableAddresses(line)}</div>;
    });
  };

  return (
    <div className='w-full space-y-4 px-6 py-6'>
      {/* Header */}
      <div className='flex items-center justify-between'>
        <div>
          <h1 className='text-2xl font-bold flex items-center gap-2'>
            <Brain className='h-6 w-6' />
            Intel Agent
          </h1>
          <p className='text-muted-foreground text-sm'>
            Bot-operator intelligence: allowlist/denylist classification, wallet reliability, toxic flow detection
          </p>
        </div>
      </div>

      {/* Focus selector + Run button */}
      <div className='flex items-center gap-3'>
        <div className='flex gap-1'>
          {FOCUS_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            return (
              <button
                key={opt.value}
                onClick={() => setSelectedFocus(opt.value)}
                className={cn(
                  'flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs transition-all',
                  selectedFocus === opt.value
                    ? 'border-primary bg-primary/10 text-primary font-medium'
                    : 'border-muted text-muted-foreground hover:text-foreground hover:border-foreground/30'
                )}
                title={opt.desc}
              >
                <Icon className='h-3.5 w-3.5' />
                {opt.label}
              </button>
            );
          })}
        </div>
        <Button
          onClick={runReport}
          disabled={running}
          className='gap-2'
        >
          {running ? (
            <><Loader2 className='h-4 w-4 animate-spin' /> Investigating...</>
          ) : (
            <><Brain className='h-4 w-4' /> Run Analysis</>
          )}
        </Button>
      </div>

      {/* Status box with agent dialogue */}
      {running && (
        <div className='rounded-lg border bg-card p-4 space-y-3'>
          {/* Progress header */}
          <div className='flex items-center gap-3'>
            <Loader2 className='h-4 w-4 animate-spin text-primary' />
            <span className='text-sm font-medium capitalize'>{status.phase || 'Starting'}...</span>
            <span className='text-xs text-muted-foreground ml-auto'>{status.progress}%</span>
          </div>
          <div className='h-2 w-full rounded-full bg-muted overflow-hidden'>
            <div className='h-full rounded-full bg-primary transition-all duration-500' style={{ width: `${status.progress}%` }} />
          </div>

          {/* API Usage */}
          {status.usage && (
            <div className='flex gap-4 text-[10px] text-muted-foreground'>
              {status.usage.housekeeper && (status.usage.housekeeper.input_tokens > 0 || status.usage.housekeeper.output_tokens > 0) && (
                <span>
                  Housekeeper: {((status.usage.housekeeper.input_tokens + status.usage.housekeeper.output_tokens) / 1000).toFixed(1)}k tokens
                  · {status.usage.housekeeper.tool_calls} queries
                  · {status.usage.housekeeper.fixes || 0} fixes
                  · ~${((status.usage.housekeeper.input_tokens * 3 + status.usage.housekeeper.output_tokens * 15) / 1000000).toFixed(3)}
                </span>
              )}
              {status.usage.investigator && (status.usage.investigator.input_tokens > 0 || status.usage.investigator.output_tokens > 0) && (
                <span>
                  Investigator: {((status.usage.investigator.input_tokens + status.usage.investigator.output_tokens) / 1000).toFixed(1)}k tokens
                  · {status.usage.investigator.tool_calls} queries
                  · ~${((status.usage.investigator.input_tokens * 3 + status.usage.investigator.output_tokens * 15) / 1000000).toFixed(3)}
                </span>
              )}
            </div>
          )}

          {/* Agent Dialogue */}
          {status.dialogue && status.dialogue.length > 0 && (
            <div className='max-h-[300px] overflow-y-auto rounded border bg-black/30 p-2 space-y-1 font-mono text-[11px]'>
              {status.dialogue.map((d: any, i: number) => (
                <div key={i} className='flex gap-2'>
                  <span className='text-muted-foreground shrink-0 w-16'>{d.timestamp}</span>
                  <span className={cn('shrink-0 w-20 font-medium',
                    d.agent === 'housekeeper' ? 'text-blue-400' :
                    d.agent === 'investigator' ? 'text-green-400' :
                    'text-muted-foreground'
                  )}>
                    {d.agent}
                  </span>
                  <span className={cn('shrink-0 w-16',
                    d.type === 'thinking' ? 'text-yellow-400/70' :
                    d.type === 'tool_call' ? 'text-cyan-400/70' :
                    d.type === 'fix' ? 'text-red-400/70' :
                    d.type === 'conclusion' ? 'text-green-400/70' :
                    'text-muted-foreground'
                  )}>
                    [{d.type}]
                  </span>
                  <span className='text-foreground/80 break-all'>{d.content}</span>
                </div>
              ))}
            </div>
          )}

          <p className='text-[10px] text-muted-foreground'>Safe to navigate away — report will be saved when complete</p>
        </div>
      )}

      {/* Main content: report + history sidebar */}
      <div className='flex gap-4'>
        {/* Report display */}
        <div className='flex-1 min-w-0'>
          {activeReport ? (
            <div className='rounded-lg border bg-card'>
              <div className='flex items-center justify-between border-b px-4 py-3'>
                <div>
                  <h2 className='text-sm font-semibold'>
                    {activeReport.focus === 'general' ? 'Full Scan' : activeReport.focus?.charAt(0).toUpperCase() + activeReport.focus?.slice(1)} Report
                  </h2>
                  <p className='text-[10px] text-muted-foreground'>
                    {activeReport.generated_at} ·
                    {activeReport.tool_calls} queries ·
                    {activeReport.duration_seconds}s ·
                    {((activeReport.input_tokens + activeReport.output_tokens) / 1000).toFixed(1)}k tokens ·
                    ~${((activeReport.input_tokens * 3 + activeReport.output_tokens * 15) / 1000000).toFixed(3)} API cost
                  </p>
                </div>
                {activeReport.id && (
                  <div className='flex gap-1.5'>
                    <a
                      href={`${API_BASE_URL}/api/intel/reports/${activeReport.id}/report.md`}
                      download
                      className='flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-muted text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors'
                      title='Download human-readable markdown report'
                    >
                      <FileText className='h-3 w-3' /> Report
                    </a>
                    <a
                      href={`${API_BASE_URL}/api/intel/reports/${activeReport.id}/bundle`}
                      download
                      className='flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-muted text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors'
                      title='Download full AI handoff bundle (JSON)'
                    >
                      <Download className='h-3 w-3' /> Bundle
                    </a>
                  </div>
                )}
              </div>
              <div className='p-5 max-h-[70vh] overflow-y-auto'>
                {/* Saved transcript — same renderer as the live dialogue feed.
                    Lets us replay what the agents said for past reports without
                    re-running them. */}
                {(() => {
                  let entries: DialogueEntry[] = [];
                  if (activeReport.dialogue_json) {
                    try {
                      const parsed = JSON.parse(activeReport.dialogue_json);
                      if (Array.isArray(parsed)) entries = parsed as DialogueEntry[];
                    } catch { /* leave empty */ }
                  }
                  if (entries.length === 0) return null;
                  return (
                    <details className='mb-4 rounded-lg border border-purple-500/20 bg-purple-500/5'>
                      <summary className='cursor-pointer px-3 py-2 text-xs font-semibold text-purple-300 hover:text-purple-200'>
                        Transcript ({entries.length} entries)
                      </summary>
                      <div className='max-h-[400px] overflow-y-auto rounded-b-lg border-t border-purple-500/20 bg-black/30 p-2 space-y-1 font-mono text-[11px]'>
                        {entries.map((d, i) => (
                          <div key={i} className='flex gap-2'>
                            <span className='text-muted-foreground shrink-0 w-16'>{d.timestamp}</span>
                            <span className={cn('shrink-0 w-20 font-medium',
                              d.agent === 'housekeeper' ? 'text-blue-400' :
                              d.agent === 'investigator' ? 'text-green-400' :
                              'text-muted-foreground'
                            )}>
                              {d.agent}
                            </span>
                            <span className={cn('shrink-0 w-16',
                              d.type === 'thinking' ? 'text-yellow-400/70' :
                              d.type === 'tool_call' ? 'text-cyan-400/70' :
                              d.type === 'fix' ? 'text-red-400/70' :
                              d.type === 'conclusion' ? 'text-green-400/70' :
                              'text-muted-foreground'
                            )}>
                              [{d.type}]
                            </span>
                            <span className='text-foreground/80 break-all'>{d.content}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  );
                })()}

                {/* Housekeeper summary */}
                {activeReport.housekeeper && !activeReport.housekeeper.skipped && (
                  <div className='rounded-lg border border-blue-500/20 bg-blue-500/5 p-3 mb-4'>
                    <div className='flex items-center gap-2 mb-1'>
                      <span className='text-xs font-semibold text-blue-400'>Housekeeper Verification</span>
                      <span className='text-[10px] text-muted-foreground'>
                        {activeReport.housekeeper.fixes_applied} fixes · {activeReport.housekeeper.tool_calls} queries
                      </span>
                    </div>
                    {activeReport.housekeeper.report && (
                      <details>
                        <summary className='text-[10px] text-muted-foreground cursor-pointer hover:text-foreground'>
                          View verification details
                        </summary>
                        <div className='mt-2 text-xs text-muted-foreground whitespace-pre-wrap break-all'>
                          {activeReport.housekeeper.report}
                        </div>
                      </details>
                    )}
                  </div>
                )}

                {/* Main report */}
                {renderReport(activeReport.report)}
              </div>
            </div>
          ) : loading ? (
            <div className='flex items-center justify-center py-16 text-muted-foreground'>
              <Loader2 className='h-5 w-5 animate-spin mr-2' /> Loading reports...
            </div>
          ) : (
            <div className='flex flex-col items-center justify-center py-16 text-muted-foreground gap-3'>
              <Brain className='h-12 w-12 opacity-20' />
              <p className='text-sm'>No reports yet. Run your first analysis above.</p>
              <p className='text-xs'>The agent will query your database, investigate patterns, and write a report.</p>
            </div>
          )}
        </div>

        {/* Right sidebar: Recommendations + Report History */}
        <div className='w-72 shrink-0 space-y-4 max-h-[85vh] overflow-y-auto'>
          {/* Recommendations panel */}
          <div className='rounded-lg border bg-card p-3'>
            <IntelRecommendationsPanel />
          </div>

          {/* Report history */}
          <div>
            <h3 className='text-xs font-semibold text-muted-foreground mb-2'>Report History</h3>
            <div className='space-y-1'>
              {reports.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setActiveReport(r)}
                  className={cn(
                    'w-full text-left rounded-lg border px-3 py-2 text-xs transition-all',
                    activeReport?.id === r.id
                      ? 'border-primary bg-primary/5'
                      : 'border-transparent hover:bg-muted/50'
                  )}
                >
                  <div className='font-medium'>
                    {r.focus === 'general' ? 'Full Scan' : r.focus?.charAt(0).toUpperCase() + r.focus?.slice(1)}
                  </div>
                  <div className='text-[10px] text-muted-foreground'>
                    {r.generated_at}
                    · {r.tool_calls} queries
                  </div>
                </button>
              ))}
              {reports.length === 0 && !loading && (
                <p className='text-[11px] text-muted-foreground'>No reports yet</p>
              )}
            </div>
          </div>
        </div>
      </div>
      <StatusBar
        tokensScanned={statusBarData.tokensScanned}
        tokensScannedToday={statusBarData.tokensScannedToday}
        latestAnalysis={null}
        latestTokenName={null}
        latestWalletsFound={null}
        latestApiCredits={null}
        totalApiCreditsToday={statusBarData.creditsUsedToday}
        recentOperations={statusBarData.recentOperations}
        onRefresh={statusBarData.refresh}
        lastUpdated={statusBarData.lastUpdated}
      />
    </div>
  );
}
