'use client';

import { NumericStepper } from './NumericStepper';
import { InfoTooltip } from './InfoTooltip';
import { ApiSettings } from './types';

interface IntelTabProps {
  apiSettings: ApiSettings;
  setApiSettings: (s: ApiSettings) => void;
}

const MODEL_OPTIONS = [
  { value: 'claude-opus-4-6-20250414', label: 'Opus 4.6 (most capable, highest cost)' },
  { value: 'claude-sonnet-4-20250514', label: 'Sonnet 4 (balanced)' },
  { value: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5 (fastest, cheapest)' },
];

export function IntelTab({ apiSettings, setApiSettings }: IntelTabProps) {
  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-sm font-semibold mb-1'>Intel Agent Configuration</h3>
        <p className='text-xs text-muted-foreground'>
          Controls for Housekeeper and Investigator agents. Changes apply to the next Intel run.
        </p>
      </div>

      {/* Model Selection */}
      <div className='space-y-2'>
        <div className='flex items-center gap-2'>
          <label className='text-xs font-medium'>Agent Model</label>
          <InfoTooltip>The Claude model used for both Housekeeper and Investigator. Sonnet is more capable but slower and more expensive. Haiku is faster and cheaper but less thorough.</InfoTooltip>
        </div>
        <select
          value={apiSettings.intelModel || 'claude-sonnet-4-20250514'}
          onChange={(e) => setApiSettings({ ...apiSettings, intelModel: e.target.value })}
          className='w-full rounded-md border bg-background px-3 py-2 text-xs'
        >
          {MODEL_OPTIONS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>

      {/* Investigator Max Tokens */}
      <div className='space-y-2'>
        <div className='flex items-center gap-2'>
          <label className='text-xs font-medium'>Investigator Max Output Tokens</label>
          <InfoTooltip>Maximum output tokens for the Investigator. Higher means longer reports, fewer truncations. Forensics with 10 wallets needs 6000+. Default: 8192.</InfoTooltip>
        </div>
        <NumericStepper
          label='Investigator Max Tokens'
          value={apiSettings.intelMaxTokens ?? 8192}
          onChange={(v) => setApiSettings({ ...apiSettings, intelMaxTokens: v })}
          min={2048}
          max={16384}
          step={1024}
        />
        <p className='text-[10px] text-muted-foreground'>
          Range: 2,048 - 16,384. If reports are getting truncated, increase this.
        </p>
      </div>

      {/* Housekeeper Max Tokens */}
      <div className='space-y-2'>
        <div className='flex items-center gap-2'>
          <label className='text-xs font-medium'>Housekeeper Max Output Tokens</label>
          <InfoTooltip>Maximum output tokens for the Housekeeper. Typically needs less than the Investigator. Default: 8192.</InfoTooltip>
        </div>
        <NumericStepper
          label='Housekeeper Max Tokens'
          value={apiSettings.intelHousekeeperMaxTokens ?? 8192}
          onChange={(v) => setApiSettings({ ...apiSettings, intelHousekeeperMaxTokens: v })}
          min={2048}
          max={16384}
          step={1024}
        />
      </div>

      {/* Forensics Wallet Count */}
      <div className='space-y-2'>
        <div className='flex items-center gap-2'>
          <label className='text-xs font-medium'>Forensics: Wallets to Analyze</label>
          <InfoTooltip>How many top-PnL wallets to analyze in Forensics mode. More wallets = more thorough but slower. Default: 10.</InfoTooltip>
        </div>
        <NumericStepper
          label='Forensics Wallet Count'
          value={apiSettings.intelForensicsWalletCount ?? 10}
          onChange={(v) => setApiSettings({ ...apiSettings, intelForensicsWalletCount: v })}
          min={3}
          max={25}
          step={1}
        />
        <p className='text-[10px] text-muted-foreground'>
          Each wallet adds ~500-800 tokens of context. 10 wallets is a good balance.
        </p>
      </div>

      {/* Cost estimate */}
      <div className='rounded-lg border border-muted bg-muted/20 p-3 space-y-1'>
        <h4 className='text-xs font-medium'>Estimated Cost per Run</h4>
        <p className='text-[10px] text-muted-foreground'>
          Full Scan: ~$0.30-0.50 (Sonnet) / ~$0.05-0.10 (Haiku)
        </p>
        <p className='text-[10px] text-muted-foreground'>
          Forensics: ~$0.15-0.30 (Sonnet) / ~$0.03-0.06 (Haiku)
        </p>
        <p className='text-[10px] text-muted-foreground'>
          Costs scale with output tokens and tool calls. Housekeeper uses a separate API key.
        </p>
      </div>
    </div>
  );
}
