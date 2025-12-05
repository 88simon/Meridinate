"""
Ingest Settings Models

Single source of truth for ingest pipeline settings schemas and defaults.
Used by both the settings persistence layer and API endpoints.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# Score Weights Schema
# ============================================================================


class ScoreWeights(BaseModel):
    """Configurable weights for performance scoring rules"""

    # MC/Price momentum rules
    mc_change_30m_50pct: int = Field(default=15, description="+points if MC change 30m >= +50%")
    mc_change_2h_30pct: int = Field(default=10, description="+points if MC change 2h >= +30%")
    drawdown_35pct: int = Field(default=-10, description="points if drawdown >= 35%")

    # Liquidity rules
    liquidity_up_30pct: int = Field(default=10, description="+points if liquidity >= first_seen * 1.3")
    liquidity_down_40pct: int = Field(default=-15, description="points if liquidity < first_seen * 0.6")

    # Volume rules
    volume_24h_100k: int = Field(default=10, description="+points if volume_24h >= $100k")
    volume_24h_10k: int = Field(default=-10, description="points if volume_24h < $10k")

    # Holder quality rules
    high_win_rate_3plus: int = Field(default=12, description="+points if >= 3 high-win-rate wallets")
    high_win_rate_1_2: int = Field(default=6, description="+points if 1-2 high-win-rate wallets")
    top_holder_concentrated: int = Field(default=-8, description="points if top_holder_share > 0.45")

    # Age/lock rules
    young_unlocked_lp: int = Field(default=-10, description="points if age < 1h and lp_locked=false")

    # PnL feedback rules
    positions_positive_pnl: int = Field(default=8, description="+points if our_positions_pnl > 0")
    positions_negative_pnl: int = Field(default=-8, description="points if our_positions_pnl < 0")


# ============================================================================
# Default Values
# ============================================================================


DEFAULT_SCORE_WEIGHTS: dict = {
    "mc_change_30m_50pct": 15,
    "mc_change_2h_30pct": 10,
    "drawdown_35pct": -10,
    "liquidity_up_30pct": 10,
    "liquidity_down_40pct": -15,
    "volume_24h_100k": 10,
    "volume_24h_10k": -10,
    "high_win_rate_3plus": 12,
    "high_win_rate_1_2": 6,
    "top_holder_concentrated": -8,
    "young_unlocked_lp": -10,
    "positions_positive_pnl": 8,
    "positions_negative_pnl": -8,
}

DEFAULT_INGEST_SETTINGS: dict = {
    # Threshold filters for discovery
    "mc_min": 10000,  # Minimum market cap in USD
    "volume_min": 5000,  # Minimum 24h volume in USD
    "liquidity_min": 5000,  # Minimum liquidity in USD
    "age_max_hours": 48,  # Maximum token age in hours
    # Discovery scheduler settings (renamed from tier0)
    "discovery_enabled": False,  # Enable Discovery (DexScreener) ingestion
    "discovery_interval_minutes": 60,  # Discovery scheduler interval
    "discovery_max_per_run": 50,  # Max tokens to discover per run
    # Auto-promote settings
    "auto_promote_enabled": False,  # Auto-promote discovered tokens to full analysis
    "auto_promote_max_per_run": 5,  # Max tokens to auto-promote per run
    # Bypass limits flag
    "bypass_limits": False,  # Bypass UI/backend validation caps
    # Tracking & Refresh settings (renamed from SWAB-driven refresh)
    "tracking_mc_threshold": 100000,  # Tokens with MC >= this get fast refresh (USD)
    "fast_lane_interval_minutes": 30,  # Refresh interval for fast-lane tokens (30m)
    "slow_lane_interval_minutes": 240,  # Refresh interval for slow-lane tokens (4h)
    "slow_lane_enabled": True,  # Enable slow-lane refresh (can be turned off)
    # Drop conditions for tracking
    "drop_if_mc_below_threshold": False,  # Drop from refresh if MC < threshold
    "drop_if_no_swab_positions": False,  # Drop from refresh if no SWAB positions
    "drop_condition_mode": "AND",  # AND = both conditions, OR = either condition
    # Stale thresholds for warnings
    "stale_threshold_hours": 4,  # Consider data stale if last refresh > this
    "dormant_threshold_hours": 72,  # Tokens with no activity beyond this are "Dormant"
    "low_liquidity_threshold": 20000,  # Tokens with liquidity < this get "Low-Liquidity" label (USD)
    # Performance scoring settings
    "score_enabled": False,  # Enable performance scoring after refresh
    "performance_prime_threshold": 65,  # Score >= this -> Prime bucket
    "performance_monitor_threshold": 40,  # Score >= this (but < prime) -> Monitor; below -> Cull
    "control_cohort_daily_quota": 5,  # Random low-score tokens to track daily
    "score_weights": DEFAULT_SCORE_WEIGHTS.copy(),
    # Run tracking (read-only, managed by scheduler)
    "last_discovery_run_at": None,
    "last_refresh_run_at": None,
    "last_score_run_at": None,
    "last_control_cohort_run_at": None,
    # Legacy fields (kept for backward compatibility during migration)
    "ingest_enabled": False,  # Deprecated: use discovery_enabled
    "tier0_interval_minutes": 60,  # Deprecated: use discovery_interval_minutes
    "tier0_max_tokens_per_run": 50,  # Deprecated: use discovery_max_per_run
    "enrich_enabled": False,  # Deprecated: tier-1 removed
    "tier1_batch_size": 10,  # Deprecated: tier-1 removed
    "tier1_credit_budget_per_run": 100,  # Deprecated: tier-1 removed
    "hot_refresh_enabled": False,  # Deprecated: use tracking settings
    "hot_refresh_age_hours": 48,  # Deprecated
    "hot_refresh_max_tokens": 100,  # Deprecated
    "fast_lane_mc_threshold": 100000,  # Deprecated: use tracking_mc_threshold
    "last_tier0_run_at": None,  # Deprecated: use last_discovery_run_at
    "last_tier1_run_at": None,  # Deprecated
    "last_tier1_credits_used": 0,  # Deprecated
    "last_hot_refresh_at": None,  # Deprecated: use last_refresh_run_at
}


# ============================================================================
# Pydantic Schemas
# ============================================================================


class IngestSettings(BaseModel):
    """Settings for the Discovery → Queue → Analysis pipeline"""

    # Threshold filters for discovery
    mc_min: float = Field(default=10000, ge=0, description="Minimum market cap in USD")
    volume_min: float = Field(default=5000, ge=0, description="Minimum 24h volume in USD")
    liquidity_min: float = Field(default=5000, ge=0, description="Minimum liquidity in USD")
    age_max_hours: float = Field(default=48, ge=1, description="Maximum token age in hours")

    # Discovery scheduler settings
    discovery_enabled: bool = Field(default=False, description="Enable Discovery (DexScreener) ingestion")
    discovery_interval_minutes: int = Field(default=60, ge=5, description="Discovery scheduler interval (min)")
    discovery_max_per_run: int = Field(default=50, ge=1, description="Max tokens to discover per run")

    # Auto-promote settings
    auto_promote_enabled: bool = Field(default=False, description="Auto-promote discovered tokens to analysis")
    auto_promote_max_per_run: int = Field(default=5, ge=1, description="Max tokens to auto-promote per run")

    # Bypass limits flag
    bypass_limits: bool = Field(default=False, description="Bypass UI/backend validation caps")

    # Tracking & Refresh settings
    tracking_mc_threshold: float = Field(default=100000, ge=0, description="MC threshold for fast-lane refresh (USD)")
    fast_lane_interval_minutes: int = Field(default=30, ge=5, description="Refresh interval for fast-lane tokens (min)")
    slow_lane_interval_minutes: int = Field(default=240, ge=15, description="Refresh interval for slow-lane tokens (min)")
    slow_lane_enabled: bool = Field(default=True, description="Enable slow-lane refresh")

    # Drop conditions for tracking
    drop_if_mc_below_threshold: bool = Field(default=False, description="Drop from refresh if MC < threshold")
    drop_if_no_swab_positions: bool = Field(default=False, description="Drop from refresh if no SWAB positions")
    drop_condition_mode: str = Field(default="AND", description="Drop condition mode: AND or OR")

    # Stale/dormant thresholds
    stale_threshold_hours: int = Field(default=4, ge=1, description="Data stale if last refresh > this (hours)")
    dormant_threshold_hours: int = Field(default=72, ge=1, description="No activity threshold for Dormant label (hours)")
    low_liquidity_threshold: float = Field(default=20000, ge=0, description="Liquidity threshold for Low-Liquidity label (USD)")

    # Performance scoring settings
    score_enabled: bool = Field(default=False, description="Enable performance scoring")
    performance_prime_threshold: int = Field(default=65, ge=0, le=100, description="Score >= this = Prime")
    performance_monitor_threshold: int = Field(default=40, ge=0, le=100, description="Score >= this = Monitor")
    control_cohort_daily_quota: int = Field(default=5, ge=0, description="Low-score tokens to track daily")
    score_weights: Optional[dict] = Field(default=None, description="Configurable score weights")

    # Run tracking (read-only)
    last_discovery_run_at: Optional[str] = None
    last_refresh_run_at: Optional[str] = None
    last_score_run_at: Optional[str] = None
    last_control_cohort_run_at: Optional[str] = None

    # Legacy fields (backward compatibility)
    ingest_enabled: Optional[bool] = Field(default=None, description="Deprecated: use discovery_enabled")
    tier0_interval_minutes: Optional[int] = Field(default=None, description="Deprecated: use discovery_interval_minutes")
    tier0_max_tokens_per_run: Optional[int] = Field(default=None, description="Deprecated: use discovery_max_per_run")
    enrich_enabled: Optional[bool] = Field(default=None, description="Deprecated: tier-1 removed")
    tier1_batch_size: Optional[int] = Field(default=None, description="Deprecated: tier-1 removed")
    tier1_credit_budget_per_run: Optional[int] = Field(default=None, description="Deprecated: tier-1 removed")
    hot_refresh_enabled: Optional[bool] = Field(default=None, description="Deprecated: use tracking settings")
    hot_refresh_age_hours: Optional[float] = Field(default=None, description="Deprecated")
    hot_refresh_max_tokens: Optional[int] = Field(default=None, description="Deprecated")
    fast_lane_mc_threshold: Optional[float] = Field(default=None, description="Deprecated: use tracking_mc_threshold")
    last_tier0_run_at: Optional[str] = None
    last_tier1_run_at: Optional[str] = None
    last_tier1_credits_used: Optional[int] = None
    last_hot_refresh_at: Optional[str] = None


class IngestSettingsUpdate(BaseModel):
    """Request model for updating ingest settings (partial update)"""

    # Threshold filters
    mc_min: Optional[float] = Field(None, ge=0)
    volume_min: Optional[float] = Field(None, ge=0)
    liquidity_min: Optional[float] = Field(None, ge=0)
    age_max_hours: Optional[float] = Field(None, ge=1)

    # Discovery settings
    discovery_enabled: Optional[bool] = None
    discovery_interval_minutes: Optional[int] = Field(None, ge=5)
    discovery_max_per_run: Optional[int] = Field(None, ge=1)

    # Auto-promote settings
    auto_promote_enabled: Optional[bool] = None
    auto_promote_max_per_run: Optional[int] = Field(None, ge=1)

    # Bypass limits
    bypass_limits: Optional[bool] = None

    # Tracking & Refresh settings
    tracking_mc_threshold: Optional[float] = Field(None, ge=0)
    fast_lane_interval_minutes: Optional[int] = Field(None, ge=5)
    slow_lane_interval_minutes: Optional[int] = Field(None, ge=15)
    slow_lane_enabled: Optional[bool] = None

    # Drop conditions
    drop_if_mc_below_threshold: Optional[bool] = None
    drop_if_no_swab_positions: Optional[bool] = None
    drop_condition_mode: Optional[str] = None

    # Stale/dormant thresholds
    stale_threshold_hours: Optional[int] = Field(None, ge=1)
    dormant_threshold_hours: Optional[int] = Field(None, ge=1)
    low_liquidity_threshold: Optional[float] = Field(None, ge=0)

    # Performance scoring settings
    score_enabled: Optional[bool] = None
    performance_prime_threshold: Optional[int] = Field(None, ge=0, le=100)
    performance_monitor_threshold: Optional[int] = Field(None, ge=0, le=100)
    control_cohort_daily_quota: Optional[int] = Field(None, ge=0)
    score_weights: Optional[dict] = None

    # Legacy fields (backward compatibility - these map to new fields)
    ingest_enabled: Optional[bool] = None  # Maps to discovery_enabled
    tier0_interval_minutes: Optional[int] = Field(None, ge=5)  # Maps to discovery_interval_minutes
    tier0_max_tokens_per_run: Optional[int] = Field(None, ge=1)  # Maps to discovery_max_per_run
    enrich_enabled: Optional[bool] = None  # Deprecated
    tier1_batch_size: Optional[int] = Field(None, ge=1)  # Deprecated
    tier1_credit_budget_per_run: Optional[int] = Field(None, ge=1)  # Deprecated
    hot_refresh_enabled: Optional[bool] = None  # Deprecated
    hot_refresh_age_hours: Optional[float] = Field(None, ge=1)  # Deprecated
    hot_refresh_max_tokens: Optional[int] = Field(None, ge=1)  # Deprecated
    fast_lane_mc_threshold: Optional[float] = Field(None, ge=0)  # Maps to tracking_mc_threshold
