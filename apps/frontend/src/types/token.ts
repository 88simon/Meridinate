/**
 * Token Types with SWAB Extensions
 *
 * Extends the generated Token type with SWAB-driven refresh fields and labels.
 */

import { components } from '@/lib/generated/api-types';

// Base Token type from generated API types
export type BaseToken = components['schemas']['Token'];
export type BaseTokenDetail = components['schemas']['TokenDetail'];

// SWAB aggregate fields added to token responses (optional since generated types don't include them)
export interface SwabFields {
  /** Count of open positions (still_holding=1) */
  swab_open_positions?: number;
  /** Unrealized PnL from open positions (USD) */
  swab_open_pnl_usd?: number | null;
  /** Realized PnL from closed positions (USD) */
  swab_realized_pnl_usd?: number | null;
  /** Latest position_checked_at timestamp for token */
  swab_last_check_at?: string | null;
  /** Whether token has active webhook */
  swab_webhook_active?: boolean;
  /** Combined auto labels (auto:*) and manual tags (tag:*) */
  labels?: string[];
  /** Computed next MC refresh time (ISO timestamp) */
  next_refresh_at?: string | null;
  /** Whether token is in fast-lane (SWAB exposure or high MC) */
  is_fast_lane?: boolean;
}

// Extended Token type with SWAB fields
export type Token = BaseToken & SwabFields;

// Extended TokenDetail type with SWAB fields
export type TokenDetail = BaseTokenDetail & SwabFields;

// ============================================================================
// Label Helpers
// ============================================================================

/** Auto label prefixes */
export const AUTO_LABEL_PREFIX = 'auto:';
export const TAG_LABEL_PREFIX = 'tag:';

/** Known auto labels */
export type AutoLabel =
  | 'auto:Manual'
  | 'auto:TIP'
  | 'auto:SWAB-Tracked'
  | 'auto:No-Positions'
  | 'auto:Exited'
  | 'auto:MC>100k'
  | 'auto:Low-Liquidity'
  | 'auto:Dormant'
  | 'auto:Discarded';

/** Filter-friendly label categories */
export const LABEL_CATEGORIES = {
  source: ['auto:Manual', 'auto:TIP'],
  swab: ['auto:SWAB-Tracked', 'auto:No-Positions', 'auto:Exited'],
  market: ['auto:MC>100k', 'auto:Low-Liquidity'],
  status: ['auto:Dormant', 'auto:Discarded']
} as const;

/** Labels available for filtering in UI */
export const FILTERABLE_LABELS: AutoLabel[] = [
  'auto:SWAB-Tracked',
  'auto:MC>100k',
  'auto:Low-Liquidity',
  'auto:Dormant',
  'auto:Discarded'
];

/**
 * Check if a label is an auto label
 */
export function isAutoLabel(label: string): boolean {
  return label.startsWith(AUTO_LABEL_PREFIX);
}

/**
 * Check if a label is a manual tag
 */
export function isManualTag(label: string): boolean {
  return label.startsWith(TAG_LABEL_PREFIX);
}

/**
 * Extract the display name from a label (removes prefix)
 */
export function getLabelDisplayName(label: string): string {
  if (label.startsWith(AUTO_LABEL_PREFIX)) {
    return label.slice(AUTO_LABEL_PREFIX.length);
  }
  if (label.startsWith(TAG_LABEL_PREFIX)) {
    return label.slice(TAG_LABEL_PREFIX.length);
  }
  return label;
}

/**
 * Get the appropriate color variant for a label
 */
export function getLabelVariant(
  label: string
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (label === 'auto:SWAB-Tracked' || label === 'auto:MC>100k') {
    return 'default';
  }
  if (label === 'auto:Discarded' || label === 'auto:Low-Liquidity') {
    return 'destructive';
  }
  if (label === 'auto:Dormant' || label === 'auto:Exited') {
    return 'secondary';
  }
  if (label.startsWith(TAG_LABEL_PREFIX)) {
    return 'outline';
  }
  return 'secondary';
}
