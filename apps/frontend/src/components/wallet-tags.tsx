'use client';

import { useState, useEffect, useRef } from 'react';
import { addWalletTag, removeWalletTag } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { X, Plus, Tag } from 'lucide-react';
import { toast } from 'sonner';
import { useWalletTags } from '@/contexts/WalletTagsContext';
import { ADDITIONAL_TAGS } from '@/lib/wallet-tags';

interface WalletTagsProps {
  walletAddress: string;
  compact?: boolean;
  iconOnly?: boolean;
}

type InputStep = 'tag' | 'kol';

export function WalletTags({
  walletAddress,
  compact = false,
  iconOnly = false
}: WalletTagsProps) {
  const { tags: contextTags } = useWalletTags(walletAddress);
  // Filter out additional tags and nationality tags - those are managed by AdditionalTagsPopover and display under wallet address
  const nationalityTags = [
    'us',
    'cn',
    'kr',
    'jp',
    'eu',
    'uk',
    'sg',
    'in',
    'ru',
    'br',
    'ca',
    'au'
  ];
  const tags = contextTags.filter(
    (t) =>
      !ADDITIONAL_TAGS.includes(t.tag.toLowerCase() as any) &&
      !nationalityTags.includes(t.tag.toLowerCase())
  );
  const [newTag, setNewTag] = useState('');
  const [kolValue, setKolValue] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [showInput, setShowInput] = useState(false);
  const [inputStep, setInputStep] = useState<InputStep>('tag');
  const inputRef = useRef<HTMLDivElement>(null);
  const kolToggleRef = useRef<HTMLDivElement>(null);

  // Auto-focus the KOL toggle when it appears
  useEffect(() => {
    if (inputStep === 'kol' && kolToggleRef.current) {
      kolToggleRef.current.focus();
    }
  }, [inputStep]);

  // Close input when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setShowInput(false);
        setNewTag('');
        setKolValue(false);
        setInputStep('tag');
      }
    };

    if (showInput) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showInput]);

  const handleTagNameSubmit = () => {
    if (!newTag.trim()) return;
    // Move to KOL step and default to Y (true)
    setKolValue(true);
    setInputStep('kol');
  };

  const handleKolSubmit = async () => {
    setLoading(true);
    try {
      await addWalletTag(walletAddress, newTag.trim(), kolValue);
      setNewTag('');
      setKolValue(false);
      setInputStep('tag');
      setShowInput(false);
      toast.success('Tag added');
      // Trigger event to refresh context
      window.dispatchEvent(
        new CustomEvent('walletTagsChanged', { detail: { walletAddress } })
      );
    } catch (error: any) {
      toast.error(error.message || 'Failed to add tag');
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveTag = async (tagName: string) => {
    setLoading(true);
    try {
      await removeWalletTag(walletAddress, tagName);
      toast.success('Tag removed');
      // Trigger event to refresh context
      window.dispatchEvent(
        new CustomEvent('walletTagsChanged', { detail: { walletAddress } })
      );
    } catch (error: any) {
      toast.error(error.message || 'Failed to remove tag');
    } finally {
      setLoading(false);
    }
  };

  if (compact) {
    return (
      <div className='flex flex-wrap items-center gap-1'>
        {tags.map((tagObj) => (
          <span
            key={tagObj.tag}
            className={`rounded px-2 py-0.5 text-xs ${
              tagObj.is_kol
                ? 'bg-amber-500/20 font-semibold text-amber-700 dark:text-amber-400'
                : 'bg-primary/10 text-primary'
            }`}
          >
            {tagObj.is_kol && '★ '}
            {tagObj.tag}
          </span>
        ))}
        {tags.length === 0 && (
          <span className='text-muted-foreground text-xs'>No tags</span>
        )}
      </div>
    );
  }

  return (
    <div className='flex flex-wrap items-center gap-1'>
      {/* Show existing tags with remove buttons (skip if iconOnly mode) */}
      {!showInput &&
        !iconOnly &&
        tags.map((tagObj) => (
          <div
            key={tagObj.tag}
            className='bg-muted flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs'
          >
            <span className='text-xs'>
              {tagObj.is_kol && '★ '}
              {tagObj.tag}
            </span>
            <Button
              variant='ghost'
              size='sm'
              className='h-3 w-3 p-0 hover:bg-transparent'
              onClick={(e) => {
                e.stopPropagation();
                handleRemoveTag(tagObj.tag);
              }}
              disabled={loading}
            >
              <X className='h-2.5 w-2.5' />
            </Button>
          </div>
        ))}

      {showInput ? (
        <div ref={inputRef} className='flex items-center gap-1'>
          {inputStep === 'tag' ? (
            <>
              <Input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleTagNameSubmit();
                  if (e.key === 'Escape') {
                    setShowInput(false);
                    setNewTag('');
                  }
                }}
                placeholder='Tag name'
                className='h-6 w-24 text-xs'
                autoFocus
                disabled={loading}
              />
              <Button
                variant='ghost'
                size='sm'
                className='h-6 w-6 p-0'
                onClick={handleTagNameSubmit}
                disabled={loading}
              >
                <Plus className='h-3 w-3' />
              </Button>
            </>
          ) : (
            <>
              <div
                ref={kolToggleRef}
                className='border-input bg-background flex h-6 items-center gap-1 rounded border px-2'
                onKeyDown={async (e) => {
                  if (e.key === 'Enter') {
                    handleKolSubmit();
                  } else if (e.key === 'Escape') {
                    setShowInput(false);
                    setNewTag('');
                    setKolValue(false);
                    setInputStep('tag');
                  } else if (e.key === 'y' || e.key === 'Y') {
                    setLoading(true);
                    try {
                      await addWalletTag(walletAddress, newTag.trim(), true);
                      setNewTag('');
                      setKolValue(false);
                      setInputStep('tag');
                      setShowInput(false);
                      toast.success('Tag added');
                      // Trigger event to refresh context
                      window.dispatchEvent(
                        new CustomEvent('walletTagsChanged', {
                          detail: { walletAddress }
                        })
                      );
                    } catch (error: any) {
                      toast.error(error.message || 'Failed to add tag');
                    } finally {
                      setLoading(false);
                    }
                  } else if (e.key === 'n' || e.key === 'N') {
                    setLoading(true);
                    try {
                      await addWalletTag(walletAddress, newTag.trim(), false);
                      setNewTag('');
                      setKolValue(false);
                      setInputStep('tag');
                      setShowInput(false);
                      toast.success('Tag added');
                      // Trigger event to refresh context
                      window.dispatchEvent(
                        new CustomEvent('walletTagsChanged', {
                          detail: { walletAddress }
                        })
                      );
                    } catch (error: any) {
                      toast.error(error.message || 'Failed to add tag');
                    } finally {
                      setLoading(false);
                    }
                  } else if (e.key === 'ArrowLeft') {
                    setKolValue(true);
                  } else if (e.key === 'ArrowRight') {
                    setKolValue(false);
                  }
                }}
                tabIndex={0}
              >
                <span className='text-muted-foreground text-xs'>KOL?</span>
                <button
                  type='button'
                  className={`rounded px-2 py-0.5 text-xs transition-colors ${
                    kolValue
                      ? 'bg-green-500/20 font-semibold text-green-700 dark:text-green-400'
                      : 'text-muted-foreground hover:bg-muted'
                  }`}
                  onClick={() => setKolValue(true)}
                  disabled={loading}
                >
                  Y
                </button>
                <button
                  type='button'
                  className={`rounded px-2 py-0.5 text-xs transition-colors ${
                    !kolValue
                      ? 'bg-red-500/20 font-semibold text-red-700 dark:text-red-400'
                      : 'text-muted-foreground hover:bg-muted'
                  }`}
                  onClick={() => setKolValue(false)}
                  disabled={loading}
                >
                  N
                </button>
              </div>
              <Button
                variant='ghost'
                size='sm'
                className='h-6 w-6 p-0'
                onClick={handleKolSubmit}
                disabled={loading}
              >
                <Plus className='h-3 w-3' />
              </Button>
            </>
          )}
        </div>
      ) : (
        <Button
          variant='ghost'
          size='sm'
          className='h-6 w-6 p-0'
          onClick={() => setShowInput(true)}
          title='Add tag'
        >
          <Tag className='h-3.5 w-3.5' />
        </Button>
      )}
    </div>
  );
}
