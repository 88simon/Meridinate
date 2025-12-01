'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react';
import { InfoTooltip } from './InfoTooltip';

interface NumericStepperProps {
  label: string;
  value: number;
  onChange: (val: number) => void;
  onReset?: () => void;
  min: number;
  max?: number;
  step: number;
  tooltip?: string;
  bypassLimits?: boolean;
}

export function NumericStepper({
  label,
  value,
  onChange,
  onReset,
  min,
  max,
  step,
  tooltip,
  bypassLimits = false
}: NumericStepperProps) {
  // When bypassLimits is true, only enforce min >= 0
  const effectiveMin = bypassLimits ? 0 : min;
  const effectiveMax = bypassLimits ? undefined : max;

  return (
    <div className='space-y-1'>
      <Label className='flex items-center text-xs'>
        {label}
        {tooltip && <InfoTooltip>{tooltip}</InfoTooltip>}
      </Label>
      <div className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='icon'
          className='h-7 w-7'
          onClick={() => onChange(Math.max(effectiveMin, value - step))}
        >
          <ChevronLeft className='h-3 w-3' />
        </Button>
        <Input
          type='number'
          value={value}
          onChange={(e) => {
            const v = parseInt(e.target.value) || effectiveMin;
            onChange(
              effectiveMax
                ? Math.min(effectiveMax, Math.max(effectiveMin, v))
                : Math.max(effectiveMin, v)
            );
          }}
          className='h-7 text-center text-xs [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
        />
        <Button
          variant='outline'
          size='icon'
          className='h-7 w-7'
          onClick={() =>
            onChange(
              effectiveMax ? Math.min(effectiveMax, value + step) : value + step
            )
          }
        >
          <ChevronRight className='h-3 w-3' />
        </Button>
        {onReset && (
          <Button
            variant='ghost'
            size='icon'
            className='h-7 w-7'
            onClick={onReset}
            title='Reset to default'
          >
            <RotateCcw className='h-3 w-3' />
          </Button>
        )}
      </div>
    </div>
  );
}
