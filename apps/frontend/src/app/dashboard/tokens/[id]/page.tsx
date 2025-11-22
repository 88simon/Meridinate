'use client';

import { useEffect, useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getTokenById, TokenDetail } from '@/lib/api';
import { TokenDetailsView } from './token-details-view';
import { WalletTagsProvider } from '@/contexts/WalletTagsContext';

export default function TokenDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [token, setToken] = useState<TokenDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Extract all wallet addresses for WalletTagsProvider
  const walletAddresses = useMemo(() => {
    if (!token) return [];
    return token.wallets.map((w) => w.wallet_address);
  }, [token]);

  useEffect(() => {
    const id = params.id as string;
    if (!id) return;

    getTokenById(parseInt(id))
      .then(setToken)
      .catch(() => {
        setError('Failed to load token details');
      })
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <div className='flex h-full items-center justify-center'>
        <div className='text-center'>
          <div className='text-lg font-medium'>Loading token details...</div>
          <div className='text-muted-foreground mt-2 text-sm'>
            Fetching data from Flask backend
          </div>
        </div>
      </div>
    );
  }

  if (error || !token) {
    return (
      <div className='flex h-full items-center justify-center'>
        <div className='text-center'>
          <div className='text-destructive text-lg font-medium'>Error</div>
          <div className='text-muted-foreground mt-2 text-sm'>
            {error || 'Token not found'}
          </div>
          <button
            onClick={() => router.push('/dashboard/tokens')}
            className='bg-primary text-primary-foreground hover:bg-primary/90 mt-4 rounded-md px-4 py-2'
          >
            Back to Tokens
          </button>
        </div>
      </div>
    );
  }

  return (
    <WalletTagsProvider walletAddresses={walletAddresses}>
      <TokenDetailsView token={token} />
    </WalletTagsProvider>
  );
}
