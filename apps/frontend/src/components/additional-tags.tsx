'use client';

import { useState } from 'react';
import { addWalletTag, removeWalletTag } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Tags } from 'lucide-react';
import { toast } from 'sonner';
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '@/components/ui/popover';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { useWalletTags } from '@/contexts/WalletTagsContext';
import { MANUAL_WALLET_TAGS } from '@/lib/wallet-tags';

interface AdditionalTagsPopoverProps {
  walletId?: number;
  walletAddress: string;
  compact?: boolean;
}

export function AdditionalTagsPopover({
  walletId,
  walletAddress,
  compact = false
}: AdditionalTagsPopoverProps) {
  const { tags: allTags } = useWalletTags(walletAddress);
  const [loading, setLoading] = useState(false);

  // Extract manual tags (tier 3) from context
  const activeTags = new Set(
    allTags
      .filter((t) =>
        (MANUAL_WALLET_TAGS as readonly string[]).includes(t.tag)
      )
      .map((t) => t.tag)
  );

  const toggleTag = async (tag: string) => {
    setLoading(true);
    try {
      if (activeTags.has(tag)) {
        await removeWalletTag(walletAddress, tag);
        toast.success(`Removed ${tag} tag`);
      } else {
        await addWalletTag(walletAddress, tag, false);
        toast.success(`Added ${tag} tag`);
      }
      window.dispatchEvent(
        new CustomEvent('walletTagsChanged', { detail: { walletAddress } })
      );
    } catch (error: any) {
      toast.error(error.message || `Failed to update ${tag} tag`);
    } finally {
      setLoading(false);
    }
  };

  const iconClass = compact ? 'h-3 w-3' : 'h-4 w-4';
  const uniqueId = walletId ? `${walletId}` : walletAddress.slice(0, 8);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant='outline'
          size='sm'
          className={compact ? 'h-6 w-6 p-0' : ''}
          onClick={(e) => e.stopPropagation()}
        >
          <Tags className={iconClass} />
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-48' onClick={(e) => e.stopPropagation()}>
        <div className='space-y-3'>
          <h4 className='text-sm font-semibold'>Manual Tags</h4>
          <div className='space-y-2'>
            {MANUAL_WALLET_TAGS.map((tag) => (
              <div key={tag} className='flex items-center space-x-2'>
                <Checkbox
                  id={`${tag}-${uniqueId}`}
                  checked={activeTags.has(tag)}
                  onCheckedChange={() => toggleTag(tag)}
                  disabled={loading}
                />
                <Label
                  htmlFor={`${tag}-${uniqueId}`}
                  className='cursor-pointer text-sm'
                >
                  {tag}
                </Label>
              </div>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** @deprecated Bot indicator removed — replaced by tier-based auto-tags */
export function WalletAddressWithBotIndicator({
  children
}: {
  walletAddress: string;
  children: React.ReactNode;
  onTagsChange?: () => void;
}) {
  return <>{children}</>;
}
