'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import {
  updateSolscanSettings,
  SolscanSettings,
  API_BASE_URL
} from '@/lib/api';
import { NumericStepper } from './NumericStepper';
import { InfoTooltip } from './InfoTooltip';
import { fetchWithRetry } from './utils';
import { ApiSettings } from './types';

interface ScanningTabProps {
  apiSettings: ApiSettings;
  setApiSettings: (s: ApiSettings) => void;
  defaultApiSettings: ApiSettings;
}

export function ScanningTab({
  apiSettings,
  setApiSettings,
  defaultApiSettings
}: ScanningTabProps) {
  const [solscanSettings, setSolscanSettings] =
    useState<SolscanSettings | null>(null);
  const [loadingSolscan, setLoadingSolscan] = useState(true);
  const [solscanError, setSolscanError] = useState<string | null>(null);

  const loadSolscanSettings = async () => {
    setLoadingSolscan(true);
    setSolscanError(null);
    try {
      const res = await fetchWithRetry(`${API_BASE_URL}/api/solscan-settings`, {
        cache: 'no-store'
      });
      const data = await res.json();
      setSolscanSettings(data);
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy. Retried but still unavailable.'
          : 'Failed to load after retries';
      setSolscanError(message);
    } finally {
      setLoadingSolscan(false);
    }
  };

  useEffect(() => {
    loadSolscanSettings();
  }, []);

  const updateSolscan = async (updates: Partial<SolscanSettings>) => {
    if (!solscanSettings) return;
    const newSettings = { ...solscanSettings, ...updates };
    setSolscanSettings(newSettings);
    try {
      await updateSolscanSettings(updates);
      toast.success('Solscan settings saved');
    } catch {
      toast.error('Failed to save Solscan settings');
    }
  };

  const bypassLimits = apiSettings.bypassLimits ?? false;

  return (
    <div className='space-y-6'>
      {/* Bypass Limits Toggle */}
      <div className='bg-muted/50 flex items-center justify-between rounded-lg p-3'>
        <div className='space-y-0.5'>
          <p className='text-sm font-medium'>Bypass All Limits</p>
          <p className='text-muted-foreground text-xs'>
            Remove all slider caps (UI and backend validation)
          </p>
        </div>
        <Switch
          checked={bypassLimits}
          onCheckedChange={(v) =>
            setApiSettings({ ...apiSettings, bypassLimits: v })
          }
        />
      </div>

      {/* Scan Settings */}
      <div>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Scan Settings
          <InfoTooltip>
            Controls for token analysis: wallet limits, transaction depth, and
            filtering. Used by both manual scans and TIP promotions.
          </InfoTooltip>
        </h4>
        <div className='grid grid-cols-2 gap-4'>
          <NumericStepper
            label='Transaction Limit'
            value={apiSettings.transactionLimit}
            onChange={(v) =>
              setApiSettings({ ...apiSettings, transactionLimit: v })
            }
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                transactionLimit: defaultApiSettings.transactionLimit
              })
            }
            min={100}
            max={20000}
            step={500}
            tooltip='Maximum transactions to scan per wallet for early buyer detection (100-20k)'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Min USD Filter ($)'
            value={apiSettings.minUsdFilter}
            onChange={(v) =>
              setApiSettings({ ...apiSettings, minUsdFilter: v })
            }
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                minUsdFilter: defaultApiSettings.minUsdFilter
              })
            }
            min={10}
            max={500}
            step={10}
            tooltip='Minimum USD value to consider a wallet as an early buyer'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Wallet Count'
            value={apiSettings.walletCount}
            onChange={(v) => setApiSettings({ ...apiSettings, walletCount: v })}
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                walletCount: defaultApiSettings.walletCount
              })
            }
            min={5}
            step={5}
            tooltip='Number of early buyer wallets to track per token'
            bypassLimits={bypassLimits}
          />
          <NumericStepper
            label='Max Credits/Analysis'
            value={apiSettings.maxCreditsPerAnalysis}
            onChange={(v) =>
              setApiSettings({ ...apiSettings, maxCreditsPerAnalysis: v })
            }
            onReset={() =>
              setApiSettings({
                ...apiSettings,
                maxCreditsPerAnalysis: defaultApiSettings.maxCreditsPerAnalysis
              })
            }
            min={100}
            step={100}
            tooltip='Maximum Helius API credits to spend per token analysis'
            bypassLimits={bypassLimits}
          />
        </div>

        {/* Advanced Settings */}
        <details className='mt-4'>
          <summary className='text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium'>
            Advanced Settings
          </summary>
          <div className='mt-2 grid grid-cols-2 gap-4'>
            <div className='space-y-1'>
              <Label className='text-muted-foreground text-xs'>
                API Rate Delay (ms)
              </Label>
              <Input
                type='number'
                value={apiSettings.apiRateDelay}
                onChange={(e) =>
                  setApiSettings({
                    ...apiSettings,
                    apiRateDelay: parseInt(e.target.value) || 0
                  })
                }
                className='h-7 text-xs'
              />
            </div>
            <div className='space-y-1'>
              <Label className='text-muted-foreground text-xs'>
                Max Retries
              </Label>
              <Input
                type='number'
                value={apiSettings.maxRetries}
                onChange={(e) =>
                  setApiSettings({
                    ...apiSettings,
                    maxRetries: parseInt(e.target.value) || 0
                  })
                }
                className='h-7 text-xs'
              />
            </div>
          </div>
        </details>
      </div>

      {/* Solscan / Action Wheel Settings */}
      <div className='border-t pt-4'>
        <h4 className='text-muted-foreground mb-3 flex items-center text-xs font-semibold uppercase'>
          Solscan / Action Wheel
          <InfoTooltip>
            URL parameters for action wheel Solscan links. Changes sync to
            action_wheel_settings.ini.
          </InfoTooltip>
        </h4>

        {loadingSolscan ? (
          <div className='flex items-center justify-center py-4'>
            <Loader2 className='h-4 w-4 animate-spin' />
          </div>
        ) : solscanError ? (
          <div className='flex items-center justify-center gap-2 py-4'>
            <span className='text-muted-foreground text-xs'>
              {solscanError}
            </span>
            <Button
              variant='ghost'
              size='sm'
              className='h-6 px-2'
              onClick={loadSolscanSettings}
            >
              <RefreshCw className='h-3 w-3' />
            </Button>
          </div>
        ) : solscanSettings ? (
          <div className='grid grid-cols-2 gap-4'>
            <div className='space-y-1'>
              <Label className='text-xs'>Activity Type</Label>
              <select
                value={solscanSettings.activity_type}
                onChange={(e) =>
                  updateSolscan({ activity_type: e.target.value })
                }
                className='border-input bg-background flex h-7 w-full rounded-md border px-2 text-xs'
              >
                <option value='ACTIVITY_SPL_TRANSFER'>Transfer</option>
                <option value='ACTIVITY_SPL_MINT'>Mint</option>
                <option value='ACTIVITY_SPL_BURN'>Burn</option>
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-xs'>Page Size</Label>
              <select
                value={solscanSettings.page_size}
                onChange={(e) => updateSolscan({ page_size: e.target.value })}
                className='border-input bg-background flex h-7 w-full rounded-md border px-2 text-xs'
              >
                <option value='10'>10</option>
                <option value='20'>20</option>
                <option value='40'>40</option>
                <option value='100'>100</option>
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-xs'>Min Value ($)</Label>
              <Input
                type='number'
                value={solscanSettings.value}
                onChange={(e) => updateSolscan({ value: e.target.value })}
                className='h-7 text-xs'
              />
            </div>
            <div className='flex items-center gap-4'>
              <div className='flex items-center gap-2'>
                <Switch
                  checked={solscanSettings.exclude_amount_zero === 'true'}
                  onCheckedChange={(v) =>
                    updateSolscan({ exclude_amount_zero: v ? 'true' : 'false' })
                  }
                />
                <Label className='text-xs'>Exclude Zero</Label>
              </div>
              <div className='flex items-center gap-2'>
                <Switch
                  checked={solscanSettings.remove_spam === 'true'}
                  onCheckedChange={(v) =>
                    updateSolscan({ remove_spam: v ? 'true' : 'false' })
                  }
                />
                <Label className='text-xs'>Remove Spam</Label>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
