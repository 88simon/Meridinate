'use client';

import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react';
import { useState, useEffect } from 'react';
import {
  getSolscanSettings,
  updateSolscanSettings,
  SolscanSettings
} from '@/lib/api';
import { toast } from 'sonner';

interface ApiSettings {
  transactionLimit: number;
  minUsdFilter: number;
  walletCount: number;
  apiRateDelay: number;
  maxCreditsPerAnalysis: number;
  maxRetries: number;
}

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apiSettings: ApiSettings;
  setApiSettings: (settings: ApiSettings) => void;
  defaultApiSettings: ApiSettings;
  children: React.ReactNode;
}

const defaultSolscanSettings: SolscanSettings = {
  activity_type: 'ACTIVITY_SPL_TRANSFER', // Correct type for SPL tokens (includes SOL)
  exclude_amount_zero: 'true',
  remove_spam: 'true',
  value: '100',
  token_address: 'So11111111111111111111111111111111111111111', // SOL token address
  page_size: '10'
};

export function SettingsModal({
  open,
  onOpenChange,
  apiSettings,
  setApiSettings,
  defaultApiSettings,
  children
}: SettingsModalProps) {
  const [solscanSettings, setSolscanSettings] = useState<SolscanSettings>(
    defaultSolscanSettings
  );
  const [loadingSolscanSettings, setLoadingSolscanSettings] = useState(false);

  // Load Solscan settings when modal opens
  useEffect(() => {
    if (open) {
      setLoadingSolscanSettings(true);
      getSolscanSettings()
        .then(setSolscanSettings)
        .catch(() => {
          toast.error('Failed to load Solscan settings');
        })
        .finally(() => setLoadingSolscanSettings(false));
    }
  }, [open]);

  // Auto-save Solscan settings when they change
  useEffect(() => {
    if (!open || loadingSolscanSettings) return;

    const timer = setTimeout(() => {
      updateSolscanSettings(solscanSettings)
        .then(() => {
          toast.success('Solscan settings saved', {
            description: 'Changes synced to action_wheel_settings.ini',
            duration: 2000
          });
        })
        .catch(() => {
          toast.error('Failed to save Solscan settings');
        });
    }, 300);

    return () => clearTimeout(timer);
  }, [solscanSettings, open, loadingSolscanSettings]);

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        side='right'
        align='start'
        className='max-h-[500px] w-[300px] overflow-y-auto p-4'
      >
        <div className='mb-4 space-y-1'>
          <h3 className='text-sm font-semibold'>Settings</h3>
          <p className='text-muted-foreground text-xs'>
            Configure API and Solscan parameters
          </p>
        </div>

        {/* API Settings Section */}
        <div className='mb-6'>
          <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
            API Settings
          </h4>

          <div className='space-y-4'>
            {/* Transaction Limit */}
            <div className='space-y-1'>
              <Label className='text-xs'>Transaction Limit</Label>
              <div className='flex items-center gap-1'>
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      transactionLimit: Math.max(
                        100,
                        apiSettings.transactionLimit - 100
                      )
                    })
                  }
                >
                  <ChevronLeft className='h-3 w-3' />
                </Button>
                <Input
                  type='number'
                  value={apiSettings.transactionLimit}
                  onChange={(e) =>
                    setApiSettings({
                      ...apiSettings,
                      transactionLimit: parseInt(e.target.value) || 0
                    })
                  }
                  onMouseDown={(e) => {
                    const startX = e.clientX;
                    const startValue = apiSettings.transactionLimit;
                    const handleMouseMove = (moveEvent: MouseEvent) => {
                      const diff =
                        Math.floor((moveEvent.clientX - startX) / 5) * 100;
                      const newValue = Math.max(
                        100,
                        Math.min(2000, startValue + diff)
                      );
                      setApiSettings({
                        ...apiSettings,
                        transactionLimit: newValue
                      });
                    };
                    const handleMouseUp = () => {
                      document.removeEventListener(
                        'mousemove',
                        handleMouseMove
                      );
                      document.removeEventListener('mouseup', handleMouseUp);
                    };
                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                  }}
                  className='h-7 cursor-ew-resize text-center text-xs [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
                />
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      transactionLimit: Math.min(
                        2000,
                        apiSettings.transactionLimit + 100
                      )
                    })
                  }
                >
                  <ChevronRight className='h-3 w-3' />
                </Button>
                <Button
                  variant='ghost'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      transactionLimit: defaultApiSettings.transactionLimit
                    })
                  }
                  title='Reset to default'
                >
                  <RotateCcw className='h-3 w-3' />
                </Button>
              </div>
            </div>

            {/* Min USD Filter */}
            <div className='space-y-1'>
              <Label className='text-xs'>Min USD ($)</Label>
              <div className='flex items-center gap-1'>
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      minUsdFilter: Math.max(10, apiSettings.minUsdFilter - 10)
                    })
                  }
                >
                  <ChevronLeft className='h-3 w-3' />
                </Button>
                <Input
                  type='number'
                  value={apiSettings.minUsdFilter}
                  onChange={(e) =>
                    setApiSettings({
                      ...apiSettings,
                      minUsdFilter: parseInt(e.target.value) || 0
                    })
                  }
                  onMouseDown={(e) => {
                    const startX = e.clientX;
                    const startValue = apiSettings.minUsdFilter;
                    const handleMouseMove = (moveEvent: MouseEvent) => {
                      const diff =
                        Math.floor((moveEvent.clientX - startX) / 5) * 10;
                      const newValue = Math.max(
                        10,
                        Math.min(500, startValue + diff)
                      );
                      setApiSettings({
                        ...apiSettings,
                        minUsdFilter: newValue
                      });
                    };
                    const handleMouseUp = () => {
                      document.removeEventListener(
                        'mousemove',
                        handleMouseMove
                      );
                      document.removeEventListener('mouseup', handleMouseUp);
                    };
                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                  }}
                  className='h-7 cursor-ew-resize text-center text-xs [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
                />
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      minUsdFilter: Math.min(500, apiSettings.minUsdFilter + 10)
                    })
                  }
                >
                  <ChevronRight className='h-3 w-3' />
                </Button>
                <Button
                  variant='ghost'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      minUsdFilter: defaultApiSettings.minUsdFilter
                    })
                  }
                  title='Reset to default'
                >
                  <RotateCcw className='h-3 w-3' />
                </Button>
              </div>
            </div>

            {/* Wallet Count */}
            <div className='space-y-1'>
              <Label className='text-xs'>Wallet Count</Label>
              <div className='flex items-center gap-1'>
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      walletCount: Math.max(5, apiSettings.walletCount - 5)
                    })
                  }
                >
                  <ChevronLeft className='h-3 w-3' />
                </Button>
                <Input
                  type='number'
                  value={apiSettings.walletCount}
                  onChange={(e) =>
                    setApiSettings({
                      ...apiSettings,
                      walletCount: parseInt(e.target.value) || 0
                    })
                  }
                  onMouseDown={(e) => {
                    const startX = e.clientX;
                    const startValue = apiSettings.walletCount;
                    const handleMouseMove = (moveEvent: MouseEvent) => {
                      const diff =
                        Math.floor((moveEvent.clientX - startX) / 10) * 5;
                      const newValue = Math.max(5, startValue + diff);
                      setApiSettings({
                        ...apiSettings,
                        walletCount: newValue
                      });
                    };
                    const handleMouseUp = () => {
                      document.removeEventListener(
                        'mousemove',
                        handleMouseMove
                      );
                      document.removeEventListener('mouseup', handleMouseUp);
                    };
                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                  }}
                  className='h-7 cursor-ew-resize text-center text-xs [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
                />
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      walletCount: apiSettings.walletCount + 5
                    })
                  }
                >
                  <ChevronRight className='h-3 w-3' />
                </Button>
                <Button
                  variant='ghost'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setApiSettings({
                      ...apiSettings,
                      walletCount: defaultApiSettings.walletCount
                    })
                  }
                  title='Reset to default'
                >
                  <RotateCcw className='h-3 w-3' />
                </Button>
              </div>
            </div>

            {/* Advanced Settings */}
            <details className='space-y-2'>
              <summary className='text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium'>
                Advanced Settings
              </summary>
              <div className='space-y-4 pt-2'>
                {/* API Rate Delay */}
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

                {/* Max Credits Per Analysis */}
                <div className='space-y-1'>
                  <Label className='text-muted-foreground text-xs'>
                    Max Credits Per Analysis
                  </Label>
                  <Input
                    type='number'
                    value={apiSettings.maxCreditsPerAnalysis}
                    onChange={(e) =>
                      setApiSettings({
                        ...apiSettings,
                        maxCreditsPerAnalysis: parseInt(e.target.value) || 0
                      })
                    }
                    className='h-7 text-xs'
                  />
                </div>

                {/* Max Retries */}
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

            {/* Current Settings JSON */}
            <details className='space-y-2'>
              <summary className='text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium'>
                View JSON
              </summary>
              <pre className='text-muted-foreground bg-muted mt-2 max-h-40 overflow-auto rounded p-3 text-xs'>
                {JSON.stringify(apiSettings, null, 2)}
              </pre>
            </details>
          </div>
        </div>

        {/* Solscan Settings Section */}
        <div className='border-t pt-4'>
          <h4 className='text-muted-foreground mb-3 text-xs font-semibold uppercase'>
            Solscan Settings
          </h4>
          <p className='text-muted-foreground mb-3 text-xs'>
            URL parameters for action wheel Solscan links
          </p>

          <div className='space-y-3'>
            {/* Activity Type */}
            <div className='space-y-1'>
              <Label className='text-xs'>Activity Type</Label>
              <select
                value={solscanSettings.activity_type}
                onChange={(e) =>
                  setSolscanSettings({
                    ...solscanSettings,
                    activity_type: e.target.value
                  })
                }
                className='border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-7 w-full rounded-md border px-3 text-xs focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
                disabled={loadingSolscanSettings}
              >
                <optgroup label='Token Operations'>
                  <option value='ACTIVITY_SPL_TRANSFER'>Transfer</option>
                  <option value='ACTIVITY_SPL_MINT'>Mint</option>
                  <option value='ACTIVITY_SPL_BURN'>Burn</option>
                  <option value='ACTIVITY_SPL_CREATE_ACCOUNT'>
                    Create Account
                  </option>
                  <option value='ACTIVITY_SPL_CLOSE_ACCOUNT'>
                    Close Account
                  </option>
                  <option value='ACTIVITY_SPL_SET_OWNER_AUTHORITY'>
                    Set Authority
                  </option>
                </optgroup>
                <optgroup label='Staking Operations'>
                  <option value='ACTIVITY_SPL_TOKEN_SPLIT_STAKE'>
                    Split Stake
                  </option>
                  <option value='ACTIVITY_SPL_TOKEN_MERGE_STAKE'>
                    Merge Stake
                  </option>
                  <option value='ACTIVITY_SPL_TOKEN_WITHDRAW_STAKE'>
                    Withdraw Stake
                  </option>
                  <option value='ACTIVITY_SPL_VOTE_WITHDRAW'>
                    Vote Withdraw
                  </option>
                </optgroup>
              </select>
              <p className='text-muted-foreground text-xs'>
                Matches Solscan&apos;s Action filter. Use Token Address below to
                filter SOL vs SPL tokens.
              </p>
            </div>

            {/* Exclude Amount Zero */}
            <div className='space-y-1'>
              <Label className='text-xs'>Exclude Amount Zero</Label>
              <select
                value={solscanSettings.exclude_amount_zero}
                onChange={(e) =>
                  setSolscanSettings({
                    ...solscanSettings,
                    exclude_amount_zero: e.target.value
                  })
                }
                className='border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-7 w-full rounded-md border px-3 text-xs focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
                disabled={loadingSolscanSettings}
              >
                <option value='true'>True</option>
                <option value='false'>False</option>
              </select>
            </div>

            {/* Remove Spam */}
            <div className='space-y-1'>
              <Label className='text-xs'>Remove Spam</Label>
              <select
                value={solscanSettings.remove_spam}
                onChange={(e) =>
                  setSolscanSettings({
                    ...solscanSettings,
                    remove_spam: e.target.value
                  })
                }
                className='border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-7 w-full rounded-md border px-3 text-xs focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
                disabled={loadingSolscanSettings}
              >
                <option value='true'>True</option>
                <option value='false'>False</option>
              </select>
            </div>

            {/* Min Value */}
            <div className='space-y-1'>
              <Label className='text-xs'>Min Value</Label>
              <div className='flex items-center gap-1'>
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setSolscanSettings({
                      ...solscanSettings,
                      value: String(
                        Math.max(0, parseInt(solscanSettings.value) - 10)
                      )
                    })
                  }
                  disabled={loadingSolscanSettings}
                >
                  <ChevronLeft className='h-3 w-3' />
                </Button>
                <Input
                  type='number'
                  value={solscanSettings.value}
                  onChange={(e) =>
                    setSolscanSettings({
                      ...solscanSettings,
                      value: e.target.value
                    })
                  }
                  onMouseDown={(e) => {
                    const startX = e.clientX;
                    const startValue = parseInt(solscanSettings.value) || 0;
                    const handleMouseMove = (moveEvent: MouseEvent) => {
                      const diff =
                        Math.floor((moveEvent.clientX - startX) / 5) * 10;
                      const newValue = Math.max(
                        0,
                        Math.min(1000, startValue + diff)
                      );
                      setSolscanSettings({
                        ...solscanSettings,
                        value: String(newValue)
                      });
                    };
                    const handleMouseUp = () => {
                      document.removeEventListener(
                        'mousemove',
                        handleMouseMove
                      );
                      document.removeEventListener('mouseup', handleMouseUp);
                    };
                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                  }}
                  className='h-7 cursor-ew-resize text-center text-xs [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
                  disabled={loadingSolscanSettings}
                />
                <Button
                  variant='outline'
                  size='icon'
                  className='h-7 w-7'
                  onClick={() =>
                    setSolscanSettings({
                      ...solscanSettings,
                      value: String(
                        Math.min(1000, parseInt(solscanSettings.value) + 10)
                      )
                    })
                  }
                  disabled={loadingSolscanSettings}
                >
                  <ChevronRight className='h-3 w-3' />
                </Button>
              </div>
            </div>

            {/* Token Address (SOL) */}
            <div className='space-y-1'>
              <Label className='text-xs'>Token Address (SOL)</Label>
              <Input
                type='text'
                value={solscanSettings.token_address}
                onChange={(e) =>
                  setSolscanSettings({
                    ...solscanSettings,
                    token_address: e.target.value
                  })
                }
                className='h-7 font-mono text-xs'
                disabled={loadingSolscanSettings}
              />
            </div>

            {/* Page Size */}
            <div className='space-y-1'>
              <Label className='text-xs'>Page Size</Label>
              <select
                value={solscanSettings.page_size}
                onChange={(e) =>
                  setSolscanSettings({
                    ...solscanSettings,
                    page_size: e.target.value
                  })
                }
                className='border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-7 w-full rounded-md border px-3 text-xs focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
                disabled={loadingSolscanSettings}
              >
                <option value='10'>10</option>
                <option value='20'>20</option>
                <option value='30'>30</option>
                <option value='40'>40</option>
                <option value='60'>60</option>
                <option value='100'>100</option>
              </select>
            </div>

            {/* Reset to Defaults */}
            <Button
              variant='outline'
              size='sm'
              className='w-full'
              onClick={() => setSolscanSettings(defaultSolscanSettings)}
              disabled={loadingSolscanSettings}
            >
              <RotateCcw className='mr-2 h-3 w-3' />
              Reset to Defaults
            </Button>

            {/* Current Settings JSON */}
            <details className='space-y-2'>
              <summary className='text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium'>
                View JSON
              </summary>
              <pre className='text-muted-foreground bg-muted mt-2 max-h-40 overflow-auto rounded p-3 text-xs'>
                {JSON.stringify(solscanSettings, null, 2)}
              </pre>
            </details>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
