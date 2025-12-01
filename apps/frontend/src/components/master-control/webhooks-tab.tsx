'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Loader2,
  RefreshCw,
  AlertTriangle,
  Trash2,
  Plus,
  Webhook
} from 'lucide-react';
import { toast } from 'sonner';
import { API_BASE_URL, fetchWithTimeout } from '@/lib/api';
import { InfoTooltip } from './InfoTooltip';
import { SETTINGS_FETCH_TIMEOUT } from './utils';
import { WebhookInfo } from './types';

export function WebhooksTab() {
  const [webhooks, setWebhooks] = useState<WebhookInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchWebhooks = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${API_BASE_URL}/webhooks/list`,
        { cache: 'no-store' },
        SETTINGS_FETCH_TIMEOUT
      );
      if (res.ok) {
        const data = await res.json();
        setWebhooks(data.webhooks || []);
      } else {
        throw new Error('Failed to fetch');
      }
    } catch (err) {
      const message =
        err instanceof Error && err.message.includes('timeout')
          ? 'Backend busy (ingestion running). Try again shortly.'
          : 'Failed to load webhooks';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const createSwabWebhook = async () => {
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE_URL}/webhooks/create-swab`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (res.ok) {
        toast.success('SWAB webhook creation queued');
        setTimeout(fetchWebhooks, 2000);
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to create webhook');
      }
    } catch {
      toast.error('Failed to create webhook');
    } finally {
      setCreating(false);
    }
  };

  const deleteWebhook = async (webhookId: string) => {
    setDeletingId(webhookId);
    try {
      const res = await fetch(`${API_BASE_URL}/webhooks/${webhookId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        toast.success('Webhook deletion queued');
        setWebhooks((prev) => prev.filter((w) => w.webhookID !== webhookId));
      } else {
        toast.error('Failed to delete webhook');
      }
    } catch {
      toast.error('Failed to delete webhook');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <h4 className='text-muted-foreground flex items-center text-xs font-semibold uppercase'>
          Helius Webhooks
          <InfoTooltip>
            Webhooks for real-time SWAB tracking. Captures accurate exit prices
            when MTEW wallets sell.
          </InfoTooltip>
        </h4>
        <div className='flex gap-2'>
          <Button
            variant='outline'
            size='sm'
            onClick={fetchWebhooks}
            disabled={loading}
          >
            <RefreshCw
              className={`mr-1 h-3 w-3 ${loading ? 'animate-spin' : ''}`}
            />
            Refresh
          </Button>
          <Button
            variant='default'
            size='sm'
            onClick={createSwabWebhook}
            disabled={creating}
          >
            {creating ? (
              <Loader2 className='mr-1 h-3 w-3 animate-spin' />
            ) : (
              <Plus className='mr-1 h-3 w-3' />
            )}
            Create SWAB Webhook
          </Button>
        </div>
      </div>

      {loading ? (
        <div className='flex items-center justify-center py-8'>
          <Loader2 className='h-5 w-5 animate-spin' />
        </div>
      ) : error ? (
        <div className='flex flex-col items-center justify-center gap-3 py-8'>
          <AlertTriangle className='h-8 w-8 text-yellow-500' />
          <p className='text-muted-foreground text-sm'>{error}</p>
          <Button variant='outline' size='sm' onClick={fetchWebhooks}>
            <RefreshCw className='mr-2 h-3 w-3' />
            Retry
          </Button>
        </div>
      ) : webhooks.length === 0 ? (
        <div className='bg-muted/50 rounded-lg border border-dashed p-6 text-center'>
          <Webhook className='text-muted-foreground mx-auto mb-2 h-8 w-8' />
          <p className='text-muted-foreground text-sm'>
            No webhooks configured
          </p>
          <p className='text-muted-foreground mt-1 text-xs'>
            Create a SWAB webhook to track MTEW wallet sells in real-time
          </p>
        </div>
      ) : (
        <div className='space-y-2'>
          {webhooks.map((webhook) => (
            <div
              key={webhook.webhookID}
              className='bg-muted/30 flex items-center justify-between rounded-lg border p-3'
            >
              <div className='min-w-0 flex-1'>
                <div className='flex items-center gap-2'>
                  <Badge variant='secondary' className='text-xs'>
                    {webhook.webhookType || 'enhanced'}
                  </Badge>
                  <code className='text-muted-foreground truncate text-xs'>
                    {webhook.webhookID}
                  </code>
                </div>
                <p className='text-muted-foreground mt-1 truncate text-xs'>
                  {webhook.webhookURL}
                </p>
                {webhook.accountAddresses && (
                  <p className='text-muted-foreground text-xs'>
                    Monitoring {webhook.accountAddresses.length} wallets
                  </p>
                )}
              </div>
              <Button
                variant='ghost'
                size='icon'
                className='text-destructive hover:text-destructive h-8 w-8'
                onClick={() => deleteWebhook(webhook.webhookID)}
                disabled={deletingId === webhook.webhookID}
              >
                {deletingId === webhook.webhookID ? (
                  <Loader2 className='h-4 w-4 animate-spin' />
                ) : (
                  <Trash2 className='h-4 w-4' />
                )}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
