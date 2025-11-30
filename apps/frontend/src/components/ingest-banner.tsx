'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getIngestQueueStats, IngestQueueStats } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { ArrowRight, Sparkles, Info } from 'lucide-react';

// Banner preferences key (shared with master-control-modal.tsx)
const BANNER_PREFS_KEY = 'meridinate_banner_prefs';

interface BannerPrefs {
  showIngestBanner: boolean;
}

function loadBannerPrefs(): BannerPrefs {
  if (typeof window === 'undefined') return { showIngestBanner: true };
  try {
    const stored = localStorage.getItem(BANNER_PREFS_KEY);
    return stored ? JSON.parse(stored) : { showIngestBanner: true };
  } catch {
    return { showIngestBanner: true };
  }
}

export function IngestBanner() {
  const [stats, setStats] = useState<IngestQueueStats | null>(null);
  const [showBanner, setShowBanner] = useState(true);

  useEffect(() => {
    // Check banner preference
    const prefs = loadBannerPrefs();
    setShowBanner(prefs.showIngestBanner);

    // Listen for storage changes (when preference is updated in Settings)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === BANNER_PREFS_KEY) {
        const newPrefs = loadBannerPrefs();
        setShowBanner(newPrefs.showIngestBanner);
      }
    };
    window.addEventListener('storage', handleStorageChange);

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
    return () => {
      clearInterval(interval);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  const preAnalyzedCount = stats?.by_tier?.enriched || 0;

  // Don't show if disabled in preferences or no pre-analyzed tokens
  if (!showBanner || !preAnalyzedCount) return null;

  return (
    <TooltipProvider>
      <Link href='/dashboard/ingestion'>
        <div className='flex items-center justify-between rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-2 transition-colors hover:bg-green-500/20'>
          <div className='flex items-center gap-2'>
            <Sparkles className='h-4 w-4 text-green-400' />
            <span className='text-sm'>
              <Badge
                variant='secondary'
                className='mr-2 bg-green-500/20 text-green-400'
              >
                {preAnalyzedCount}
              </Badge>
              Pre-Analyzed token{preAnalyzedCount !== 1 ? 's' : ''} waiting for
              promotion
            </span>
            <Tooltip>
              <TooltipTrigger>
                <Info className='h-3 w-3 text-green-400/60' />
              </TooltipTrigger>
              <TooltipContent>
                Light Helius enrichment complete. Promote to run full analysis
                and add to Scanned Tokens.
              </TooltipContent>
            </Tooltip>
          </div>
          <div className='flex items-center gap-1 text-sm text-green-400'>
            View Ingestion
            <ArrowRight className='h-4 w-4' />
          </div>
        </div>
      </Link>
    </TooltipProvider>
  );
}
