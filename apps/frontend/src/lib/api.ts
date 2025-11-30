/**
 * Meridinate API Client
 * Fetches data from the FastAPI backend running on localhost:5003
 *
 * Uses auto-generated types from OpenAPI schema
 */

import { components } from './generated/api-types';

export const API_BASE_URL = 'http://localhost:5003';

// ============================================================================
// Fetch with Timeout Utility
// ============================================================================

/**
 * Fetch with timeout support.
 * Prevents requests from hanging indefinitely during long-running backend operations.
 *
 * @param url - The URL to fetch
 * @param options - Fetch options
 * @param timeoutMs - Timeout in milliseconds (default: 5000ms)
 * @returns Promise that resolves to Response or rejects on timeout
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 5000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    return response;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`Request timeout after ${timeoutMs}ms`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ============================================================================
// Type Exports (from generated schemas)
// ============================================================================

// Performance bucket type for type guards
export type PerformanceBucket = 'prime' | 'monitor' | 'cull' | 'excluded';

// Token types - use generated schemas directly (performance fields now included)
export type Token = components['schemas']['Token'];
export type TokenDetail = components['schemas']['TokenDetail'];
export type TokensResponse = components['schemas']['TokensResponse'];
export type Wallet = components['schemas']['Wallet'];
export type WalletTag = components['schemas']['WalletTag'];
export type MultiTokenWallet = components['schemas']['MultiTokenWallet'];
export type MultiTokenWalletsResponse =
  components['schemas']['MultiTokenWalletsResponse'];
export type CodexWallet = components['schemas']['CodexWallet'];
export type CodexResponse = components['schemas']['CodexResponse'];
export type AnalysisRun = components['schemas']['AnalysisRun'];
export type AnalysisHistory = components['schemas']['AnalysisHistory'];
export type AnalysisSettings = components['schemas']['AnalysisSettings'];
export type AnalysisJob = components['schemas']['AnalysisJob'];
export type AnalysisJobSummary = components['schemas']['AnalysisJobSummary'];
export type AnalysisListResponse =
  components['schemas']['AnalysisListResponse'];
export type QueueTokenResponse = components['schemas']['QueueTokenResponse'];
export type RefreshBalancesResult =
  components['schemas']['RefreshBalancesResult'];
export type RefreshBalancesResponse =
  components['schemas']['RefreshBalancesResponse'];
export type RefreshMarketCapResult =
  components['schemas']['RefreshMarketCapResult'];
export type RefreshMarketCapsResponse =
  components['schemas']['RefreshMarketCapsResponse'];

// Top Holders types (manually defined until OpenAPI schema regeneration)
export interface TopHolder {
  address: string;
  amount: string;
  decimals: number;
  uiAmountString: string;
  token_balance_usd?: number | null;
  wallet_balance_usd?: number | null;
}

export interface TopHoldersResponse {
  token_address: string;
  token_symbol?: string | null;
  holders: TopHolder[];
  total_holders: number;
  api_credits_used: number;
}

// Backwards compatibility - ApiSettings is now AnalysisSettings with bypassLimits
export type ApiSettings = AnalysisSettings & { bypassLimits?: boolean };

// ============================================================================
// Token Details Cache (for instant modal opening)
// ============================================================================

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const TOKEN_DETAILS_CACHE_TTL = 30000; // 30 seconds - enough for hover prefetch
const tokenDetailsCache = new Map<number, CacheEntry<TokenDetail>>();

/**
 * Get cached token details if available and not stale
 */
export function getCachedTokenDetails(id: number): TokenDetail | null {
  const entry = tokenDetailsCache.get(id);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > TOKEN_DETAILS_CACHE_TTL) {
    tokenDetailsCache.delete(id);
    return null;
  }
  return entry.data;
}

/**
 * Set token details in cache
 */
function setCachedTokenDetails(id: number, data: TokenDetail): void {
  tokenDetailsCache.set(id, { data, timestamp: Date.now() });
}

/**
 * Clear token details cache entry
 */
export function clearTokenDetailsCache(id?: number): void {
  if (id !== undefined) {
    tokenDetailsCache.delete(id);
  } else {
    tokenDetailsCache.clear();
  }
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Fetch all analyzed tokens
 */
export async function getTokens(): Promise<TokensResponse> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/history`, {
    cache: 'no-store' // Always fetch fresh data
  });

  if (!res.ok) {
    throw new Error('Failed to fetch tokens');
  }

  return res.json();
}

/**
 * Fetch details for a specific token (uses cache if available)
 */
export async function getTokenById(
  id: number,
  options?: { skipCache?: boolean }
): Promise<TokenDetail> {
  // Check cache first (unless explicitly skipped)
  if (!options?.skipCache) {
    const cached = getCachedTokenDetails(id);
    if (cached) return cached;
  }

  const res = await fetch(`${API_BASE_URL}/api/tokens/${id}`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch token details');
  }

  const data: TokenDetail = await res.json();
  setCachedTokenDetails(id, data);
  return data;
}

/**
 * Fetch analysis history for a specific token
 */
export async function getTokenAnalysisHistory(
  id: number
): Promise<AnalysisHistory> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${id}/history`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch analysis history');
  }

  return res.json();
}

/**
 * Download Axiom JSON for a token
 */
export function downloadAxiomJson(token: TokenDetail) {
  const dataStr = JSON.stringify(token.axiom_json, null, 2);
  const blob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${token.acronym}_axiom_export.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Format UTC timestamp to local time
 */
export function formatTimestamp(timestamp: string): string {
  if (!timestamp) return '-';
  // SQLite returns UTC without 'Z', so we append it
  const utcTimestamp = timestamp.replace(' ', 'T') + 'Z';
  const date = new Date(utcTimestamp);
  return date.toLocaleString();
}

/**
 * Format timestamp to short date
 */
export function formatShortDate(timestamp: string): string {
  if (!timestamp) return '-';
  const utcTimestamp = timestamp.replace(' ', 'T') + 'Z';
  const date = new Date(utcTimestamp);
  return date.toLocaleDateString();
}

/**
 * Fetch wallets that appear in multiple tokens
 */
export async function getMultiTokenWallets(
  minTokens: number = 2
): Promise<MultiTokenWalletsResponse> {
  const res = await fetch(
    `${API_BASE_URL}/multi-token-wallets?min_tokens=${minTokens}`,
    {
      cache: 'no-store'
    }
  );

  if (!res.ok) {
    throw new Error('Failed to fetch multi-token wallets');
  }

  return res.json();
}

/**
 * Get tags for a wallet address
 */
export async function getWalletTags(
  walletAddress: string
): Promise<WalletTag[]> {
  const res = await fetch(`${API_BASE_URL}/wallets/${walletAddress}/tags`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch wallet tags');
  }

  const data = await res.json();
  return data.tags;
}

/**
 * Add a tag to a wallet
 */
export async function addWalletTag(
  walletAddress: string,
  tag: string,
  isKol: boolean = false
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/wallets/${walletAddress}/tags`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ tag, is_kol: isKol })
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error || 'Failed to add tag');
  }
}

/**
 * Remove a tag from a wallet
 */
export async function removeWalletTag(
  walletAddress: string,
  tag: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/wallets/${walletAddress}/tags`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ tag })
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error || 'Failed to remove tag');
  }
}

/**
 * Get all unique tags
 */
export async function getAllTags(): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/tags`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch tags');
  }

  const data = await res.json();
  return data.tags;
}

/**
 * Get all wallets in the Codex (wallets that have tags)
 */
export async function getCodexWallets(): Promise<CodexResponse> {
  const res = await fetch(`${API_BASE_URL}/codex`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch Codex');
  }

  return res.json();
}

/**
 * Get all deleted tokens (trash)
 */
export async function getDeletedTokens(): Promise<TokensResponse> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/trash`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch deleted tokens');
  }

  return res.json();
}

/**
 * Restore a deleted token
 */
export async function restoreToken(tokenId: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${tokenId}/restore`, {
    method: 'POST',
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to restore token');
  }
}

/**
 * Permanently delete a token
 */
export async function permanentDeleteToken(tokenId: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${tokenId}/permanent`, {
    method: 'DELETE',
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to permanently delete token');
  }
}

/**
 * Analyze a token with custom API settings
 */
export async function analyzeToken(
  tokenAddress: string,
  apiSettings: AnalysisSettings
): Promise<QueueTokenResponse> {
  const res = await fetch(`${API_BASE_URL}/analyze/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      address: tokenAddress,
      api_settings: apiSettings
    }),
    cache: 'no-store'
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error || 'Failed to analyze token');
  }

  return res.json();
}

/**
 * Refresh wallet balances for multiple wallets
 */
export async function refreshWalletBalances(
  walletAddresses: string[]
): Promise<RefreshBalancesResponse> {
  const res = await fetch(`${API_BASE_URL}/wallets/refresh-balances`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      wallet_addresses: walletAddresses
    }),
    cache: 'no-store'
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error || 'Failed to refresh balances');
  }

  return res.json();
}

/**
 * Refresh market caps for multiple tokens
 */
export async function refreshMarketCaps(
  tokenIds: number[]
): Promise<RefreshMarketCapsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/refresh-market-caps`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      token_ids: tokenIds
    }),
    cache: 'no-store'
  });

  if (!res.ok) {
    let errorMessage = 'Failed to refresh market caps';
    try {
      const error = await res.json();
      errorMessage = error.error || error.detail || errorMessage;
    } catch (e) {
      const text = await res.text();
      errorMessage = `HTTP ${res.status}: ${text || res.statusText}`;
    }
    throw new Error(errorMessage);
  }

  return res.json();
}

/**
 * Get current API settings
 */
export async function getApiSettings(): Promise<AnalysisSettings> {
  const res = await fetch(`${API_BASE_URL}/api/settings`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch API settings');
  }

  return res.json();
}

/**
 * Solscan Settings Interface
 */
export interface SolscanSettings {
  activity_type: string;
  exclude_amount_zero: string;
  remove_spam: string;
  value: string;
  token_address: string;
  page_size: string;
}

/**
 * Get current Solscan URL settings from action_wheel_settings.ini
 */
export async function getSolscanSettings(): Promise<SolscanSettings> {
  const res = await fetch(`${API_BASE_URL}/api/solscan-settings`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch Solscan settings');
  }

  return res.json();
}

/**
 * Update Solscan URL settings in action_wheel_settings.ini
 */
export async function updateSolscanSettings(
  settings: Partial<SolscanSettings>
): Promise<{ status: string; settings: SolscanSettings }> {
  const res = await fetch(`${API_BASE_URL}/api/solscan-settings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(settings)
  });

  if (!res.ok) {
    throw new Error('Failed to update Solscan settings');
  }

  return res.json();
}

/**
 * Build Solscan URL from settings for a wallet address
 * Fetches current settings and constructs the proper URL
 *
 * IMPORTANT: Parameter order matters for Solscan!
 * - token_address must come BEFORE value parameters
 * - Second value parameter should be 'undefined', not empty
 */
export async function buildSolscanUrlWithSettings(
  walletAddress: string
): Promise<string> {
  try {
    const settings = await getSolscanSettings();
    // CRITICAL: Maintain exact parameter order that Solscan expects
    return `https://solscan.io/account/${walletAddress}?activity_type=${settings.activity_type}&exclude_amount_zero=${settings.exclude_amount_zero}&remove_spam=${settings.remove_spam}&token_address=${settings.token_address}&value=${settings.value}&value=undefined&page_size=${settings.page_size}#transfers`;
  } catch (error) {
    console.error('Failed to build Solscan URL with settings:', error);
    // Fallback to basic URL if settings fetch fails
    return `https://solscan.io/account/${walletAddress}#transfers`;
  }
}

/**
 * Normalize activity_type for compatibility with Solscan's current expectations
 * Handles migration from old ACTIVITY_* values to current format if needed
 */
function normalizeActivityType(activityType: string): string {
  // Map old/deprecated values to current ones
  const migrations: Record<string, string> = {
    ACTIVITY_SOL_TRANSFER: 'ACTIVITY_SPL_TRANSFER' // SOL is handled via token_address filter
    // Add more migrations here if Solscan changes parameter format
  };

  return migrations[activityType] || activityType;
}

/**
 * Update gem status of a token (DEPRECATED - use token tags instead)
 */
export async function updateGemStatus(
  tokenId: number,
  gemStatus: 'gem' | 'dud' | null
): Promise<{ message: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/tokens/${tokenId}/gem-status`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gem_status: gemStatus })
    }
  );

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'Failed to update gem status');
  }

  return response.json();
}

/**
 * Get tags for a token
 */
export async function getTokenTags(tokenId: number): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${tokenId}/tags`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch token tags');
  }

  const data = await res.json();
  return data.tags;
}

/**
 * Add a tag to a token (e.g., 'gem', 'dud')
 */
export async function addTokenTag(tokenId: number, tag: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${tokenId}/tags`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ tag })
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to add tag');
  }
}

/**
 * Remove a tag from a token
 */
export async function removeTokenTag(
  tokenId: number,
  tag: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${tokenId}/tags`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ tag })
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to remove tag');
  }
}

/**
 * Get top N token holders for a given token
 * This triggers a fresh analysis via Helius API (1 credit)
 */
export async function getTopHolders(
  mintAddress: string,
  limit?: number
): Promise<TopHoldersResponse> {
  const url = new URL(`${API_BASE_URL}/api/tokens/${mintAddress}/top-holders`);
  if (limit !== undefined) {
    url.searchParams.set('limit', limit.toString());
  }

  const res = await fetch(url.toString());

  if (!res.ok) {
    const error = await res
      .json()
      .catch(() => ({ detail: 'Failed to fetch top holders' }));
    throw new Error(error.detail || 'Failed to fetch top holders');
  }

  return res.json();
}

/**
 * Build Solscan URL synchronously from provided settings
 * Use this when settings are already available
 */
export function buildSolscanUrl(
  walletAddress: string,
  settings: SolscanSettings
): string {
  // Normalize activity_type for compatibility
  const activityType = normalizeActivityType(settings.activity_type);

  // CRITICAL: Maintain exact parameter order that Solscan expects
  // Based on Solscan's 2025 format:
  // 1. activity_type
  // 2. exclude_amount_zero
  // 3. remove_spam
  // 4. token_address (MUST come before value parameters)
  // 5. value (min value)
  // 6. value=undefined (max value, required by Solscan)
  // 7. page_size
  return `https://solscan.io/account/${walletAddress}?activity_type=${activityType}&exclude_amount_zero=${settings.exclude_amount_zero}&remove_spam=${settings.remove_spam}&token_address=${settings.token_address}&value=${settings.value}&value=undefined&page_size=${settings.page_size}#transfers`;
}

// ============================================================================
// Credit Stats API Functions
// ============================================================================

export type CreditUsageStats =
  components['schemas']['CreditUsageStatsResponse'];

/**
 * Get today's API credit usage
 */
export async function getCreditStatsToday(): Promise<CreditUsageStats> {
  const res = await fetch(`${API_BASE_URL}/api/stats/credits/today`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch credit stats');
  }

  return res.json();
}

/**
 * Get API credit usage for a date range
 */
export async function getCreditStatsRange(
  days: number = 7
): Promise<CreditUsageStats> {
  const res = await fetch(
    `${API_BASE_URL}/api/stats/credits/range?days=${days}`,
    {
      cache: 'no-store'
    }
  );

  if (!res.ok) {
    throw new Error('Failed to fetch credit stats range');
  }

  return res.json();
}

/**
 * Credit transaction for recent credits list
 */
export interface CreditTransaction {
  id: number;
  operation: string;
  credits: number;
  timestamp: string | null;
  token_id: number | null;
  wallet_address: string | null;
  context: Record<string, unknown> | null;
}

/**
 * Get recent credit transactions
 */
export async function getCreditTransactions(
  limit: number = 5
): Promise<{ transactions: CreditTransaction[]; total: number }> {
  const res = await fetch(
    `${API_BASE_URL}/api/stats/credits/transactions?limit=${limit}`,
    {
      cache: 'no-store'
    }
  );

  if (!res.ok) {
    throw new Error('Failed to fetch credit transactions');
  }

  return res.json();
}

/**
 * Aggregated operation for status bar display
 */
export interface AggregatedOperation {
  operation: string;
  label: string;
  credits: number;
  timestamp: string;
  transaction_count: number;
}

/**
 * Get aggregated credit operations (grouped by time window)
 * @deprecated Use getOperationLog for persisted operations
 */
export async function getAggregatedOperations(
  limit: number = 5
): Promise<{ operations: AggregatedOperation[] }> {
  const res = await fetch(
    `${API_BASE_URL}/api/stats/credits/operations?limit=${limit}`,
    {
      cache: 'no-store'
    }
  );

  if (!res.ok) {
    throw new Error('Failed to fetch aggregated operations');
  }

  return res.json();
}

/**
 * Persisted operation log entry
 */
export interface OperationLogEntry {
  id: number;
  operation: string;
  label: string;
  credits: number;
  call_count: number;
  timestamp: string;
  context?: Record<string, unknown>;
}

/**
 * Get persisted operation log (survives restarts)
 */
export async function getOperationLog(
  limit: number = 30
): Promise<{ operations: OperationLogEntry[]; total: number }> {
  const res = await fetch(
    `${API_BASE_URL}/api/stats/credits/operation-log?limit=${limit}`,
    {
      cache: 'no-store'
    }
  );

  if (!res.ok) {
    throw new Error('Failed to fetch operation log');
  }

  return res.json();
}

/**
 * Latest token response type
 */
export interface LatestToken {
  token_id: number | null;
  token_name: string | null;
  token_symbol: string | null;
  analysis_timestamp: string | null;
  wallets_found: number | null;
  credits_used: number | null;
}

/**
 * Get the most recently analyzed token
 */
export async function getLatestToken(): Promise<LatestToken> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/latest`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch latest token');
  }

  return res.json();
}

// ============================================================================
// SWAB (Smart Wallet Archive Builder) API Functions
// ============================================================================

export type SwabSettings = components['schemas']['SwabSettingsResponse'];
export type SwabStats = components['schemas']['SwabStatsResponse'];
// Extended position type with new USD PnL, hold time, and FPnL fields
export type SwabPosition = components['schemas']['PositionResponse'] & {
  entry_balance?: number | null;
  entry_balance_usd?: number | null;
  pnl_usd?: number | null;
  hold_time_seconds?: number | null;
  fpnl_ratio?: number | null; // Fumbled PnL: what they would have made if held
};
export type SwabPositionsResponse = Omit<
  components['schemas']['PositionsResponse'],
  'positions'
> & {
  positions: SwabPosition[];
};
export type SwabWalletSummary = components['schemas']['WalletSummaryResponse'];
export type SwabCheckResult = components['schemas']['CheckResultResponse'];

/**
 * Get SWAB settings
 */
export async function getSwabSettings(): Promise<SwabSettings> {
  const res = await fetch(`${API_BASE_URL}/api/swab/settings`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch SWAB settings');
  }

  return res.json();
}

/**
 * Update SWAB settings
 */
export async function updateSwabSettings(settings: {
  auto_check_enabled?: boolean;
  check_interval_minutes?: number;
  daily_credit_budget?: number;
  stale_threshold_minutes?: number;
  min_token_count?: number;
}): Promise<SwabSettings> {
  const res = await fetch(`${API_BASE_URL}/api/swab/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  });

  if (!res.ok) {
    const errorText = await res.text();
    console.error('SWAB settings update failed:', res.status, errorText);
    throw new Error(
      `Failed to update SWAB settings: ${res.status} - ${errorText}`
    );
  }

  return res.json();
}

/**
 * Get SWAB statistics
 */
export async function getSwabStats(): Promise<SwabStats> {
  const res = await fetch(`${API_BASE_URL}/api/swab/stats`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch SWAB stats');
  }

  return res.json();
}

/**
 * Get SWAB scheduler status
 */
export async function getSwabSchedulerStatus(): Promise<{
  running: boolean;
  auto_check_enabled: boolean;
  check_interval_minutes: number;
  last_check_at: string | null;
  next_check_at: string | null;
}> {
  const res = await fetch(`${API_BASE_URL}/api/swab/scheduler/status`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch scheduler status');
  }

  return res.json();
}

/**
 * Get SWAB positions with filters
 */
export async function getSwabPositions(params?: {
  min_token_count?: number;
  status?: 'holding' | 'sold' | 'stale' | 'all';
  pnl_min?: number;
  pnl_max?: number;
  limit?: number;
  offset?: number;
}): Promise<SwabPositionsResponse> {
  const searchParams = new URLSearchParams();

  if (params?.min_token_count)
    searchParams.set('min_token_count', String(params.min_token_count));
  if (params?.status) searchParams.set('status', params.status);
  if (params?.pnl_min !== undefined)
    searchParams.set('pnl_min', String(params.pnl_min));
  if (params?.pnl_max !== undefined)
    searchParams.set('pnl_max', String(params.pnl_max));
  if (params?.limit) searchParams.set('limit', String(params.limit));
  if (params?.offset !== undefined)
    searchParams.set('offset', String(params.offset));

  const query = searchParams.toString();
  const url = `${API_BASE_URL}/api/swab/positions${query ? `?${query}` : ''}`;

  const res = await fetch(url, { cache: 'no-store' });

  if (!res.ok) {
    throw new Error('Failed to fetch SWAB positions');
  }

  return res.json();
}

/**
 * Get SWAB wallet summaries
 */
export async function getSwabWalletSummaries(
  min_token_count?: number
): Promise<SwabWalletSummary[]> {
  const url = min_token_count
    ? `${API_BASE_URL}/api/swab/wallets?min_token_count=${min_token_count}`
    : `${API_BASE_URL}/api/swab/wallets`;

  const res = await fetch(url, { cache: 'no-store' });

  if (!res.ok) {
    throw new Error('Failed to fetch SWAB wallet summaries');
  }

  return res.json();
}

/**
 * Stop tracking a position
 */
export async function stopSwabPositionTracking(
  positionId: number,
  reason: string = 'manual'
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(
    `${API_BASE_URL}/api/swab/positions/${positionId}/stop`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason })
    }
  );

  if (!res.ok) {
    throw new Error('Failed to stop position tracking');
  }

  return res.json();
}

/**
 * Resume tracking a position
 */
export async function resumeSwabPositionTracking(
  positionId: number
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(
    `${API_BASE_URL}/api/swab/positions/${positionId}/resume`,
    {
      method: 'POST'
    }
  );

  if (!res.ok) {
    throw new Error('Failed to resume position tracking');
  }

  return res.json();
}

/**
 * Stop tracking all positions for a wallet
 */
export async function stopSwabWalletTracking(
  walletAddress: string,
  reason: string = 'manual'
): Promise<{ success: boolean; message: string; positions_stopped: number }> {
  const res = await fetch(
    `${API_BASE_URL}/api/swab/wallets/${walletAddress}/stop`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason })
    }
  );

  if (!res.ok) {
    throw new Error('Failed to stop wallet tracking');
  }

  return res.json();
}

/**
 * Batch stop tracking multiple positions at once
 */
export async function batchStopSwabPositions(
  positionIds: number[],
  reason: string = 'manual'
): Promise<{
  success: boolean;
  positions_stopped: number;
  failed_ids: number[];
  message: string;
}> {
  const res = await fetch(`${API_BASE_URL}/api/swab/positions/batch-stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ position_ids: positionIds, reason })
  });

  if (!res.ok) {
    throw new Error('Failed to batch stop positions');
  }

  return res.json();
}

/**
 * Trigger manual position check
 */
export async function triggerSwabCheck(params?: {
  max_positions?: number;
  max_credits?: number;
}): Promise<SwabCheckResult> {
  const searchParams = new URLSearchParams();

  if (params?.max_positions)
    searchParams.set('max_positions', String(params.max_positions));
  if (params?.max_credits)
    searchParams.set('max_credits', String(params.max_credits));

  const query = searchParams.toString();
  const url = `${API_BASE_URL}/api/swab/check${query ? `?${query}` : ''}`;

  const res = await fetch(url, { method: 'POST' });

  if (!res.ok) {
    throw new Error('Failed to trigger position check');
  }

  return res.json();
}

/**
 * Trigger PnL ratio update (free operation)
 */
export async function triggerSwabPnlUpdate(): Promise<{
  success: boolean;
  tokens_updated: number;
  positions_updated: number;
  duration_ms: number;
}> {
  const res = await fetch(`${API_BASE_URL}/api/swab/update-pnl`, {
    method: 'POST'
  });

  if (!res.ok) {
    throw new Error('Failed to trigger PnL update');
  }

  return res.json();
}

export async function purgeSwabData(): Promise<{
  success: boolean;
  positions_deleted: number;
  metrics_deleted: number;
}> {
  const res = await fetch(`${API_BASE_URL}/api/swab/purge`, {
    method: 'POST'
  });

  if (!res.ok) {
    throw new Error('Failed to purge SWAB data');
  }

  return res.json();
}

// Reconciliation types and functions
export interface ReconciliationResultItem {
  wallet_address: string;
  token_symbol: string;
  status: 'success' | 'no_tx_found' | 'error';
  old_pnl_ratio: number | null;
  new_pnl_ratio: number | null;
  tokens_sold: number | null;
  usd_received: number | null;
  error_message: string | null;
}

export interface ReconciliationResponse {
  positions_found: number;
  positions_reconciled: number;
  positions_no_tx_found: number;
  positions_error: number;
  credits_used: number;
  results: ReconciliationResultItem[];
}

/**
 * Reconcile sold positions for a specific token using Helius transaction history.
 * Fixes positions where sell was never recorded with actual price data.
 */
export async function reconcileTokenPositions(
  tokenId: number,
  maxSignatures: number = 50
): Promise<ReconciliationResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/swab/reconcile/${tokenId}?max_signatures=${maxSignatures}`,
    { method: 'POST' }
  );

  if (!res.ok) {
    throw new Error('Failed to reconcile positions');
  }

  return res.json();
}

/**
 * Reconcile all sold positions across all tokens that need reconciliation.
 */
export async function reconcileAllPositions(params?: {
  max_signatures?: number;
  max_positions?: number;
}): Promise<ReconciliationResponse> {
  const searchParams = new URLSearchParams();
  if (params?.max_signatures)
    searchParams.set('max_signatures', params.max_signatures.toString());
  if (params?.max_positions)
    searchParams.set('max_positions', params.max_positions.toString());

  const url = searchParams.toString()
    ? `${API_BASE_URL}/api/swab/reconcile-all?${searchParams}`
    : `${API_BASE_URL}/api/swab/reconcile-all`;

  const res = await fetch(url, { method: 'POST' });

  if (!res.ok) {
    throw new Error('Failed to reconcile positions');
  }

  return res.json();
}

// ============================================================================
// Ingest Pipeline API
// ============================================================================

export interface IngestSettings {
  mc_min: number;
  volume_min: number;
  liquidity_min: number;
  age_max_hours: number;
  tier0_max_tokens_per_run: number;
  tier1_batch_size: number;
  tier1_credit_budget_per_run: number;
  ingest_enabled: boolean;
  enrich_enabled: boolean;
  auto_promote_enabled: boolean;
  hot_refresh_enabled: boolean;
  auto_promote_max_per_run: number;
  hot_refresh_age_hours: number;
  hot_refresh_max_tokens: number;
  // Performance scoring settings
  score_enabled: boolean;
  performance_prime_threshold: number;
  performance_monitor_threshold: number;
  control_cohort_daily_quota: number;
  score_weights: Record<string, number>;
  // Run tracking
  last_tier0_run_at: string | null;
  last_tier1_run_at: string | null;
  last_tier1_credits_used: number;
  last_hot_refresh_at: string | null;
  last_score_run_at: string | null;
  last_control_cohort_run_at: string | null;
}

export interface IngestQueueEntry {
  token_address: string;
  token_name: string | null;
  token_symbol: string | null;
  first_seen_at: string | null;
  source: string;
  tier: 'ingested' | 'enriched' | 'analyzed' | 'discarded';
  status: 'pending' | 'completed' | 'failed';
  ingested_at: string | null;
  enriched_at: string | null;
  analyzed_at: string | null;
  discarded_at: string | null;
  last_mc_usd: number | null;
  last_volume_usd: number | null;
  last_liquidity: number | null;
  age_hours: number | null;
  ingest_notes: string | null;
  last_error: string | null;
}

export interface IngestQueueResponse {
  total: number;
  by_tier: Record<string, number>;
  by_status: Record<string, number>;
  entries: IngestQueueEntry[];
}

export interface IngestQueueStats {
  total: number;
  by_tier: Record<string, number>;
  by_status: Record<string, number>;
  last_tier0_run_at: string | null;
  last_tier1_run_at: string | null;
  last_tier1_credits_used: number;
}

export interface IngestRunResult {
  tokens_fetched?: number;
  tokens_new?: number;
  tokens_updated?: number;
  tokens_skipped?: number;
  tokens_processed?: number;
  tokens_enriched?: number;
  tokens_failed?: number;
  tokens_promoted?: number;
  credits_used?: number;
  errors: string[];
  started_at: string;
  completed_at: string | null;
}

/**
 * Get ingest pipeline settings
 */
export async function getIngestSettings(): Promise<IngestSettings> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/settings`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch ingest settings');
  }

  return res.json();
}

/**
 * Update ingest pipeline settings
 */
export async function updateIngestSettings(
  settings: Partial<IngestSettings>
): Promise<{ status: string; settings: IngestSettings }> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  });

  if (!res.ok) {
    throw new Error('Failed to update ingest settings');
  }

  return res.json();
}

/**
 * Get ingest queue entries
 */
export async function getIngestQueue(params?: {
  tier?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<IngestQueueResponse> {
  const searchParams = new URLSearchParams();
  if (params?.tier) searchParams.set('tier', params.tier);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.offset) searchParams.set('offset', params.offset.toString());

  const url = searchParams.toString()
    ? `${API_BASE_URL}/api/ingest/queue?${searchParams}`
    : `${API_BASE_URL}/api/ingest/queue`;

  const res = await fetch(url, { cache: 'no-store' });

  if (!res.ok) {
    throw new Error('Failed to fetch ingest queue');
  }

  return res.json();
}

/**
 * Get ingest queue statistics
 */
export async function getIngestQueueStats(): Promise<IngestQueueStats> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/queue/stats`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch ingest queue stats');
  }

  return res.json();
}

/**
 * Trigger Tier-0 ingestion (DexScreener, free)
 */
export async function runTier0Ingestion(params?: {
  max_tokens?: number;
  mc_min?: number;
  volume_min?: number;
  liquidity_min?: number;
  age_max_hours?: number;
}): Promise<{ status: string; result: IngestRunResult }> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/run-tier0`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: params ? JSON.stringify(params) : '{}'
  });

  if (!res.ok) {
    throw new Error('Failed to run Tier-0 ingestion');
  }

  return res.json();
}

/**
 * Trigger Tier-1 enrichment (Helius, budgeted)
 */
export async function runTier1Enrichment(params?: {
  batch_size?: number;
  credit_budget?: number;
  mc_min?: number;
  volume_min?: number;
  liquidity_min?: number;
  age_max_hours?: number;
}): Promise<{ status: string; result: IngestRunResult }> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/run-tier1`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: params ? JSON.stringify(params) : '{}'
  });

  if (!res.ok) {
    throw new Error('Failed to run Tier-1 enrichment');
  }

  return res.json();
}

/**
 * Promote tokens from enriched tier to full analysis
 */
export async function promoteTokens(
  tokenAddresses: string[]
): Promise<{ status: string; result: IngestRunResult }> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_addresses: tokenAddresses })
  });

  if (!res.ok) {
    throw new Error('Failed to promote tokens');
  }

  return res.json();
}

/**
 * Discard tokens from the ingest queue
 */
export async function discardTokens(
  tokenAddresses: string[],
  reason: string = 'manual'
): Promise<{ status: string; discarded: number }> {
  const res = await fetch(`${API_BASE_URL}/api/ingest/discard`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_addresses: tokenAddresses, reason })
  });

  if (!res.ok) {
    throw new Error('Failed to discard tokens');
  }

  return res.json();
}
