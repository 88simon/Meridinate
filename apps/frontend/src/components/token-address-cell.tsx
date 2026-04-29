'use client';

import { Copy, Twitter } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface TokenAddressCellProps {
  address: string;
  compact?: boolean;
  showTwitter?: boolean;
}

export function TokenAddressCell({
  address,
  compact = false,
  showTwitter = true
}: TokenAddressCellProps) {
  const iconSize = compact ? 'h-2.5 w-2.5' : 'h-3 w-3';
  const btnSize = compact ? 'h-5 w-5' : 'h-6 w-6';

  return (
    <div className='flex items-center gap-1'>
      <span
        className={cn(
          'text-muted-foreground font-mono break-all',
          compact ? 'text-[9px]' : 'text-[10px]'
        )}
      >
        {address}
      </span>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <a
              href={`https://gmgn.ai/sol/token/${address}?isInputValue=true`}
              target='_blank'
              rel='noopener noreferrer'
              className='shrink-0 opacity-70 hover:opacity-100 transition-opacity'
              onClick={(e) => e.stopPropagation()}
            >
              <img src='/gmgn-logo.png' alt='GMGN' className={cn(compact ? 'h-3.5 w-3.5' : 'h-4 w-4')} />
            </a>
          </TooltipTrigger>
          <TooltipContent>View on GMGN.ai</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {showTwitter && (
        <a
          href={`https://twitter.com/search?q=${encodeURIComponent(address)}`}
          target='_blank'
          rel='noopener noreferrer'
          onClick={(e) => e.stopPropagation()}
        >
          <Button
            variant='ghost'
            size='sm'
            className={cn('shrink-0 p-0', btnSize)}
          >
            <Twitter className={cn(iconSize)} />
          </Button>
        </a>
      )}
      <Button
        variant='ghost'
        size='sm'
        className={cn('shrink-0 p-0', btnSize)}
        onClick={(e) => {
          e.stopPropagation();
          navigator.clipboard.writeText(address);
          toast.success('Address copied to clipboard');
        }}
      >
        <Copy className={cn(iconSize)} />
      </Button>
    </div>
  );
}
