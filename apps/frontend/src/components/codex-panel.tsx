'use client';

import { useState, useEffect, useRef } from 'react';
import {
  getCodexWallets,
  CodexWallet,
  addWalletTag,
  removeWalletTag
} from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, Tag, X, Plus, Trash2, Pencil, Twitter } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface CodexPanelProps {
  open: boolean;
  onClose: () => void;
}

type AddWalletStep = 'address' | 'tag' | 'kol';

export function CodexPanel({ open, onClose }: CodexPanelProps) {
  const [wallets, setWallets] = useState<CodexWallet[]>([]);
  const [filteredWallets, setFilteredWallets] = useState<CodexWallet[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);

  // Add wallet state
  const [newWalletAddress, setNewWalletAddress] = useState('');
  const [newWalletTag, setNewWalletTag] = useState('');
  const [newWalletKol, setNewWalletKol] = useState(false);
  const [addWalletStep, setAddWalletStep] = useState<AddWalletStep>('address');
  const [showAddWallet, setShowAddWallet] = useState(false);
  const [addingWallet, setAddingWallet] = useState(false);
  const kolToggleRef = useRef<HTMLDivElement>(null);

  // Edit wallet state
  const [editingWallet, setEditingWallet] = useState<string | null>(null);
  const [editTagName, setEditTagName] = useState('');
  const [editTagKol, setEditTagKol] = useState(false);
  const [editStep, setEditStep] = useState<'tag' | 'kol'>('tag');
  const editKolToggleRef = useRef<HTMLDivElement>(null);

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
      await loadWallets();
    } catch (error: any) {
      toast.error(error.message || 'Failed to add wallet');
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
      await loadWallets();
    } catch (error: any) {
      toast.error(error.message || 'Failed to remove wallet');
    } finally {
      setLoading(false);
    }
  };

  const handleEditWallet = (wallet: CodexWallet) => {
    // Start editing with the first tag
    if (wallet.tags.length > 0) {
      const firstTag = wallet.tags[0];
      setEditingWallet(wallet.wallet_address);
      setEditTagName(firstTag.tag);
      setEditTagKol(firstTag.is_kol);
      setEditStep('tag');
    }
  };

  const handleEditTagSubmit = () => {
    if (!editTagName.trim()) {
      toast.error('Please enter a tag name');
      return;
    }
    setEditStep('kol');
  };

  const handleEditKolSubmit = async (isKol: boolean) => {
    if (!editingWallet) return;

    setLoading(true);
    try {
      const wallet = wallets.find((w) => w.wallet_address === editingWallet);
      if (!wallet) return;

      // Remove old tag
      const oldTag = wallet.tags[0];
      await removeWalletTag(editingWallet, oldTag.tag);

      // Add new tag
      await addWalletTag(editingWallet, editTagName.trim(), isKol);

      toast.success('Tag updated');

      // Reset edit state
      setEditingWallet(null);
      setEditTagName('');
      setEditTagKol(false);
      setEditStep('tag');

      // Reload wallets
      await loadWallets();
    } catch (error: any) {
      toast.error(error.message || 'Failed to update tag');
    } finally {
      setLoading(false);
    }
  };

  const cancelEdit = () => {
    setEditingWallet(null);
    setEditTagName('');
    setEditTagKol(false);
    setEditStep('tag');
  };

  // Auto-focus edit KOL toggle when step changes
  useEffect(() => {
    if (editStep === 'kol' && editKolToggleRef.current) {
      editKolToggleRef.current.focus();
    }
  }, [editStep]);

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
            <div>
              <h2 className='text-base font-semibold'>Codex</h2>
              <p className='text-muted-foreground text-xs'>
                View all tagged wallets. Click to copy address.
              </p>
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
                  className='hover:bg-muted/50 rounded-lg border p-2 transition-colors'
                >
                  {editingWallet === wallet.wallet_address ? (
                    // Edit mode
                    <div className='space-y-2'>
                      <div className='mb-1.5 flex items-center justify-between'>
                        <div className='text-xs font-semibold'>Edit Tag</div>
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

                      {editStep === 'tag' && (
                        <div className='space-y-2'>
                          <Input
                            placeholder='Tag name...'
                            value={editTagName}
                            onChange={(e) => setEditTagName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleEditTagSubmit();
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
                              onClick={handleEditTagSubmit}
                              disabled={loading}
                              className='w-full'
                            >
                              Next
                            </Button>
                          </div>
                        </div>
                      )}

                      {editStep === 'kol' && (
                        <div className='space-y-2'>
                          <div className='text-xs'>
                            Tag:{' '}
                            <span className='font-semibold'>{editTagName}</span>
                          </div>
                          <div
                            ref={editKolToggleRef}
                            className='border-input bg-background flex items-center gap-2 rounded border p-2'
                            onKeyDown={(e) => {
                              if (e.key === 'y' || e.key === 'Y') {
                                handleEditKolSubmit(true);
                              } else if (e.key === 'n' || e.key === 'N') {
                                handleEditKolSubmit(false);
                              } else if (e.key === 'Escape') {
                                cancelEdit();
                              } else if (e.key === 'ArrowLeft') {
                                setEditTagKol(true);
                              } else if (e.key === 'ArrowRight') {
                                setEditTagKol(false);
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
                                editTagKol
                                  ? 'bg-green-500/20 font-semibold text-green-700 dark:text-green-400'
                                  : 'text-muted-foreground hover:bg-muted'
                              }`}
                              onClick={() => setEditTagKol(true)}
                              disabled={loading}
                            >
                              Y
                            </button>
                            <button
                              type='button'
                              className={`rounded px-3 py-1 text-xs transition-colors ${
                                !editTagKol
                                  ? 'bg-red-500/20 font-semibold text-red-700 dark:text-red-400'
                                  : 'text-muted-foreground hover:bg-muted'
                              }`}
                              onClick={() => setEditTagKol(false)}
                              disabled={loading}
                            >
                              N
                            </button>
                          </div>
                          <div className='flex gap-2'>
                            <Button
                              variant='outline'
                              size='sm'
                              onClick={() => setEditStep('tag')}
                              disabled={loading}
                              className='w-full'
                            >
                              Back
                            </Button>
                            <Button
                              size='sm'
                              onClick={() => handleEditKolSubmit(editTagKol)}
                              disabled={loading}
                              className='w-full'
                            >
                              Save
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    // View mode
                    <>
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
                            title='Edit tag'
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
