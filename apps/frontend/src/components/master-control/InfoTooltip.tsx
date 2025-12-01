'use client';

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { Info } from 'lucide-react';

interface InfoTooltipProps {
  children: React.ReactNode;
}

export function InfoTooltip({ children }: InfoTooltipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className='text-muted-foreground ml-1 inline h-3 w-3 cursor-help' />
      </TooltipTrigger>
      <TooltipContent side='right' className='max-w-[250px] text-xs'>
        {children}
      </TooltipContent>
    </Tooltip>
  );
}
