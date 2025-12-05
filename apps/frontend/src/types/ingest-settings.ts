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

  // Discovery settings (new)
  discovery_enabled?: boolean;
  discovery_interval_minutes?: number;
  discovery_max_per_run?: number;

  // Tracking & Refresh settings (new)
  tracking_mc_threshold?: number;
  fast_lane_interval_minutes?: number;
  slow_lane_interval_minutes?: number;
  slow_lane_enabled?: boolean;

  // Drop conditions (new)
  drop_if_mc_below_threshold?: boolean;
  drop_if_no_swab_positions?: boolean;
  drop_condition_mode?: 'AND' | 'OR';

  // Stale/dormant thresholds
  stale_threshold_hours?: number;
  dormant_threshold_hours?: number;
  low_liquidity_threshold?: number;

  // Run tracking (new)
  last_discovery_run_at?: string | null;
  last_refresh_run_at?: string | null;

  // Legacy fields (backward compatibility)
  ingest_enabled?: boolean;
  tier0_interval_minutes?: number;
  tier0_max_tokens_per_run?: number;
  enrich_enabled?: boolean;
  tier1_batch_size?: number;
  tier1_credit_budget_per_run?: number;
  hot_refresh_enabled?: boolean;
  hot_refresh_age_hours?: number;
  hot_refresh_max_tokens?: number;
  fast_lane_mc_threshold?: number;
  last_tier0_run_at?: string | null;
  last_tier1_run_at?: string | null;
  last_tier1_credits_used?: number;
  last_hot_refresh_at?: string | null;
};

export type IngestSettingsUpdate =
  components['schemas']['IngestSettingsUpdate'] & {
    bypass_limits?: boolean;
    score_weights?: ScoreWeights;

    // Discovery settings (new)
    discovery_enabled?: boolean;
    discovery_interval_minutes?: number;
    discovery_max_per_run?: number;

    // Tracking & Refresh settings (new)
    tracking_mc_threshold?: number;
    fast_lane_interval_minutes?: number;
    slow_lane_interval_minutes?: number;
    slow_lane_enabled?: boolean;

    // Drop conditions (new)
    drop_if_mc_below_threshold?: boolean;
    drop_if_no_swab_positions?: boolean;
    drop_condition_mode?: 'AND' | 'OR';

    // Stale/dormant thresholds
    stale_threshold_hours?: number;
    dormant_threshold_hours?: number;
    low_liquidity_threshold?: number;

    // Legacy fields (backward compatibility)
    ingest_enabled?: boolean;
    tier0_interval_minutes?: number;
    tier0_max_tokens_per_run?: number;
    enrich_enabled?: boolean;
    tier1_batch_size?: number;
    tier1_credit_budget_per_run?: number;
    hot_refresh_enabled?: boolean;
    hot_refresh_age_hours?: number;
    hot_refresh_max_tokens?: number;
    fast_lane_mc_threshold?: number;
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
  // Threshold filters for discovery
  mc_min: 10000,
  volume_min: 5000,
  liquidity_min: 5000,
  age_max_hours: 48,

  // Discovery scheduler settings (new)
  discovery_enabled: false,
  discovery_interval_minutes: 60,
  discovery_max_per_run: 50,

  // Auto-promote settings
  auto_promote_enabled: false,
  auto_promote_max_per_run: 5,

  // Bypass limits flag
  bypass_limits: false,

  // Tracking & Refresh settings (new)
  tracking_mc_threshold: 100000,
  fast_lane_interval_minutes: 30,
  slow_lane_interval_minutes: 240,
  slow_lane_enabled: true,

  // Drop conditions (new)
  drop_if_mc_below_threshold: false,
  drop_if_no_swab_positions: false,
  drop_condition_mode: 'AND',

  // Stale/dormant thresholds
  stale_threshold_hours: 4,
  dormant_threshold_hours: 72,
  low_liquidity_threshold: 20000,

  // Performance scoring settings
  score_enabled: false,
  performance_prime_threshold: 65,
  performance_monitor_threshold: 40,
  control_cohort_daily_quota: 5,
  score_weights: { ...DEFAULT_SCORE_WEIGHTS },

  // Run tracking (new)
  last_discovery_run_at: null,
  last_refresh_run_at: null,
  last_score_run_at: null,
  last_control_cohort_run_at: null,

  // Legacy fields (backward compatibility)
  ingest_enabled: false,
  tier0_interval_minutes: 60,
  tier0_max_tokens_per_run: 50,
  enrich_enabled: false,
  tier1_batch_size: 10,
  tier1_credit_budget_per_run: 100,
  hot_refresh_enabled: false,
  hot_refresh_age_hours: 48,
  hot_refresh_max_tokens: 100,
  fast_lane_mc_threshold: 100000,
  last_tier0_run_at: null,
  last_tier1_run_at: null,
  last_tier1_credits_used: 0,
  last_hot_refresh_at: null
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

  // Discovery scheduler settings (new)
  discovery_interval_minutes: { min: 5, max: 1440 }, // 5 min to 24 hours
  discovery_max_per_run: { min: 1, max: 500 },

  // Auto-promote settings
  auto_promote_max_per_run: { min: 1, max: 50 },

  // Tracking & Refresh settings (new)
  tracking_mc_threshold: { min: 0, max: 10000000 },
  fast_lane_interval_minutes: { min: 5, max: 240 },
  slow_lane_interval_minutes: { min: 15, max: 1440 },

  // Stale/dormant thresholds
  stale_threshold_hours: { min: 1, max: 24 },
  dormant_threshold_hours: { min: 1, max: 168 },
  low_liquidity_threshold: { min: 0, max: 500000 },

  // Performance scoring
  performance_prime_threshold: { min: 0, max: 100 },
  performance_monitor_threshold: { min: 0, max: 100 },
  control_cohort_daily_quota: { min: 0, max: 50 },

  // Legacy fields (backward compatibility)
  tier0_interval_minutes: { min: 5, max: 1440 },
  tier0_max_tokens_per_run: { min: 1, max: 500 },
  tier1_batch_size: { min: 1, max: 100 },
  tier1_credit_budget_per_run: { min: 1, max: 1000 },
  hot_refresh_age_hours: { min: 1, max: 168 },
  hot_refresh_max_tokens: { min: 1, max: 500 },
  fast_lane_mc_threshold: { min: 0, max: 10000000 }
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
