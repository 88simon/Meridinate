'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '@/lib/api';
import { useStatusBarData } from '@/hooks/useStatusBarData';
import { StatusBar } from '@/components/status-bar';
import { Button } from '@/components/ui/button';
import {
  Loader2, Shield, ChevronDown, ChevronRight, Clock, FileText,
  Play, Zap, Hash,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface RugLabels {
  fake: number;
  real: number;
  unsure: number;
}

interface RugReport {
  id: number;
  tokens_analyzed: number;
  fake_count: number;
  real_count: number;
  unsure_count: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  duration_seconds: number;
  generated_at: string;
  report_text?: string;
}

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr.replace(' ', 'T') + (dateStr.includes('Z') ? '' : 'Z'));
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ago`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

export default function RugAnalysisPage() {
  const statusBarData = useStatusBarData();
  const [labels, setLabels] = useState<RugLabels | null>(null);
  const [reports, setReports] = useState<RugReport[]>([]);
  const [running, setRunning] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedReport, setExpandedReport] = useState<RugReport | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const loadLabels = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/tokens/rug-labels`);
      if (res.ok) {
        const data = await res.json();
        // Count labels from array or use pre-counted object
        if (Array.isArray(data)) {
          const counts: RugLabels = { fake: 0, real: 0, unsure: 0 };
          data.forEach((t: any) => {
            const label = (t.rug_label || '').toLowerCase();
            if (label === 'fake') counts.fake++;
            else if (label === 'real') counts.real++;
            else if (label === 'unsure') counts.unsure++;
          });
          setLabels(counts);
        } else if (data.fake !== undefined) {
          setLabels(data);
        }
      }
    } catch { /* silent */ }
  }, []);

  const loadReports = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/rug-analysis/reports?limit=10`);
      if (res.ok) {
        const data = await res.json();
        setReports(data.reports || []);
      }
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    loadLabels();
    loadReports();
  }, [loadLabels, loadReports]);

  // Poll for completion while running
  useEffect(() => {
    if (!running) return;
    const initialCount = reports.length;
    const initialId = reports[0]?.id ?? 0;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/rug-analysis/reports?limit=1`);
        if (res.ok) {
          const data = await res.json();
          const latest = data.reports?.[0];
          if (latest && latest.id !== initialId) {
            setRunning(false);
            toast.success('Rug analysis complete');
            loadReports();
            loadLabels();
          }
        }
      } catch { /* silent */ }
    }, 5000);
    return () => clearInterval(interval);
  }, [running, reports, loadReports, loadLabels]);

  const runAnalysis = async () => {
    try {
      setRunning(true);
      const res = await fetch(`${API_BASE_URL}/api/rug-analysis/run`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || err.error || 'Failed to start rug analysis');
        setRunning(false);
      }
    } catch {
      toast.error('Failed to start rug analysis');
      setRunning(false);
    }
  };

  const toggleReport = async (report: RugReport) => {
    if (expandedId === report.id) {
      setExpandedId(null);
      setExpandedReport(null);
      return;
    }
    setExpandedId(report.id);
    if (report.report_text) {
      setExpandedReport(report);
      return;
    }
    setLoadingDetail(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/rug-analysis/reports/${report.id}`);
      if (res.ok) {
        const data = await res.json();
        setExpandedReport(data);
      }
    } catch {
      toast.error('Failed to load report');
    } finally {
      setLoadingDetail(false);
    }
  };

  const totalLabeled = labels ? labels.fake + labels.real + labels.unsure : 0;

  return (
    <div className='w-full space-y-4 px-6 py-6'>
      {/* Header */}
      <div>
        <h1 className='text-2xl font-bold flex items-center gap-2'>
          <Shield className='h-6 w-6' />
          Rug Analysis
        </h1>
        <p className='text-muted-foreground text-sm'>
          AI-powered exploration of fake chart detection patterns
        </p>
      </div>

      {/* Stats bar */}
      <div className='rounded-lg border bg-card p-4'>
        {labels === null ? (
          <div className='flex items-center gap-2 text-sm text-muted-foreground'>
            <Loader2 className='h-4 w-4 animate-spin' />
            Loading label counts...
          </div>
        ) : totalLabeled === 0 ? (
          <p className='text-sm text-muted-foreground'>
            No labeled tokens found. Label tokens as FAKE, REAL, or UNSURE in the Token Leaderboard to enable rug analysis.
          </p>
        ) : (
          <div className='flex items-center gap-6 text-sm'>
            <span className='text-muted-foreground'>Labeled Tokens:</span>
            <span className='font-semibold text-red-400'>{labels.fake} FAKE</span>
            <span className='text-muted-foreground'>&middot;</span>
            <span className='font-semibold text-green-400'>{labels.real} REAL</span>
            <span className='text-muted-foreground'>&middot;</span>
            <span className='font-semibold text-yellow-400'>{labels.unsure} UNSURE</span>
          </div>
        )}
      </div>

      {/* Run button */}
      <div className='rounded-lg border bg-card p-4 space-y-3'>
        <div className='flex items-center gap-3'>
          <Button
            onClick={runAnalysis}
            disabled={running || totalLabeled === 0}
            size='lg'
            className='gap-2'
          >
            {running ? (
              <>
                <Loader2 className='h-5 w-5 animate-spin' />
                Running...
              </>
            ) : (
              <>
                <Play className='h-5 w-5' />
                Run Rug Analysis
              </>
            )}
          </Button>
          {running && (
            <span className='text-sm text-muted-foreground animate-pulse'>
              Running... (this may take a minute)
            </span>
          )}
        </div>
        <p className='text-[10px] text-muted-foreground'>
          Analyzes all manually labeled tokens, evaluates rug score accuracy, discovers new signals, and produces a report.
        </p>
      </div>

      {/* Reports list */}
      <div className='space-y-2'>
        <h2 className='text-sm font-semibold text-muted-foreground'>Reports</h2>
        {reports.length === 0 ? (
          <div className='rounded-lg border bg-card p-4'>
            <p className='text-sm text-muted-foreground'>No reports yet. Run an analysis to generate one.</p>
          </div>
        ) : (
          <div className='space-y-1'>
            {reports.map((report) => (
              <div key={report.id} className='rounded-lg border bg-card'>
                {/* Report header row */}
                <button
                  onClick={() => toggleReport(report)}
                  className='w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50'
                >
                  {expandedId === report.id ? (
                    <ChevronDown className='h-4 w-4 shrink-0 text-muted-foreground' />
                  ) : (
                    <ChevronRight className='h-4 w-4 shrink-0 text-muted-foreground' />
                  )}
                  <div className='flex-1 min-w-0 flex items-center gap-4 text-xs'>
                    <span className='text-muted-foreground flex items-center gap-1'>
                      <Clock className='h-3 w-3' />
                      {relativeTime(report.generated_at)}
                    </span>
                    <span className='flex items-center gap-1'>
                      <Hash className='h-3 w-3 text-muted-foreground' />
                      {report.tokens_analyzed} tokens
                      <span className='text-muted-foreground ml-1'>
                        ({report.fake_count}F / {report.real_count}R / {report.unsure_count}U)
                      </span>
                    </span>
                    <span className='flex items-center gap-1 text-muted-foreground'>
                      <Zap className='h-3 w-3' />
                      {report.tool_calls} tool calls
                    </span>
                    <span className='text-muted-foreground'>
                      {formatDuration(report.duration_seconds)}
                    </span>
                  </div>
                </button>

                {/* Expanded report detail */}
                {expandedId === report.id && (
                  <div className='border-t px-4 py-4'>
                    {loadingDetail ? (
                      <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                        <Loader2 className='h-4 w-4 animate-spin' />
                        Loading report...
                      </div>
                    ) : expandedReport?.report_text ? (
                      <div className='space-y-3'>
                        {/* Token usage stats */}
                        <div className='flex gap-4 text-[10px] text-muted-foreground'>
                          <span>Input tokens: {expandedReport.input_tokens?.toLocaleString()}</span>
                          <span>Output tokens: {expandedReport.output_tokens?.toLocaleString()}</span>
                          <span>Duration: {formatDuration(expandedReport.duration_seconds)}</span>
                        </div>
                        {/* Report text */}
                        <div
                          className='rounded-lg bg-muted/30 p-4 text-sm leading-relaxed'
                          style={{ whiteSpace: 'pre-wrap' }}
                        >
                          {expandedReport.report_text}
                        </div>
                      </div>
                    ) : (
                      <p className='text-sm text-muted-foreground'>No report text available.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
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
