/**
 * Token Types with Position Tracker Extensions
 *
 * Extends the generated Token type with position-tracker refresh fields and labels.
 */

import { components } from '@/lib/generated/api-types';

// Base Token type from generated API types
export type BaseToken = components['schemas']['Token'];
export type BaseTokenDetail = components['schemas']['TokenDetail'];

// Extended fields added to token responses (optional since generated types don't include them)
export interface SwabFields {
  /** Token liquidity in USD */
  liquidity_usd?: number | null;
  /** DEX/launchpad identifier */
  dex_id?: string | null;
  /** PumpFun cashback coin (true = cashback to traders, false = creator fees) */
  is_cashback?: boolean | null;
  /** Count of open tracked positions (still_holding=1) */
  swab_open_positions?: number;
  /** Unrealized PnL from open tracked positions (USD) */
  swab_open_pnl_usd?: number | null;
  /** Realized PnL from closed tracked positions (USD) */
  swab_realized_pnl_usd?: number | null;
  /** Latest position_checked_at timestamp for token */
  swab_last_check_at?: string | null;
  /** Whether token has active position-tracking webhook */
  swab_webhook_active?: boolean;
  /** Combined auto labels (auto:*) and manual tags (tag:*) */
  labels?: string[];
  /** Computed next MC refresh time (ISO timestamp) */
  next_refresh_at?: string | null;
  /** Whether token is in fast-lane (active positions or high MC) */
  is_fast_lane?: boolean;
  /** Wallet address that deployed/created this token */
  deployer_address?: string | null;
  /** JSON array of creation timeline events (CREATE, ADD_LIQUIDITY, FIRST_BUY) */
  creation_events_json?: string | null;
  /** Holder concentration change rate per hour */
  holder_velocity?: number | null;
  /** Whether the deployer is still a top holder */
  deployer_is_top_holder?: boolean | null;
  /** How many early buyers are also top holders */
  early_buyer_holder_overlap?: number | null;
  /** MC coefficient of variation (volatility) */
  mc_volatility?: number | null;
  /** Number of 30%+ MC drops that recovered */
  mc_recovery_count?: number | null;
  /** Smart money flow JSON (smart_buying, smart_selling, flow_direction) */
  smart_money_flow?: string | null;
  /** Average hold duration in hours for exited positions */
  avg_hold_hours?: number | null;
  /** Percentage of early buyers that are fresh wallets */
  fresh_wallet_pct?: number | null;
  /** When webhook first detected this token (before auto-scan) */
  webhook_detected_at?: string | null;
  /** Webhook conviction score at detection time */
  webhook_conviction_score?: number | null;
  /** Minutes between webhook detection and auto-scan pickup */
  time_to_migration_minutes?: number | null;
}

// Extended Token type with position tracker fields
export type Token = BaseToken & SwabFields;

// Extended TokenDetail type with position tracker fields
export type TokenDetail = BaseTokenDetail & SwabFields;

// ============================================================================
// Label Helpers
// ============================================================================

/** Label prefixes for the 3-tier system */
export const AUTO_LABEL_PREFIX = 'auto:';
export const SIGNAL_LABEL_PREFIX = 'signal:';
export const WIN_LABEL_PREFIX = 'win:';
export const TAG_LABEL_PREFIX = 'tag:';

/** Known auto labels (Tier 1: MC-based + operational) */
export type AutoLabel =
  // Source labels
  | 'auto:Manual'
  | 'auto:TIP'
  // Position tracking operational labels
  | 'auto:Position-Tracked'
  | 'auto:No-Positions'
  | 'auto:Exited'
  // MC-based performance labels (new)
  | 'auto:Mooning'
  | 'auto:Climbing'
  | 'auto:Stable'
  | 'auto:Declining'
  | 'auto:Dead'
  | 'auto:ATH'
  // Status labels
  | 'auto:Discarded';

/** Known signal labels (Tier 2: wallet-signal) */
export type SignalLabel =
  | 'signal:Smart-Money'
  | 'signal:Cluster-Alert'
  | 'signal:Insider-Heavy'
  | 'signal:Bot-Heavy'
  | 'signal:Whale-Backed'
  | 'signal:Smart-Bullish'
  | 'signal:Smart-Bearish';

/** Win multiplier labels (auto-computed with verdict) */
export type WinLabel =
  | 'win:3x'
  | 'win:5x'
  | 'win:10x'
  | 'win:25x'
  | 'win:50x'
  | 'win:100x';

/** Filter-friendly label categories */
export const LABEL_CATEGORIES = {
  source: ['auto:Manual', 'auto:TIP'],
  positions: ['auto:Position-Tracked', 'auto:No-Positions', 'auto:Exited'],
  performance: ['auto:Mooning', 'auto:Climbing', 'auto:Stable', 'auto:Declining', 'auto:Dead', 'auto:ATH'],
  signals: ['signal:Smart-Money', 'signal:Cluster-Alert', 'signal:Insider-Heavy', 'signal:Bot-Heavy', 'signal:Whale-Backed'],
  multiplier: ['win:3x', 'win:5x', 'win:10x', 'win:25x', 'win:50x', 'win:100x'],
  status: ['auto:Discarded']
} as const;

/** Labels available for filtering in UI */
export const FILTERABLE_LABELS: (AutoLabel | SignalLabel)[] = [
  'auto:Position-Tracked',
  'auto:Mooning',
  'auto:Climbing',
  'auto:Declining',
  'auto:Dead',
  'auto:ATH',
  'auto:Discarded',
  'signal:Smart-Money',
  'signal:Cluster-Alert',
  'signal:Insider-Heavy',
  'signal:Whale-Backed'
];

/**
 * Check if a label is an auto label
 */
export function isAutoLabel(label: string): boolean {
  return label.startsWith(AUTO_LABEL_PREFIX);
}

/**
 * Check if a label is a signal label
 */
export function isSignalLabel(label: string): boolean {
  return label.startsWith(SIGNAL_LABEL_PREFIX);
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
  if (label.startsWith(SIGNAL_LABEL_PREFIX)) {
    return label.slice(SIGNAL_LABEL_PREFIX.length);
  }
  if (label.startsWith(WIN_LABEL_PREFIX)) {
    return label.slice(WIN_LABEL_PREFIX.length).toUpperCase();
  }
  if (label.startsWith(TAG_LABEL_PREFIX)) {
    return label.slice(TAG_LABEL_PREFIX.length);
  }
  return label;
}

/**
 * Get custom className for win multiplier badges (green gradient by tier)
 */
export function getWinBadgeClass(label: string): string | null {
  switch (label) {
    case 'win:3x':
      return 'border-transparent bg-emerald-800/60 text-emerald-300';
    case 'win:5x':
      return 'border-transparent bg-emerald-700/60 text-emerald-200';
    case 'win:10x':
      return 'border-transparent bg-green-600/60 text-green-200';
    case 'win:25x':
      return 'border-transparent bg-lime-600/60 text-lime-200';
    case 'win:50x':
      return 'border-transparent bg-yellow-600/60 text-yellow-200';
    case 'win:100x':
      return 'border-transparent bg-amber-500/60 text-amber-100 font-bold';
    default:
      return null;
  }
}

/**
 * Get the appropriate color variant for a label
 */
export function getLabelVariant(
  label: string
): 'default' | 'secondary' | 'destructive' | 'outline' {
  // Win multiplier labels — use getWinBadgeClass() for custom styling
  if (label.startsWith('win:')) {
    return 'outline';
  }
  // Positive performance / signals
  if (label === 'auto:Mooning' || label === 'auto:ATH' || label === 'auto:Position-Tracked') {
    return 'default';
  }
  if (label === 'auto:Climbing' || label === 'auto:Stable') {
    return 'secondary';
  }
  // Negative performance
  if (label === 'auto:Declining' || label === 'auto:Dead' || label === 'auto:Discarded') {
    return 'destructive';
  }
  // Wallet signal labels
  if (label === 'signal:Smart-Money' || label === 'signal:Whale-Backed' || label === 'signal:Smart-Bullish') {
    return 'default';
  }
  if (label === 'signal:Cluster-Alert' || label === 'signal:Bot-Heavy' || label === 'signal:Smart-Bearish') {
    return 'destructive';
  }
  if (label === 'signal:Insider-Heavy') {
    return 'secondary';
  }
  // Operational
  if (label === 'auto:Exited' || label === 'auto:No-Positions') {
    return 'secondary';
  }
  // Manual tags
  if (label.startsWith(TAG_LABEL_PREFIX)) {
    return 'outline';
  }
  return 'secondary';
}
