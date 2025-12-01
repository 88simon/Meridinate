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
    # Threshold filters for promotion
    "mc_min": 10000,  # Minimum market cap in USD
    "volume_min": 5000,  # Minimum 24h volume in USD
    "liquidity_min": 5000,  # Minimum liquidity in USD
    "age_max_hours": 48,  # Maximum token age in hours
    # Scheduler intervals
    "tier0_interval_minutes": 60,  # Tier-0 (DexScreener) scheduler interval
    # Batch and budget limits
    "tier0_max_tokens_per_run": 50,  # Max tokens to ingest per Tier-0 run
    "tier1_batch_size": 10,  # Max tokens to enrich per Tier-1 run
    "tier1_credit_budget_per_run": 100,  # Max Helius credits per Tier-1 run
    # Feature flags
    "ingest_enabled": False,  # Enable Tier-0 ingestion
    "enrich_enabled": False,  # Enable Tier-1 enrichment
    "auto_promote_enabled": False,  # Auto-promote enriched tokens to full analysis
    "hot_refresh_enabled": False,  # Enable hot token MC/volume refresh
    # Bypass limits flag
    "bypass_limits": False,  # Bypass UI/backend validation caps
    # Auto-promote settings
    "auto_promote_max_per_run": 5,  # Max tokens to auto-promote per run
    # Hot refresh settings
    "hot_refresh_age_hours": 48,  # Max age for hot tokens to refresh
    "hot_refresh_max_tokens": 100,  # Max tokens to refresh per run
    # Performance scoring settings
    "score_enabled": False,  # Enable performance scoring after hot refresh
    "performance_prime_threshold": 65,  # Score >= this -> Prime bucket
    "performance_monitor_threshold": 40,  # Score >= this (but < prime) -> Monitor; below -> Cull
    "control_cohort_daily_quota": 5,  # Random low-score tokens to track daily
    "score_weights": DEFAULT_SCORE_WEIGHTS.copy(),
    # Run tracking (read-only, managed by scheduler)
    "last_tier0_run_at": None,
    "last_tier1_run_at": None,
    "last_tier1_credits_used": 0,
    "last_hot_refresh_at": None,
    "last_score_run_at": None,
    "last_control_cohort_run_at": None,
}


# ============================================================================
# Pydantic Schemas
# ============================================================================


class IngestSettings(BaseModel):
    """Settings for the tiered token ingestion pipeline"""

    # Threshold filters
    mc_min: float = Field(default=10000, ge=0, description="Minimum market cap in USD")
    volume_min: float = Field(default=5000, ge=0, description="Minimum 24h volume in USD")
    liquidity_min: float = Field(default=5000, ge=0, description="Minimum liquidity in USD")
    age_max_hours: float = Field(default=48, ge=1, description="Maximum token age in hours")

    # Scheduler intervals
    tier0_interval_minutes: int = Field(default=60, ge=5, description="Tier-0 scheduler interval in minutes")

    # Batch and budget limits (no upper bounds when bypass_limits=True)
    tier0_max_tokens_per_run: int = Field(default=50, ge=1, description="Max tokens per Tier-0 run")
    tier1_batch_size: int = Field(default=10, ge=1, description="Max tokens per Tier-1 run")
    tier1_credit_budget_per_run: int = Field(default=100, ge=1, description="Max Helius credits per Tier-1 run")

    # Feature flags
    ingest_enabled: bool = Field(default=False, description="Enable Tier-0 ingestion")
    enrich_enabled: bool = Field(default=False, description="Enable Tier-1 enrichment")
    auto_promote_enabled: bool = Field(default=False, description="Auto-promote enriched tokens")
    hot_refresh_enabled: bool = Field(default=False, description="Enable hot token MC/volume refresh")

    # Bypass limits flag
    bypass_limits: bool = Field(default=False, description="Bypass UI/backend validation caps")

    # Auto-promote settings
    auto_promote_max_per_run: int = Field(default=5, ge=1, description="Max tokens to auto-promote per run")

    # Hot refresh settings
    hot_refresh_age_hours: float = Field(default=48, ge=1, description="Max age for hot tokens (hours)")
    hot_refresh_max_tokens: int = Field(default=100, ge=1, description="Max tokens to refresh per run")

    # Performance scoring settings
    score_enabled: bool = Field(default=False, description="Enable performance scoring")
    performance_prime_threshold: int = Field(default=65, ge=0, le=100, description="Score >= this = Prime")
    performance_monitor_threshold: int = Field(default=40, ge=0, le=100, description="Score >= this = Monitor")
    control_cohort_daily_quota: int = Field(default=5, ge=0, description="Low-score tokens to track daily")
    score_weights: Optional[dict] = Field(default=None, description="Configurable score weights")
    last_score_run_at: Optional[str] = None

    # Run tracking (read-only)
    last_tier0_run_at: Optional[str] = None
    last_tier1_run_at: Optional[str] = None
    last_tier1_credits_used: int = 0
    last_hot_refresh_at: Optional[str] = None
    last_control_cohort_run_at: Optional[str] = None


class IngestSettingsUpdate(BaseModel):
    """Request model for updating ingest settings (partial update)"""

    mc_min: Optional[float] = Field(None, ge=0)
    volume_min: Optional[float] = Field(None, ge=0)
    liquidity_min: Optional[float] = Field(None, ge=0)
    age_max_hours: Optional[float] = Field(None, ge=1)
    tier0_interval_minutes: Optional[int] = Field(None, ge=5)
    tier0_max_tokens_per_run: Optional[int] = Field(None, ge=1)
    tier1_batch_size: Optional[int] = Field(None, ge=1)
    tier1_credit_budget_per_run: Optional[int] = Field(None, ge=1)
    ingest_enabled: Optional[bool] = None
    enrich_enabled: Optional[bool] = None
    auto_promote_enabled: Optional[bool] = None
    hot_refresh_enabled: Optional[bool] = None
    bypass_limits: Optional[bool] = None
    auto_promote_max_per_run: Optional[int] = Field(None, ge=1)
    hot_refresh_age_hours: Optional[float] = Field(None, ge=1)
    hot_refresh_max_tokens: Optional[int] = Field(None, ge=1)
    # Performance scoring settings
    score_enabled: Optional[bool] = None
    performance_prime_threshold: Optional[int] = Field(None, ge=0, le=100)
    performance_monitor_threshold: Optional[int] = Field(None, ge=0, le=100)
    control_cohort_daily_quota: Optional[int] = Field(None, ge=0)
    score_weights: Optional[dict] = None
