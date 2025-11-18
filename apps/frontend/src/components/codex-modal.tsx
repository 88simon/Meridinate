'use client';

import { useState, useEffect } from 'react';
import { getCodexWallets, CodexWallet } from '@/lib/api';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet';
import { Input } from '@/components/ui/input';
import { Search, Tag } from 'lucide-react';
import { toast } from 'sonner';

interface CodexModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CodexModal({ open, onOpenChange }: CodexModalProps) {
  const [wallets, setWallets] = useState<CodexWallet[]>([]);
  const [filteredWallets, setFilteredWallets] = useState<CodexWallet[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      loadWallets();
    }
  }, [open]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredWallets(wallets);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = wallets.filter((wallet) => {
      const addressMatch = wallet.wallet_address.toLowerCase().includes(query);
      const tagMatch = wallet.tags.some((tag) =>
        tag.tag.toLowerCase().includes(query)
      );
      return addressMatch || tagMatch;
    });
    setFilteredWallets(filtered);
  }, [searchQuery, wallets]);

  const loadWallets = async () => {
    setLoading(true);
    try {
      const data = await getCodexWallets();
      setWallets(data.wallets);
      setFilteredWallets(data.wallets);
    } catch (error: any) {
      toast.error(error.message || 'Failed to load Codex');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} modal={false}>
      <SheetContent
        side='right'
        className='flex w-[600px] flex-col border-l sm:w-[700px]'
      >
        <SheetHeader>
          <SheetTitle>Codex</SheetTitle>
          <SheetDescription>
            View all tagged wallets. Click to copy address.
          </SheetDescription>
        </SheetHeader>

        <div className='relative mt-4 mb-4'>
          <Search className='text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 transform' />
          <Input
            placeholder='Search by wallet address or tag...'
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className='pl-10'
          />
        </div>

        <div className='flex-1 space-y-2 overflow-y-auto pr-2'>
          {loading ? (
            <div className='text-muted-foreground py-8 text-center'>
              Loading...
            </div>
          ) : filteredWallets.length === 0 ? (
            <div className='text-muted-foreground py-8 text-center'>
              {searchQuery
                ? 'No wallets match your search'
                : 'No tagged wallets found'}
            </div>
          ) : (
            filteredWallets.map((wallet) => (
              <div
                key={wallet.wallet_address}
                className='hover:bg-muted/50 cursor-pointer rounded-lg border p-3 transition-colors'
                onClick={() => copyToClipboard(wallet.wallet_address)}
              >
                <div className='mb-2 font-mono text-sm break-all'>
                  {wallet.wallet_address}
                </div>
                <div className='flex flex-wrap items-center gap-1'>
                  {wallet.tags.map((tagObj) => (
                    <span
                      key={tagObj.tag}
                      className={`flex items-center gap-1 rounded px-2 py-0.5 text-xs ${
                        tagObj.is_kol
                          ? 'bg-amber-500/20 font-semibold text-amber-700 dark:text-amber-400'
                          : 'bg-primary/10 text-primary'
                      }`}
                    >
                      <Tag className='h-3 w-3' />
                      {tagObj.is_kol && '★ '}
                      {tagObj.tag}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        <div className='text-muted-foreground mt-2 border-t pt-2 text-sm'>
          Showing {filteredWallets.length} of {wallets.length} wallets
        </div>
      </SheetContent>
    </Sheet>
  );
}
