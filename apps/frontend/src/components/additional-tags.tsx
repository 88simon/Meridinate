'use client';

import { useState, useEffect } from 'react';
import { getWalletTags, addWalletTag, removeWalletTag } from '@/lib/api';
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

interface AdditionalTagsPopoverProps {
  walletId?: number;
  walletAddress: string;
  compact?: boolean;
}

const NATIONALITY_OPTIONS = [
  { value: '', label: 'Select...' },
  { value: 'US', label: 'United States (US)' },
  { value: 'CN', label: 'China (CN)' },
  { value: 'KR', label: 'South Korea (KR)' },
  { value: 'JP', label: 'Japan (JP)' },
  { value: 'EU', label: 'European Union (EU)' },
  { value: 'UK', label: 'United Kingdom (UK)' },
  { value: 'SG', label: 'Singapore (SG)' },
  { value: 'IN', label: 'India (IN)' },
  { value: 'RU', label: 'Russia (RU)' },
  { value: 'BR', label: 'Brazil (BR)' },
  { value: 'CA', label: 'Canada (CA)' },
  { value: 'AU', label: 'Australia (AU)' }
];

export function AdditionalTagsPopover({
  walletId,
  walletAddress,
  compact = false
}: AdditionalTagsPopoverProps) {
  const { tags: allTags } = useWalletTags(walletAddress);
  const [loading, setLoading] = useState(false);

  // Extract only additional tags (bot, whale, insider) from context
  const tags = new Set(
    allTags
      .filter((t) => ['bot', 'whale', 'insider'].includes(t.tag.toLowerCase()))
      .map((t) => t.tag.toLowerCase())
  );

  // Find current nationality tag (if any)
  const currentNationality =
    allTags.find((t) =>
      NATIONALITY_OPTIONS.some(
        (n) => n.value && n.value === t.tag.toUpperCase()
      )
    )?.tag.toUpperCase() || '';

  const toggleTag = async (tag: string) => {
    setLoading(true);
    try {
      const tagLower = tag.toLowerCase();
      if (tags.has(tagLower)) {
        await removeWalletTag(walletAddress, tag);
        toast.success(`Removed ${tag} tag`);
      } else {
        await addWalletTag(walletAddress, tag, false);
        toast.success(`Added ${tag} tag`);
      }
      // Trigger a custom event to notify the context to refresh
      window.dispatchEvent(
        new CustomEvent('walletTagsChanged', { detail: { walletAddress } })
      );
    } catch (error: any) {
      toast.error(error.message || `Failed to update ${tag} tag`);
    } finally {
      setLoading(false);
    }
  };

  const handleNationalityChange = async (
    e: React.ChangeEvent<HTMLSelectElement>
  ) => {
    const newNationality = e.target.value;
    setLoading(true);
    try {
      // Remove old nationality tag if exists
      if (currentNationality) {
        await removeWalletTag(walletAddress, currentNationality);
      }
      // Add new nationality tag if selected
      if (newNationality) {
        await addWalletTag(walletAddress, newNationality, false);
        toast.success(`Set nationality to ${newNationality}`);
      } else {
        toast.success('Removed nationality tag');
      }
      // Trigger refresh
      window.dispatchEvent(
        new CustomEvent('walletTagsChanged', { detail: { walletAddress } })
      );
    } catch (error: any) {
      toast.error(error.message || 'Failed to update nationality tag');
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
      <PopoverContent className='w-56' onClick={(e) => e.stopPropagation()}>
        <div className='space-y-3'>
          <h4 className='text-sm font-semibold'>Additional Tags</h4>
          <div className='space-y-2'>
            <div className='flex items-center space-x-2'>
              <Checkbox
                id={`bot-${uniqueId}`}
                checked={tags.has('bot')}
                onCheckedChange={() => toggleTag('Bot')}
                disabled={loading}
              />
              <Label
                htmlFor={`bot-${uniqueId}`}
                className='cursor-pointer text-sm'
              >
                Bot
              </Label>
            </div>
            <div className='flex items-center space-x-2'>
              <Checkbox
                id={`whale-${uniqueId}`}
                checked={tags.has('whale')}
                onCheckedChange={() => toggleTag('Whale')}
                disabled={loading}
              />
              <Label
                htmlFor={`whale-${uniqueId}`}
                className='cursor-pointer text-sm'
              >
                Whale
              </Label>
            </div>
            <div className='flex items-center space-x-2'>
              <Checkbox
                id={`insider-${uniqueId}`}
                checked={tags.has('insider')}
                onCheckedChange={() => toggleTag('Insider')}
                disabled={loading}
              />
              <Label
                htmlFor={`insider-${uniqueId}`}
                className='cursor-pointer text-sm'
              >
                Insider
              </Label>
            </div>
          </div>

          {/* Nationality Dropdown */}
          <div className='space-y-1.5 border-t pt-3'>
            <Label htmlFor={`nationality-${uniqueId}`} className='text-sm'>
              Nationality
            </Label>
            <select
              id={`nationality-${uniqueId}`}
              value={currentNationality}
              onChange={handleNationalityChange}
              onClick={(e) => e.stopPropagation()}
              disabled={loading}
              className='border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-8 w-full rounded-md border px-3 text-xs focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
            >
              {NATIONALITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// Hook to check if a wallet has specific additional tags
export function useWalletBotTag(walletAddress: string) {
  const [isBot, setIsBot] = useState(false);

  const checkBotTag = async () => {
    try {
      const walletTags = await getWalletTags(walletAddress);
      const hasBot = walletTags.some((t) => t.tag.toLowerCase() === 'bot');
      setIsBot(hasBot);
    } catch (error) {}
  };

  useEffect(() => {
    checkBotTag();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walletAddress]);

  return isBot;
}

// Component to display wallet address with bot emoji if tagged
export function WalletAddressWithBotIndicator({
  walletAddress,
  children
}: {
  walletAddress: string;
  children: React.ReactNode;
  onTagsChange?: () => void;
}) {
  const { tags } = useWalletTags(walletAddress);
  const isBot = tags.some((t) => t.tag.toLowerCase() === 'bot');

  return (
    <>
      {isBot && <span className='mr-1'>🤖</span>}
      {children}
    </>
  );
}
