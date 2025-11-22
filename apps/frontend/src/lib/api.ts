/**
 * Meridinate API Client
 * Fetches data from the FastAPI backend running on localhost:5003
 *
 * Uses auto-generated types from OpenAPI schema
 */

import { components } from './generated/api-types';

export const API_BASE_URL = 'http://localhost:5003';

// ============================================================================
// Type Exports (from generated schemas)
// ============================================================================

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

// Backwards compatibility - ApiSettings is now AnalysisSettings
export type ApiSettings = AnalysisSettings;

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
 * Fetch details for a specific token
 */
export async function getTokenById(id: number): Promise<TokenDetail> {
  const res = await fetch(`${API_BASE_URL}/api/tokens/${id}`, {
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error('Failed to fetch token details');
  }

  return res.json();
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
