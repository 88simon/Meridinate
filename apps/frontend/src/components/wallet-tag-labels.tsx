'use client';

import { useWalletTags } from '@/contexts/WalletTagsContext';

interface WalletTagLabelsProps {
  walletAddress: string;
}

export function WalletTagLabels({ walletAddress }: WalletTagLabelsProps) {
  const { tags } = useWalletTags(walletAddress);

  if (tags.length === 0) {
    return null;
  }

  const getTagStyle = (tagName: string) => {
    const lowerTag = tagName.toLowerCase();

    // Bot tag - blue/purple theme
    if (lowerTag === 'bot') {
      return 'bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30';
    }

    // Whale tag - cyan theme
    if (lowerTag === 'whale') {
      return 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-400 border-cyan-500/30';
    }

    // Insider tag - purple theme
    if (lowerTag === 'insider') {
      return 'bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30';
    }

    // Gunslinger tag - orange theme
    if (lowerTag === 'gunslinger') {
      return 'bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30';
    }

    // Gambler tag - red theme
    if (lowerTag === 'gambler') {
      return 'bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30';
    }

    // Smart label - green/emerald theme with emphasis
    if (lowerTag === 'smart') {
      return 'bg-emerald-500/30 text-emerald-700 dark:text-emerald-300 border-emerald-500/50 font-bold';
    }

    // Dumb label - red/rose theme with emphasis
    if (lowerTag === 'dumb') {
      return 'bg-rose-500/30 text-rose-700 dark:text-rose-300 border-rose-500/50 font-bold';
    }

    // Nationality tags - green theme
    const nationalityCodes = [
      'US',
      'CN',
      'KR',
      'JP',
      'EU',
      'UK',
      'SG',
      'IN',
      'RU',
      'BR',
      'CA',
      'AU'
    ];
    if (nationalityCodes.includes(tagName.toUpperCase())) {
      return 'bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30';
    }

    // KOL tags - amber/gold theme
    const tagObj = tags.find((t) => t.tag === tagName);
    if (tagObj?.is_kol) {
      return 'bg-amber-500/20 text-amber-700 dark:text-amber-400 border-amber-500/30 font-semibold';
    }

    // Default tags - primary theme
    return 'bg-primary/10 text-primary border-primary/20';
  };

  return (
    <div className='mt-1 flex flex-wrap gap-1'>
      {tags.map((tagObj) => (
        <span
          key={tagObj.tag}
          className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${getTagStyle(tagObj.tag)}`}
        >
          {tagObj.is_kol && '★ '}
          {tagObj.tag}
        </span>
      ))}
    </div>
  );
}
