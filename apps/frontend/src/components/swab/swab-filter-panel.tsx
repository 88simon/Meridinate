'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';

interface SwabFilters {
  status: 'holding' | 'sold' | 'stale' | 'all';
  pnl_min: number | undefined;
  pnl_max: number | undefined;
}

interface SwabFilterPanelProps {
  filters: SwabFilters;
  onClose: () => void;
  onApply: (filters: SwabFilters) => void;
}

export function SwabFilterPanel({ filters, onClose, onApply }: SwabFilterPanelProps) {
  const [status, setStatus] = useState(filters.status);
  const [pnlMin, setPnlMin] = useState<string>(filters.pnl_min?.toString() ?? '');
  const [pnlMax, setPnlMax] = useState<string>(filters.pnl_max?.toString() ?? '');

  // Handle ESC key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleApply = () => {
    onApply({
      status,
      pnl_min: pnlMin ? parseFloat(pnlMin) : undefined,
      pnl_max: pnlMax ? parseFloat(pnlMax) : undefined
    });
  };

  const handleClear = () => {
    setStatus('all');
    setPnlMin('');
    setPnlMax('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-card w-full max-w-md rounded-lg border shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">Filter SWAB Display</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-6 p-4">
          {/* Position Status */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Position Status</label>
            <div className="flex flex-wrap gap-2">
              {[
                { value: 'all', label: 'All' },
                { value: 'holding', label: 'Holding' },
                { value: 'sold', label: 'Sold (Historical)' },
                { value: 'stale', label: 'Stale (Need Check)' }
              ].map((opt) => (
                <button
                  key={opt.value}
                  className={`rounded px-3 py-1.5 text-sm ${
                    status === opt.value
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:bg-muted/80'
                  }`}
                  onClick={() => setStatus(opt.value as typeof status)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* PnL Range */}
          <div className="space-y-2">
            <label className="text-sm font-medium">PnL Range</label>
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <label className="text-muted-foreground mb-1 block text-xs">Min</label>
                <input
                  type="number"
                  value={pnlMin}
                  onChange={(e) => setPnlMin(e.target.value)}
                  placeholder="0.1"
                  step="0.1"
                  min="0"
                  className="bg-background w-full rounded border p-2 text-sm"
                />
              </div>
              <span className="text-muted-foreground pt-5">to</span>
              <div className="flex-1">
                <label className="text-muted-foreground mb-1 block text-xs">Max</label>
                <input
                  type="number"
                  value={pnlMax}
                  onChange={(e) => setPnlMax(e.target.value)}
                  placeholder="10.0"
                  step="0.1"
                  min="0"
                  className="bg-background w-full rounded border p-2 text-sm"
                />
              </div>
            </div>
            <p className="text-muted-foreground text-xs">
              Filter by PnL ratio (e.g., 1.0 = break-even, 2.0 = 2x gain)
            </p>
          </div>
        </div>

        <div className="flex justify-between border-t p-4">
          <Button variant="ghost" onClick={handleClear}>
            Clear Filters
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleApply}>Apply Filters</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
