'use client';

import React from 'react';
import { useStarred } from '@/contexts/starred-context';
import { Star } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StarButtonProps {
  type: 'wallet' | 'token';
  address: string;
  className?: string;
  size?: 'sm' | 'md';
}

export const StarButton = React.memo(function StarButton({ type, address, className, size = 'sm' }: StarButtonProps) {
  const { isStarred, toggleStar } = useStarred();
  const starred = isStarred(type, address);

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        toggleStar(type, address);
      }}
      title={starred ? 'Remove from favorites' : 'Add to favorites'}
      className={cn(
        'transition-all duration-150 shrink-0',
        starred
          ? 'text-yellow-400 hover:text-yellow-300'
          : 'text-muted-foreground/30 hover:text-yellow-400/60',
        size === 'sm' ? 'p-0.5' : 'p-1',
        className,
      )}
    >
      <Star
        className={cn(
          size === 'sm' ? 'h-3 w-3' : 'h-4 w-4',
          starred && 'fill-yellow-400',
        )}
      />
    </button>
  );
});
