'use client';

import { useState, useEffect, useCallback } from 'react';
import { useWalletIntelligence } from '@/contexts/wallet-intelligence-context';
import { useTokenIntelligence } from '@/contexts/token-intelligence-context';
import { useWalletNametags } from '@/contexts/wallet-nametags-context';
import { API_BASE_URL } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { StarButton } from '@/components/star-button';
import {
  Search,
  X,
  Loader2,
  Pencil,
  Wallet,
  Coins,
  Shield,
  ShieldAlert,
  Radio,
  Eye,
  Star
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

// Returned by /api/codex/by-category. Used for the non-starred wallet category views.
interface CategorizedWallet {
  wallet_address: string;
  nametag: string | null;
  added_at: string;
}

type WalletCategory = 'starred' | 'allowlist' | 'denylist' | 'shadowing' | 'watching';

const CATEGORY_META: Record<WalletCategory, { label: string; icon: typeof Star; color: string; description: string }> = {
  starred:    { label: 'Starred',    icon: Star,        color: 'text-yellow-400', description: 'Manually favorited' },
  allowlist:  { label: 'Allowlist',  icon: Shield,      color: 'text-green-400',  description: 'Trusted as anti-rug confluence (auto-shadowed)' },
  denylist:   { label: 'Denylist',   icon: ShieldAlert, color: 'text-red-400',    description: 'Filtered out of positive confluence' },
  shadowing:  { label: 'Shadowing',  icon: Radio,       color: 'text-emerald-400',description: 'Live tracked via Wallet Shadow' },
  watching:   { label: 'Watchlist',  icon: Eye,         color: 'text-blue-400',   description: 'Pending classification — manual review' },
};

interface CodexPanelProps {
  open: boolean;
  onClose: () => void;
}

export function CodexPanel({ open, onClose }: CodexPanelProps) {
  const { openWIR } = useWalletIntelligence();
  const { openTIP } = useTokenIntelligence();
  const { setNametag: saveWalletNametag } = useWalletNametags();

  // Starred-tokens list comes from /api/starred. Starred-wallets comes through
  // /api/codex/by-category as the 'starred' bucket so we don't keep two parallel lists.
  const [tokens, setTokens] = useState<StarredItemFull[]>([]);
  const [categorized, setCategorized] = useState<Record<WalletCategory, CategorizedWallet[]>>({
    starred: [], allowlist: [], denylist: [], shadowing: [], watching: [],
  });
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'wallets' | 'tokens'>('wallets');
  const [walletCategory, setWalletCategory] = useState<WalletCategory>('starred');

  // Edit nametag state — applies to the StarredItemFull list (starred tokens)
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editNametag, setEditNametag] = useState('');
  // Separate edit state for category-view rows (keyed by address since they have no id).
  const [editingCategoryAddr, setEditingCategoryAddr] = useState<string | null>(null);
  const [editCategoryNametag, setEditCategoryNametag] = useState('');

  const loadStarred = useCallback(async () => {
    setLoading(true);
    try {
      const [starredRes, categoriesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/starred`),
        fetch(`${API_BASE_URL}/api/codex/by-category`),
      ]);

      // Capture starred wallets from the always-available /api/starred endpoint as a
      // fallback. /api/codex/by-category is newer and may 404 if the backend wasn't
      // restarted after the upgrade; without this fallback the Wallets/Starred tab
      // would show empty even though the data exists.
      let starredWalletFallback: CategorizedWallet[] = [];
      if (starredRes.ok) {
        const data = await starredRes.json();
        setTokens(data.tokens || []);
        starredWalletFallback = (data.wallets || []).map((w: StarredItemFull) => ({
          wallet_address: w.item_address,
          nametag: w.nametag,
          added_at: w.starred_at,
        }));
      }

      if (categoriesRes.ok) {
        const data = await categoriesRes.json();
        setCategorized({
          // Prefer the categorized endpoint's starred list if present, but never
          // let it be empty when the legacy endpoint had results.
          starred: (data.starred && data.starred.length > 0) ? data.starred : starredWalletFallback,
          allowlist: data.allowlist || [],
          denylist: data.denylist || [],
          shadowing: data.shadowing || [],
          watching: data.watching || [],
        });
      } else {
        // New endpoint missing entirely (older backend) — keep starred from the legacy
        // endpoint so the Codex remains usable. Other categories remain empty until restart.
        setCategorized({
          starred: starredWalletFallback,
          allowlist: [],
          denylist: [],
          shadowing: [],
          watching: [],
        });
      }
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (open) loadStarred();
  }, [open, loadStarred]);

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
  const filteredTokens = query
    ? tokens.filter(t => t.item_address.toLowerCase().includes(query) || (t.nametag || '').toLowerCase().includes(query))
    : tokens;

  // Wallet view comes from the categorized endpoint — gives us starred + tracking
  // categories under one filter. The legacy /api/starred wallet list is kept only
  // for the StarButton state machine and isn't rendered here anymore.
  const categoryWallets = categorized[walletCategory] || [];
  const filteredCategoryWallets = query
    ? categoryWallets.filter(w =>
        w.wallet_address.toLowerCase().includes(query) ||
        (w.nametag || '').toLowerCase().includes(query)
      )
    : categoryWallets;

  const saveCategoryNametag = async (address: string) => {
    const ok = await saveWalletNametag(address, editCategoryNametag);
    if (ok) {
      toast.success('Nametag saved');
      setEditingCategoryAddr(null);
      setEditCategoryNametag('');
      loadStarred();
    } else {
      toast.error('Nametag must be non-empty');
    }
  };

  return (
      <div
        className='flex h-full w-full flex-col border-l bg-background shadow-xl'
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b px-4 py-3'>
          <div>
            <h2 className='text-sm font-semibold'>Codex — Favorites</h2>
            <p className='text-muted-foreground text-[11px]'>
              {categorized.starred.length} starred wallets · {tokens.length} starred tokens
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
            Wallets ({categoryWallets.length})
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

        {/* Category chips — only meaningful for wallets */}
        {activeTab === 'wallets' && (
          <div className='border-b px-3 py-2'>
            <div className='flex flex-wrap gap-1'>
              {(Object.keys(CATEGORY_META) as WalletCategory[]).map((cat) => {
                const meta = CATEGORY_META[cat];
                const Icon = meta.icon;
                const count = categorized[cat]?.length || 0;
                const active = walletCategory === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => setWalletCategory(cat)}
                    title={meta.description}
                    className={cn(
                      'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                      active
                        ? 'bg-primary/15 text-primary border border-primary/30'
                        : 'bg-muted/30 text-muted-foreground hover:bg-muted/60 hover:text-foreground border border-transparent'
                    )}
                  >
                    <Icon className={cn('h-3 w-3', active ? meta.color : '')} />
                    {meta.label}
                    <span className='text-[9px] opacity-70'>{count}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* List */}
        <div className='flex-1 overflow-y-auto px-3 py-2'>
          {loading ? (
            <div className='flex items-center justify-center gap-2 py-8 text-muted-foreground'>
              <Loader2 className='h-4 w-4 animate-spin' /> Loading...
            </div>
          ) : activeTab === 'wallets' ? (
            filteredCategoryWallets.length === 0 ? (
              <div className='py-8 text-center text-muted-foreground text-sm'>
                {searchQuery
                  ? 'No matches'
                  : `No wallets in ${CATEGORY_META[walletCategory].label} yet.`}
              </div>
            ) : (
              <div className='space-y-1'>
                {filteredCategoryWallets.map((w) => (
                  <div key={`${walletCategory}-${w.wallet_address}`} className='group rounded-lg border p-2 hover:bg-muted/50 transition-colors'>
                    {editingCategoryAddr === w.wallet_address ? (
                      <div className='space-y-2'>
                        <input
                          type='text'
                          value={editCategoryNametag}
                          onChange={(e) => setEditCategoryNametag(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveCategoryNametag(w.wallet_address);
                            if (e.key === 'Escape') { setEditingCategoryAddr(null); setEditCategoryNametag(''); }
                          }}
                          placeholder='Nametag (e.g. profitable scalper)'
                          className='bg-background h-7 w-full rounded border px-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary'
                          autoFocus
                        />
                        <div className='flex gap-1'>
                          <Button size='sm' className='h-6 text-[10px] flex-1' onClick={() => saveCategoryNametag(w.wallet_address)}>Save</Button>
                          <Button variant='outline' size='sm' className='h-6 text-[10px] flex-1' onClick={() => { setEditingCategoryAddr(null); setEditCategoryNametag(''); }}>Cancel</Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {w.nametag && (
                          <div className='text-sm font-semibold text-cyan-400 mb-0.5 truncate'>{w.nametag}</div>
                        )}
                        <div className='flex items-center justify-between gap-2'>
                          <code
                            className='font-mono text-[11px] cursor-pointer hover:text-blue-400 transition-colors break-all flex-1'
                            onClick={() => openWIR(w.wallet_address)}
                          >
                            {w.wallet_address}
                          </code>
                          <div className='flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity'>
                            <button
                              onClick={() => { setEditingCategoryAddr(w.wallet_address); setEditCategoryNametag(w.nametag || ''); }}
                              className='text-muted-foreground hover:text-foreground p-0.5'
                              title={w.nametag ? 'Edit nametag' : 'Add nametag'}
                            >
                              <Pencil className='h-3 w-3' />
                            </button>
                            <StarButton type='wallet' address={w.wallet_address} size='sm' />
                          </div>
                        </div>
                        <div className='flex items-center gap-2 mt-1 text-[10px] text-muted-foreground'>
                          {(() => {
                            const Icon = CATEGORY_META[walletCategory].icon;
                            return <Icon className={cn('h-3 w-3', CATEGORY_META[walletCategory].color)} />;
                          })()}
                          <span>{CATEGORY_META[walletCategory].label}</span>
                          {w.added_at && <span>· added {new Date(w.added_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>}
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )
          ) : filteredTokens.length === 0 ? (
            <div className='py-8 text-center text-muted-foreground text-sm'>
              {searchQuery ? 'No matches' : 'No starred tokens yet. Star items from the leaderboard to add them here.'}
            </div>
          ) : (
            <div className='space-y-1'>
              {filteredTokens.map((item) => (
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
          {activeTab === 'wallets'
            ? `${filteredCategoryWallets.length} ${CATEGORY_META[walletCategory].label.toLowerCase()} wallet${filteredCategoryWallets.length === 1 ? '' : 's'}`
            : `${filteredTokens.length} starred token${filteredTokens.length === 1 ? '' : 's'}`}
        </div>
      </div>
  );
}
