'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getCodexWallets,
  CodexWallet,
  addWalletTag,
  removeWalletTag,
  setWalletNametag
} from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Search,
  Tag,
  X,
  Plus,
  Trash2,
  Pencil,
  Twitter,
  Loader2
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

// Session storage cache key
const CACHE_KEY_CODEX = 'codex_panel_wallets';

interface CachedCodexData {
  wallets: CodexWallet[];
  cached_at: number;
}

interface CodexPanelProps {
  open: boolean;
  onClose: () => void;
}

type AddWalletStep = 'address' | 'tag' | 'kol';

// Cache helpers
function getFromCache(): CachedCodexData | null {
  try {
    const cached = sessionStorage.getItem(CACHE_KEY_CODEX);
    if (!cached) return null;
    return JSON.parse(cached) as CachedCodexData;
  } catch {
    return null;
  }
}

function setInCache(wallets: CodexWallet[]): void {
  try {
    sessionStorage.setItem(
      CACHE_KEY_CODEX,
      JSON.stringify({ wallets, cached_at: Date.now() })
    );
  } catch {
    // Ignore storage errors
  }
}

export function CodexPanel({ open, onClose }: CodexPanelProps) {
  // Initialize from cache
  const cachedData = useRef(getFromCache());

  const [wallets, setWallets] = useState<CodexWallet[]>(
    cachedData.current?.wallets || []
  );
  const [filteredWallets, setFilteredWallets] = useState<CodexWallet[]>(
    cachedData.current?.wallets || []
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Track if we have any data to show
  const hasData = wallets.length > 0;

  // Track initial cache state (only on mount)
  const initialHadCache = useRef(cachedData.current !== null);

  // Add wallet state
  const [newWalletAddress, setNewWalletAddress] = useState('');
  const [newWalletTag, setNewWalletTag] = useState('');
  const [newWalletKol, setNewWalletKol] = useState(false);
  const [addWalletStep, setAddWalletStep] = useState<AddWalletStep>('address');
  const [showAddWallet, setShowAddWallet] = useState(false);
  const [addingWallet, setAddingWallet] = useState(false);
  const kolToggleRef = useRef<HTMLDivElement>(null);

  // Edit nametag state
  const [editingWallet, setEditingWallet] = useState<string | null>(null);
  const [editNametag, setEditNametag] = useState('');

  const loadWallets = useCallback(
    async (showLoader = true) => {
      if (showLoader && !hasData) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const data = await getCodexWallets();
        setWallets(data.wallets);
        setFilteredWallets(data.wallets);
        setInCache(data.wallets);
      } catch (error: unknown) {
        // Only show error if we have no cached data
        if (!hasData) {
          const message =
            error instanceof Error ? error.message : 'Failed to load Codex';
          toast.error(message);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [hasData]
  );

  useEffect(() => {
    if (open) {
      // If we have cached data, show it immediately and refresh in background
      loadWallets(!initialHadCache.current);
    }
  }, [open, loadWallets]);

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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  // Auto-focus KOL toggle when step changes
  useEffect(() => {
    if (addWalletStep === 'kol' && kolToggleRef.current) {
      kolToggleRef.current.focus();
    }
  }, [addWalletStep]);

  const handleAddressSubmit = () => {
    const trimmed = newWalletAddress.trim();
    if (!trimmed) {
      toast.error('Please enter a wallet address');
      return;
    }
    if (trimmed.length < 32 || trimmed.length > 44) {
      toast.error('Invalid Solana wallet address');
      return;
    }
    setAddWalletStep('tag');
  };

  const handleTagSubmit = () => {
    if (!newWalletTag.trim()) {
      toast.error('Please enter a tag');
      return;
    }
    setNewWalletKol(true); // Default to Y
    setAddWalletStep('kol');
  };

  const handleKolSubmit = async (isKol: boolean) => {
    setAddingWallet(true);
    try {
      await addWalletTag(newWalletAddress.trim(), newWalletTag.trim(), isKol);
      toast.success('Wallet added to Codex');

      // Reset form
      setNewWalletAddress('');
      setNewWalletTag('');
      setNewWalletKol(false);
      setAddWalletStep('address');
      setShowAddWallet(false);

      // Reload wallets
      await loadWallets(false);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to add wallet';
      toast.error(message);
    } finally {
      setAddingWallet(false);
    }
  };

  const resetAddWalletForm = () => {
    setNewWalletAddress('');
    setNewWalletTag('');
    setNewWalletKol(false);
    setAddWalletStep('address');
    setShowAddWallet(false);
  };

  const handleDeleteWallet = async (wallet: CodexWallet) => {
    if (
      !confirm(
        `Remove ${wallet.wallet_address} from Codex? This will delete all ${wallet.tags.length} tag(s).`
      )
    ) {
      return;
    }

    setLoading(true);
    try {
      // Remove all tags from this wallet
      for (const tagObj of wallet.tags) {
        await removeWalletTag(wallet.wallet_address, tagObj.tag);
      }

      toast.success('Wallet removed from Codex');

      // Reload wallets
      await loadWallets(false);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to remove wallet';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleEditWallet = (wallet: CodexWallet) => {
    setEditingWallet(wallet.wallet_address);
    setEditNametag(wallet.nametag || '');
  };

  const handleSaveNametag = async () => {
    if (!editingWallet) return;

    if (!editNametag.trim()) {
      toast.error('Please enter a name');
      return;
    }

    setLoading(true);
    try {
      await setWalletNametag(editingWallet, editNametag.trim());
      toast.success('Name updated');
      setEditingWallet(null);
      setEditNametag('');
      await loadWallets(false);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update name';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const cancelEdit = () => {
    setEditingWallet(null);
    setEditNametag('');
  };

  return (
    <div
      className={cn(
        'bg-background flex flex-col border-l transition-all duration-300 ease-in-out',
        open ? 'w-[700px]' : 'w-0 border-l-0'
      )}
    >
      {open && (
        <div className='flex h-full flex-col overflow-hidden'>
          {/* Header */}
          <div className='flex items-center justify-between border-b p-3'>
            <div className='flex items-center gap-2'>
              <div>
                <h2 className='text-base font-semibold'>Codex</h2>
                <p className='text-muted-foreground text-xs'>
                  View all tagged wallets. Click to copy address.
                </p>
              </div>
              {refreshing && (
                <Loader2 className='text-muted-foreground h-3 w-3 animate-spin' />
              )}
            </div>
            <button
              onClick={onClose}
              className='rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-hidden'
            >
              <X className='h-4 w-4' />
              <span className='sr-only'>Close</span>
            </button>
          </div>

          {/* Search and Add Wallet */}
          <div className='space-y-2 p-3 pb-2'>
            {/* Search */}
            <div className='relative'>
              <Search className='text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 transform' />
              <Input
                placeholder='Search by wallet address or tag...'
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className='pl-10'
              />
            </div>

            {/* Add Wallet Section */}
            {!showAddWallet ? (
              <Button
                variant='outline'
                size='sm'
                onClick={() => setShowAddWallet(true)}
                className='w-full'
              >
                <Plus className='mr-2 h-4 w-4' />
                Add Wallet to Codex
              </Button>
            ) : (
              <div className='space-y-2 rounded-lg border p-2'>
                <div className='mb-1.5 flex items-center justify-between'>
                  <h4 className='text-xs font-semibold'>Add New Wallet</h4>
                  <Button
                    variant='ghost'
                    size='sm'
                    onClick={resetAddWalletForm}
                    className='h-6 w-6 p-0'
                  >
                    <X className='h-3 w-3' />
                  </Button>
                </div>

                {addWalletStep === 'address' && (
                  <div className='space-y-2'>
                    <Input
                      placeholder='Wallet address...'
                      value={newWalletAddress}
                      onChange={(e) => setNewWalletAddress(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleAddressSubmit();
                        if (e.key === 'Escape') resetAddWalletForm();
                      }}
                      className='font-mono text-xs'
                      autoFocus
                      disabled={addingWallet}
                    />
                    <Button
                      size='sm'
                      onClick={handleAddressSubmit}
                      disabled={addingWallet}
                      className='w-full'
                    >
                      Next
                    </Button>
                  </div>
                )}

                {addWalletStep === 'tag' && (
                  <div className='space-y-2'>
                    <div className='text-muted-foreground font-mono text-xs break-all'>
                      {newWalletAddress.slice(0, 16)}...
                    </div>
                    <Input
                      placeholder='Tag name...'
                      value={newWalletTag}
                      onChange={(e) => setNewWalletTag(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleTagSubmit();
                        if (e.key === 'Escape') resetAddWalletForm();
                      }}
                      className='text-xs'
                      autoFocus
                      disabled={addingWallet}
                    />
                    <div className='flex gap-2'>
                      <Button
                        variant='outline'
                        size='sm'
                        onClick={() => setAddWalletStep('address')}
                        disabled={addingWallet}
                        className='w-full'
                      >
                        Back
                      </Button>
                      <Button
                        size='sm'
                        onClick={handleTagSubmit}
                        disabled={addingWallet}
                        className='w-full'
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}

                {addWalletStep === 'kol' && (
                  <div className='space-y-2'>
                    <div className='text-muted-foreground space-y-1 text-xs'>
                      <div className='font-mono break-all'>
                        {newWalletAddress.slice(0, 16)}...
                      </div>
                      <div>
                        Tag:{' '}
                        <span className='font-semibold'>{newWalletTag}</span>
                      </div>
                    </div>
                    <div
                      ref={kolToggleRef}
                      className='border-input bg-background flex items-center gap-2 rounded border p-2'
                      onKeyDown={(e) => {
                        if (e.key === 'y' || e.key === 'Y') {
                          handleKolSubmit(true);
                        } else if (e.key === 'n' || e.key === 'N') {
                          handleKolSubmit(false);
                        } else if (e.key === 'Escape') {
                          resetAddWalletForm();
                        } else if (e.key === 'ArrowLeft') {
                          setNewWalletKol(true);
                        } else if (e.key === 'ArrowRight') {
                          setNewWalletKol(false);
                        }
                      }}
                      tabIndex={0}
                    >
                      <span className='text-muted-foreground flex-1 text-xs'>
                        Is KOL?
                      </span>
                      <button
                        type='button'
                        className={`rounded px-3 py-1 text-xs transition-colors ${
                          newWalletKol
                            ? 'bg-green-500/20 font-semibold text-green-700 dark:text-green-400'
                            : 'text-muted-foreground hover:bg-muted'
                        }`}
                        onClick={() => setNewWalletKol(true)}
                        disabled={addingWallet}
                      >
                        Y
                      </button>
                      <button
                        type='button'
                        className={`rounded px-3 py-1 text-xs transition-colors ${
                          !newWalletKol
                            ? 'bg-red-500/20 font-semibold text-red-700 dark:text-red-400'
                            : 'text-muted-foreground hover:bg-muted'
                        }`}
                        onClick={() => setNewWalletKol(false)}
                        disabled={addingWallet}
                      >
                        N
                      </button>
                    </div>
                    <div className='flex gap-2'>
                      <Button
                        variant='outline'
                        size='sm'
                        onClick={() => setAddWalletStep('tag')}
                        disabled={addingWallet}
                        className='w-full'
                      >
                        Back
                      </Button>
                      <Button
                        size='sm'
                        onClick={() => handleKolSubmit(newWalletKol)}
                        disabled={addingWallet}
                        className='w-full'
                      >
                        Add to Codex
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Wallet List */}
          <div className='flex-1 space-y-1.5 overflow-y-auto px-3 py-2'>
            {loading && !hasData ? (
              <div className='text-muted-foreground flex items-center justify-center gap-2 py-8'>
                <Loader2 className='h-4 w-4 animate-spin' />
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
                  className='hover:bg-muted/50 rounded-lg border p-2 transition-colors'
                >
                  {editingWallet === wallet.wallet_address ? (
                    // Edit nametag mode
                    <div className='space-y-2'>
                      <div className='mb-1.5 flex items-center justify-between'>
                        <div className='text-xs font-semibold'>Edit Name</div>
                        <Button
                          variant='ghost'
                          size='sm'
                          onClick={cancelEdit}
                          className='h-6 w-6 p-0'
                        >
                          <X className='h-3 w-3' />
                        </Button>
                      </div>
                      <div className='text-muted-foreground font-mono text-xs break-all'>
                        {wallet.wallet_address.slice(0, 16)}...
                      </div>
                      <Input
                        placeholder='Display name for this wallet...'
                        value={editNametag}
                        onChange={(e) => setEditNametag(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveNametag();
                          if (e.key === 'Escape') cancelEdit();
                        }}
                        className='text-xs'
                        autoFocus
                        disabled={loading}
                      />
                      <div className='flex gap-2'>
                        <Button
                          variant='outline'
                          size='sm'
                          onClick={cancelEdit}
                          disabled={loading}
                          className='w-full'
                        >
                          Cancel
                        </Button>
                        <Button
                          size='sm'
                          onClick={handleSaveNametag}
                          disabled={loading}
                          className='w-full'
                        >
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : (
                    // View mode
                    <>
                      {/* Nametag (display name) */}
                      {wallet.nametag && (
                        <div className='mb-1 text-sm font-semibold'>
                          {wallet.nametag}
                        </div>
                      )}
                      <div className='mb-1.5 flex items-center justify-between gap-2'>
                        <div
                          className='flex-1 cursor-pointer font-mono text-xs break-all'
                          onClick={() => copyToClipboard(wallet.wallet_address)}
                        >
                          {wallet.wallet_address}
                        </div>
                        <div className='flex items-center gap-1'>
                          <Button
                            variant='ghost'
                            size='sm'
                            className='hover:bg-muted h-6 w-6 p-0'
                            onClick={() => handleEditWallet(wallet)}
                            title='Edit name'
                          >
                            <Pencil className='h-3 w-3' />
                          </Button>
                          <a
                            href={`https://twitter.com/search?q=${encodeURIComponent(wallet.wallet_address)}`}
                            target='_blank'
                            rel='noopener noreferrer'
                            title='Search on Twitter/X'
                          >
                            <Button
                              variant='ghost'
                              size='sm'
                              className='hover:bg-muted h-6 w-6 p-0'
                            >
                              <Twitter className='h-3 w-3' />
                            </Button>
                          </a>
                          <Button
                            variant='ghost'
                            size='sm'
                            className='text-destructive hover:text-destructive hover:bg-destructive/10 h-6 w-6 p-0'
                            onClick={() => handleDeleteWallet(wallet)}
                            title='Remove from Codex'
                          >
                            <Trash2 className='h-3 w-3' />
                          </Button>
                        </div>
                      </div>
                      <div className='mb-1.5 flex flex-wrap items-center gap-1.5'>
                        <div className='flex items-center gap-1'>
                          <span className='text-muted-foreground text-xs'>
                            Tokens:
                          </span>
                          <span className='bg-primary text-primary-foreground rounded-full px-2 py-0.5 text-xs font-bold'>
                            {wallet.token_count}
                          </span>
                        </div>
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
                    </>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className='text-muted-foreground border-t p-3 text-xs'>
            Showing {filteredWallets.length} of {wallets.length} wallets
          </div>
        </div>
      )}
    </div>
  );
}
