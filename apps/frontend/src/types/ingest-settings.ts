/**
 * Ingest Settings Types and Defaults
 *
 * Single source of truth for frontend ingest settings types.
 * Mirrors the backend IngestSettings Pydantic schema.
 *
 * After backend changes, regenerate api-types.ts and update this file if needed.
 */

import { components } from '@/lib/generated/api-types';

// Re-export from generated types (base schema)
export type IngestSettings = components['schemas']['IngestSettings'] & {
  // Extended fields not yet in generated types
  bypass_limits?: boolean;
  score_weights?: ScoreWeights;
  last_control_cohort_run_at?: string | null;
};

export type IngestSettingsUpdate =
  components['schemas']['IngestSettingsUpdate'] & {
    bypass_limits?: boolean;
    score_weights?: ScoreWeights;
  };

// ============================================================================
// Score Weights
// ============================================================================

export interface ScoreWeights {
  // MC/Price momentum rules
  mc_change_30m_50pct: number;
  mc_change_2h_30pct: number;
  drawdown_35pct: number;

  // Liquidity rules
  liquidity_up_30pct: number;
  liquidity_down_40pct: number;

  // Volume rules
  volume_24h_100k: number;
  volume_24h_10k: number;

  // Holder quality rules
  high_win_rate_3plus: number;
  high_win_rate_1_2: number;
  top_holder_concentrated: number;

  // Age/lock rules
  young_unlocked_lp: number;

  // PnL feedback rules
  positions_positive_pnl: number;
  positions_negative_pnl: number;
}

// ============================================================================
// Default Values (mirrors backend DEFAULT_INGEST_SETTINGS)
// ============================================================================

export const DEFAULT_SCORE_WEIGHTS: ScoreWeights = {
  mc_change_30m_50pct: 15,
  mc_change_2h_30pct: 10,
  drawdown_35pct: -10,
  liquidity_up_30pct: 10,
  liquidity_down_40pct: -15,
  volume_24h_100k: 10,
  volume_24h_10k: -10,
  high_win_rate_3plus: 12,
  high_win_rate_1_2: 6,
  top_holder_concentrated: -8,
  young_unlocked_lp: -10,
  positions_positive_pnl: 8,
  positions_negative_pnl: -8
};

export const DEFAULT_INGEST_SETTINGS: IngestSettings = {
  // Threshold filters
  mc_min: 10000,
  volume_min: 5000,
  liquidity_min: 5000,
  age_max_hours: 48,

  // Scheduler intervals
  tier0_interval_minutes: 60,

  // Batch and budget limits
  tier0_max_tokens_per_run: 50,
  tier1_batch_size: 10,
  tier1_credit_budget_per_run: 100,

  // Feature flags
  ingest_enabled: false,
  enrich_enabled: false,
  auto_promote_enabled: false,
  hot_refresh_enabled: false,

  // Bypass limits flag
  bypass_limits: false,

  // Auto-promote settings
  auto_promote_max_per_run: 5,

  // Hot refresh settings
  hot_refresh_age_hours: 48,
  hot_refresh_max_tokens: 100,

  // Performance scoring settings
  score_enabled: false,
  performance_prime_threshold: 65,
  performance_monitor_threshold: 40,
  control_cohort_daily_quota: 5,
  score_weights: { ...DEFAULT_SCORE_WEIGHTS },

  // Run tracking (read-only)
  last_tier0_run_at: null,
  last_tier1_run_at: null,
  last_tier1_credits_used: 0,
  last_hot_refresh_at: null,
  last_score_run_at: null,
  last_control_cohort_run_at: null
};

// ============================================================================
// Slider/Input Limits (when bypass_limits is false)
// ============================================================================

export const INGEST_LIMITS = {
  // Threshold filters
  mc_min: { min: 0, max: 1000000 },
  volume_min: { min: 0, max: 500000 },
  liquidity_min: { min: 0, max: 500000 },
  age_max_hours: { min: 1, max: 168 }, // up to 1 week

  // Scheduler intervals
  tier0_interval_minutes: { min: 5, max: 1440 }, // 5 min to 24 hours

  // Batch and budget limits
  tier0_max_tokens_per_run: { min: 1, max: 500 },
  tier1_batch_size: { min: 1, max: 100 },
  tier1_credit_budget_per_run: { min: 1, max: 1000 },

  // Auto-promote settings
  auto_promote_max_per_run: { min: 1, max: 50 },

  // Hot refresh settings
  hot_refresh_age_hours: { min: 1, max: 168 },
  hot_refresh_max_tokens: { min: 1, max: 500 },

  // Performance scoring
  performance_prime_threshold: { min: 0, max: 100 },
  performance_monitor_threshold: { min: 0, max: 100 },
  control_cohort_daily_quota: { min: 0, max: 50 }
} as const;

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Merge partial settings with defaults
 */
export function mergeWithDefaults(
  partial: Partial<IngestSettings>
): IngestSettings {
  return {
    ...DEFAULT_INGEST_SETTINGS,
    ...partial,
    score_weights: {
      ...DEFAULT_SCORE_WEIGHTS,
      ...(partial.score_weights || {})
    }
  };
}

/**
 * Check if a value exceeds the limit (when bypass_limits is false)
 */
export function exceedsLimit(
  field: keyof typeof INGEST_LIMITS,
  value: number,
  bypassLimits: boolean
): boolean {
  if (bypassLimits) return false;
  const limit = INGEST_LIMITS[field];
  return value < limit.min || value > limit.max;
}
