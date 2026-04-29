'use client';

import { useWalletTags } from '@/contexts/WalletTagsContext';
import { getTagStyle, getTagTier } from '@/lib/wallet-tags';

const CLICKABLE_TAGS = new Set([
  'Deployer',
  'Serial Deployer',
  'Winning Deployer',
  'Rug Deployer',
  'High-Value Deployer',
  'Cluster',
]);

interface WalletTagLabelsProps {
  walletAddress: string;
  onTagClick?: (tag: string, walletAddress: string) => void;
}

export function WalletTagLabels({ walletAddress, onTagClick }: WalletTagLabelsProps) {
  const { tags } = useWalletTags(walletAddress);

  if (tags.length === 0) {
    return null;
  }

  return (
    <div className='mt-1 flex flex-wrap gap-1'>
      {tags.map((tagObj) => {
        const style = getTagStyle(tagObj.tag);
        const tier = getTagTier(tagObj.tag);
        const isClickable = onTagClick && CLICKABLE_TAGS.has(tagObj.tag);
        return (
          <span
            key={tagObj.tag}
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${style.bg} ${style.text} ${tier < 3 ? '' : 'border border-current/20'} ${isClickable ? 'cursor-pointer hover:opacity-80' : ''}`}
            onClick={
              isClickable
                ? (e) => {
                    e.stopPropagation();
                    onTagClick(tagObj.tag, walletAddress);
                  }
                : undefined
            }
          >
            {tagObj.tag}
          </span>
        );
      })}
    </div>
  );
}
