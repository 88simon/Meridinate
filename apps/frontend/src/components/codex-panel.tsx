'use client';

import { useState, useEffect, useCallback } from 'react';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { useStarred } from '@/contexts/starred-context';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { StarButton } from '@/components/star-button';
import {
  Search,
  X,
  Loader2,
  Pencil,
  Wallet,
  Coins
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface StarredItemFull {
  id: number;
  item_type: string;
  item_address: string;
  nametag: string | null;
  starred_at: string;
  token_id?: number | null;
  token_name?: string | null;
  token_symbol?: string | null;
}

interface CodexPanelProps {
  open: boolean;
  onClose: () => void;
}

export function CodexPanel({ open, onClose }: CodexPanelProps) {
  const { openWIR } = useWalletIntelligence();
  const { openTIP } = useTokenIntelligence();
  const { refreshStarred } = useStarred();

  const [wallets, setWallets] = useState<StarredItemFull[]>([]);
  const [tokens, setTokens] = useState<StarredItemFull[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'wallets' | 'tokens'>('wallets');

  // Edit nametag state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editNametag, setEditNametag] = useState('');

  const loadStarred = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/starred`);
      if (res.ok) {
        const data = await res.json();
        setWallets(data.wallets || []);
        setTokens(data.tokens || []);
      }
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (open) loadStarred();
  }, [open, loadStarred]);

  const handleUnstar = async (type: string, address: string) => {
    try {
      await fetch(`${API_BASE_URL}/api/starred?item_type=${type}&item_address=${address}`, { method: 'DELETE' });
      toast.success('Removed from favorites');
      loadStarred();
      refreshStarred();
    } catch {
      toast.error('Failed to remove');
    }
  };

  const handleSaveNametag = async (type: string, address: string) => {
    try {
      await fetch(`${API_BASE_URL}/api/starred/nametag`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_type: type, item_address: address, nametag: editNametag.trim() || null }),
      });
      toast.success('Name updated');
      setEditingId(null);
      setEditNametag('');
      loadStarred();
    } catch {
      toast.error('Failed to update');
    }
  };

  if (!open) return null;

  const query = searchQuery.toLowerCase();
  const filteredWallets = query
    ? wallets.filter(w => w.item_address.toLowerCase().includes(query) || (w.nametag || '').toLowerCase().includes(query))
    : wallets;
  const filteredTokens = query
    ? tokens.filter(t => t.item_address.toLowerCase().includes(query) || (t.nametag || '').toLowerCase().includes(query))
    : tokens;

  const activeItems = activeTab === 'wallets' ? filteredWallets : filteredTokens;

  return (
      <div
        className='flex h-full w-full flex-col border-l bg-background shadow-xl'
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-4 py-3'>
          <div>
            <h2 className='text-sm font-semibold'>Codex — Favorites</h2>
            <p className='text-muted-foreground text-[11px]'>
              {wallets.length} wallets · {tokens.length} tokens starred
            </p>
          </div>
          <Button variant='ghost' size='sm' onClick={onClose} className='h-7 w-7 p-0'>
            <X className='h-4 w-4' />
          </Button>
        </div>

        {/* Search */}
        <div className='px-4 py-2 border-b'>
          <div className='relative'>
            <Search className='absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground' />
            <input
              type='text'
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder='Search favorites...'
              className='bg-background focus:ring-primary h-8 w-full rounded-md border pl-9 pr-8 text-xs focus:outline-none focus:ring-2'
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className='absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground'>
                <X className='h-3 w-3' />
              </button>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className='flex border-b'>
          <button
            onClick={() => setActiveTab('wallets')}
            className={cn('flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium border-b-2 transition-colors',
              activeTab === 'wallets' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            <Wallet className='h-3.5 w-3.5' />
            Wallets ({filteredWallets.length})
          </button>
          <button
            onClick={() => setActiveTab('tokens')}
            className={cn('flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium border-b-2 transition-colors',
              activeTab === 'tokens' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            <Coins className='h-3.5 w-3.5' />
            Tokens ({filteredTokens.length})
          </button>
        </div>

        {/* List */}
        <div className='flex-1 overflow-y-auto px-3 py-2'>
          {loading ? (
            <div className='flex items-center justify-center gap-2 py-8 text-muted-foreground'>
              <Loader2 className='h-4 w-4 animate-spin' /> Loading...
            </div>
          ) : activeItems.length === 0 ? (
            <div className='py-8 text-center text-muted-foreground text-sm'>
              {searchQuery ? 'No matches' : `No starred ${activeTab} yet. Star items from the leaderboard to add them here.`}
            </div>
          ) : (
            <div className='space-y-1'>
              {activeItems.map((item) => (
                <div
                  key={item.id}
                  className='group rounded-lg border p-2 hover:bg-muted/50 transition-colors'
                >
                  {editingId === item.id ? (
                    <div className='space-y-2'>
                      <input
                        type='text'
                        value={editNametag}
                        onChange={(e) => setEditNametag(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveNametag(item.item_type, item.item_address);
                          if (e.key === 'Escape') { setEditingId(null); setEditNametag(''); }
                        }}
                        placeholder='Display name...'
                        className='bg-background h-7 w-full rounded border px-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary'
                        autoFocus
                      />
                      <div className='flex gap-1'>
                        <Button size='sm' className='h-6 text-[10px] flex-1' onClick={() => handleSaveNametag(item.item_type, item.item_address)}>Save</Button>
                        <Button variant='outline' size='sm' className='h-6 text-[10px] flex-1' onClick={() => { setEditingId(null); setEditNametag(''); }}>Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {(item.nametag || (item.item_type === 'token' && item.token_name)) && (
                        <div className='text-sm font-semibold mb-0.5'>
                          {item.nametag || item.token_name}
                          {item.token_symbol && !item.nametag && (
                            <span className='text-muted-foreground text-xs font-normal ml-1'>({item.token_symbol})</span>
                          )}
                        </div>
                      )}
                      <div className='flex items-center justify-between gap-2'>
                        <code
                          className='font-mono text-[11px] cursor-pointer hover:text-blue-400 transition-colors break-all flex-1'
                          onClick={() => {
                            if (item.item_type === 'wallet') openWIR(item.item_address);
                            if (item.item_type === 'token' && item.token_id) openTIP({ id: item.token_id });
                          }}
                        >
                          {item.item_address}
                        </code>
                        <div className='flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity'>
                          <button
                            onClick={() => { setEditingId(item.id); setEditNametag(item.nametag || ''); }}
                            className='text-muted-foreground hover:text-foreground p-0.5' title='Edit name'
                          >
                            <Pencil className='h-3 w-3' />
                          </button>
                          <StarButton type={item.item_type as 'wallet' | 'token'} address={item.item_address} size='sm' />
                        </div>
                      </div>
                      <div className='flex items-center gap-2 mt-1 text-[10px] text-muted-foreground'>
                        <span>{item.item_type === 'wallet' ? '🔑' : '🪙'} {item.item_type}</span>
                        <span>· starred {new Date(item.starred_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className='text-muted-foreground border-t px-4 py-2 text-[11px]'>
          {activeItems.length} {activeTab} · Star items from leaderboards or intelligence reports
        </div>
      </div>
  );
}
