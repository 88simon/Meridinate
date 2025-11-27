'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { SwabSettings } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';

interface SwabSettingsPanelProps {
  settings: SwabSettings;
  onClose: () => void;
  onSave: (settings: Partial<SwabSettings>) => void;
}

export function SwabSettingsPanel({ settings, onClose, onSave }: SwabSettingsPanelProps) {
  const [autoCheckEnabled, setAutoCheckEnabled] = useState(settings.auto_check_enabled);
  const [checkInterval, setCheckInterval] = useState(settings.check_interval_minutes);
  const [dailyBudget, setDailyBudget] = useState(settings.daily_credit_budget);
  const [staleThreshold, setStaleThreshold] = useState(settings.stale_threshold_minutes);
  const [minTokenCount, setMinTokenCount] = useState(settings.min_token_count);

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

  const handleSave = () => {
    onSave({
      auto_check_enabled: autoCheckEnabled,
      check_interval_minutes: checkInterval,
      daily_credit_budget: dailyBudget,
      stale_threshold_minutes: staleThreshold,
      min_token_count: minTokenCount
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-card w-full max-w-md rounded-lg border shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">SWAB Configuration</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-6 p-4">
          {/* MTEW → SWAB Gate - Most important setting, shown first */}
          <div className="bg-primary/5 -mx-4 space-y-2 border-b px-4 pb-4">
            <label className="text-sm font-medium">MTEW → SWAB Gate</label>
            <p className="text-muted-foreground mb-2 text-xs">
              Only MTEWs appearing in <strong>{minTokenCount}+</strong> analyzed tokens get tracked
            </p>
            <input
              type="range"
              value={minTokenCount}
              onChange={(e) => setMinTokenCount(Number(e.target.value))}
              min={1}
              max={10}
              className="w-full"
            />
            <div className="flex justify-between text-xs">
              <span>1</span>
              <span className="text-primary font-bold">{minTokenCount}+ tokens</span>
              <span>10</span>
            </div>
          </div>

          {/* Auto-Check Toggle */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Auto-Check</label>
            <div className="flex items-center gap-4">
              <button
                className={`rounded px-4 py-2 text-sm ${
                  autoCheckEnabled
                    ? 'bg-green-500 text-white'
                    : 'bg-muted text-muted-foreground'
                }`}
                onClick={() => setAutoCheckEnabled(true)}
              >
                Enabled
              </button>
              <button
                className={`rounded px-4 py-2 text-sm ${
                  !autoCheckEnabled
                    ? 'bg-red-500 text-white'
                    : 'bg-muted text-muted-foreground'
                }`}
                onClick={() => setAutoCheckEnabled(false)}
              >
                Disabled
              </button>
            </div>
            <p className="text-muted-foreground text-xs">
              When enabled, positions are checked automatically at the interval below
            </p>
          </div>

          {/* Check Interval */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Check Interval</label>
            <select
              value={checkInterval}
              onChange={(e) => setCheckInterval(Number(e.target.value))}
              className="bg-background w-full rounded border p-2 text-sm"
            >
              <option value={5}>Every 5 minutes</option>
              <option value={10}>Every 10 minutes</option>
              <option value={15}>Every 15 minutes</option>
              <option value={30}>Every 30 minutes</option>
              <option value={60}>Every 1 hour</option>
              <option value={120}>Every 2 hours</option>
              <option value={240}>Every 4 hours</option>
            </select>
            <p className="text-muted-foreground text-xs">
              How often to check if wallets still hold their positions
            </p>
          </div>

          {/* Daily Credit Budget */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Daily Credit Budget</label>
            <input
              type="number"
              value={dailyBudget}
              onChange={(e) => setDailyBudget(Number(e.target.value))}
              min={0}
              max={10000}
              className="bg-background w-full rounded border p-2 text-sm"
            />
            <p className="text-muted-foreground text-xs">
              Maximum credits to spend on position checks per day (10 credits per check)
            </p>
          </div>

          {/* Stale Threshold */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Stale Threshold (minutes)</label>
            <input
              type="number"
              value={staleThreshold}
              onChange={(e) => setStaleThreshold(Number(e.target.value))}
              min={5}
              max={1440}
              className="bg-background w-full rounded border p-2 text-sm"
            />
            <p className="text-muted-foreground text-xs">
              Positions not checked within this time are considered stale
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t p-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save Settings</Button>
        </div>
      </div>
    </div>
  );
}
