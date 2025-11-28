'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getIngestQueueStats, IngestQueueStats } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { ArrowRight, Sparkles } from 'lucide-react';

export function IngestBanner() {
  const [stats, setStats] = useState<IngestQueueStats | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await getIngestQueueStats();
        setStats(data);
      } catch (error) {
        // Silently fail - banner is optional
      }
    };

    fetchStats();
    // Refresh every 5 minutes
    const interval = setInterval(fetchStats, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const enrichedCount = stats?.by_tier?.enriched || 0;

  // Don't show if no enriched tokens
  if (!enrichedCount) return null;

  return (
    <Link href="/dashboard/ingestion">
      <div className="flex items-center justify-between rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-2 transition-colors hover:bg-green-500/20">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-green-400" />
          <span className="text-sm">
            <Badge
              variant="secondary"
              className="mr-2 bg-green-500/20 text-green-400"
            >
              {enrichedCount}
            </Badge>
            enriched token{enrichedCount !== 1 ? 's' : ''} ready for promotion
          </span>
        </div>
        <div className="flex items-center gap-1 text-sm text-green-400">
          View Ingestion
          <ArrowRight className="h-4 w-4" />
        </div>
      </div>
    </Link>
  );
}
