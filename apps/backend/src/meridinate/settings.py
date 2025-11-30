"""
Configuration and settings management for Gun Del Sol

Centralizes loading of:
- Helius API key
- API settings (transaction limits, wallet count, etc.)
- File paths (database, results directories)
"""

import json
import os
from typing import Dict, Optional

# ============================================================================
# Directory Paths
# ============================================================================

# Get backend root directory (apps/backend/)
# settings.py is at apps/backend/src/meridinate/settings.py
# Go up 3 levels: meridinate -> src -> backend
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_FILE = os.path.join(BACKEND_ROOT, "data", "db", "analyzed_tokens.db")
SETTINGS_FILE = os.path.join(BACKEND_ROOT, "api_settings.json")
DATA_FILE = os.path.join(BACKEND_ROOT, "monitored_addresses.json")
ANALYSIS_RESULTS_DIR = os.path.join(BACKEND_ROOT, "data", "analysis_results")
AXIOM_EXPORTS_DIR = os.path.join(BACKEND_ROOT, "data", "axiom_exports")

# Ensure directories exist
os.makedirs(ANALYSIS_RESULTS_DIR, exist_ok=True)
os.makedirs(AXIOM_EXPORTS_DIR, exist_ok=True)

# ============================================================================
# Helius API Key Loading
# ============================================================================


def load_api_key() -> Optional[str]:
    """Load Helius API key from environment or config file"""
    # Try environment variable first
    api_key = os.environ.get("HELIUS_API_KEY")
    if api_key:
        return api_key

    # Try config.json (look in the backend root directory)
    config_file = os.path.join(BACKEND_ROOT, "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                return config.get("helius_api_key")
        except Exception as e:
            print(f"[Config] Error reading config.json: {e}")

    return None


HELIUS_API_KEY = load_api_key()
if not HELIUS_API_KEY:
    raise RuntimeError("HELIUS_API_KEY not set. Add it to environment variable or backend/config.json")

print(f"[Config] Loaded Helius API key: {HELIUS_API_KEY[:8]}..." if HELIUS_API_KEY else "[Config] No API key loaded")


def load_top_holders_api_key() -> Optional[str]:
    """Load separate Helius API key for Top Holders feature from environment or config file"""
    # Try environment variable first
    api_key = os.environ.get("HELIUS_TOP_HOLDERS_API_KEY")
    if api_key:
        return api_key

    # Try config.json (look in the backend root directory)
    config_file = os.path.join(BACKEND_ROOT, "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                return config.get("helius_top_holders_api_key")
        except Exception as e:
            print(f"[Config] Error reading config.json for top holders key: {e}")

    return None


HELIUS_TOP_HOLDERS_API_KEY = load_top_holders_api_key()
# Fallback to main API key if top holders key not set
if not HELIUS_TOP_HOLDERS_API_KEY:
    HELIUS_TOP_HOLDERS_API_KEY = HELIUS_API_KEY
    print("[Config] Using main Helius API key for Top Holders feature")
else:
    print(f"[Config] Loaded Top Holders API key: {HELIUS_TOP_HOLDERS_API_KEY[:8]}...")

# ============================================================================
# Redis Configuration (for task queue and rate limiting)
# ============================================================================

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
REDIS_ENABLED = os.environ.get("REDIS_ENABLED", "false").lower() == "true"
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "false").lower() == "true"

print(f"[Config] Redis URL: {REDIS_URL}")
print(f"[Config] Redis enabled: {REDIS_ENABLED}")
print(f"[Config] Rate limiting enabled: {RATE_LIMIT_ENABLED}")

# ============================================================================
# API Settings Management
# ============================================================================

DEFAULT_API_SETTINGS = {
    "transactionLimit": 500,
    "minUsdFilter": 50.0,
    "walletCount": 10,
    "apiRateDelay": 100,
    "maxCreditsPerAnalysis": 1000,
    "maxRetries": 3,
    "topHoldersLimit": 10,
}

DEFAULT_THRESHOLD = 100


def load_api_settings() -> Dict:
    """Load API settings from file, fallback to defaults"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                # Merge with defaults (file values override defaults)
                return {**DEFAULT_API_SETTINGS, **data}
        except Exception as e:
            print(f"[Config] Error reading api_settings.json: {e}")
            return DEFAULT_API_SETTINGS.copy()
    return DEFAULT_API_SETTINGS.copy()


def save_api_settings(settings: Dict) -> bool:
    """Save API settings to file"""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        print(f"[Config] API settings saved: {settings}")
        return True
    except Exception as exc:
        print(f"[Config] Failed to persist API settings: {exc}")
        return False


# Load settings on module import
CURRENT_API_SETTINGS = load_api_settings()
print(
    f"[Config] API Settings: walletCount={CURRENT_API_SETTINGS['walletCount']}, "
    f"transactionLimit={CURRENT_API_SETTINGS['transactionLimit']}, "
    f"maxCredits={CURRENT_API_SETTINGS['maxCreditsPerAnalysis']}"
)

# ============================================================================
# Ingest Settings Management (Tiered Token Discovery Pipeline)
# ============================================================================

INGEST_SETTINGS_FILE = os.path.join(BACKEND_ROOT, "ingest_settings.json")

DEFAULT_INGEST_SETTINGS = {
    # Threshold filters for promotion
    "mc_min": 10000,  # Minimum market cap in USD
    "volume_min": 5000,  # Minimum 24h volume in USD
    "liquidity_min": 5000,  # Minimum liquidity in USD
    "age_max_hours": 48,  # Maximum token age in hours
    # Batch and budget limits
    "tier0_max_tokens_per_run": 50,  # Max tokens to ingest per Tier-0 run
    "tier1_batch_size": 10,  # Max tokens to enrich per Tier-1 run
    "tier1_credit_budget_per_run": 100,  # Max Helius credits per Tier-1 run
    # Feature flags
    "ingest_enabled": False,  # Enable Tier-0 ingestion
    "enrich_enabled": False,  # Enable Tier-1 enrichment
    "auto_promote_enabled": False,  # Auto-promote enriched tokens to full analysis
    "hot_refresh_enabled": False,  # Enable hot token MC/volume refresh
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
    "score_weights": {
        # MC/Price momentum rules
        "mc_change_30m_50pct": 15,  # +15 if MC change 30m >= +50%
        "mc_change_2h_30pct": 10,  # +10 if MC change 2h >= +30%
        "drawdown_35pct": -10,  # -10 if drawdown >= 35%
        # Liquidity rules
        "liquidity_up_30pct": 10,  # +10 if liquidity >= first_seen * 1.3
        "liquidity_down_40pct": -15,  # -15 if liquidity < first_seen * 0.6
        # Volume rules
        "volume_24h_100k": 10,  # +10 if volume_24h >= $100k
        "volume_24h_10k": -10,  # -10 if volume_24h < $10k
        # Holder quality rules
        "high_win_rate_3plus": 12,  # +12 if >= 3 high-win-rate wallets
        "high_win_rate_1_2": 6,  # +6 if 1-2 high-win-rate wallets
        "top_holder_concentrated": -8,  # -8 if top_holder_share > 0.45
        # Age/lock rules
        "young_unlocked_lp": -10,  # -10 if age < 1h and lp_locked=false
        # PnL feedback rules
        "positions_positive_pnl": 8,  # +8 if our_positions_pnl > 0
        "positions_negative_pnl": -8,  # -8 if our_positions_pnl < 0
    },
    # Run tracking
    "last_tier0_run_at": None,
    "last_tier1_run_at": None,
    "last_tier1_credits_used": 0,
    "last_hot_refresh_at": None,
    "last_score_run_at": None,
    "last_control_cohort_run_at": None,
}


def load_ingest_settings() -> Dict:
    """Load ingest settings from file, fallback to defaults"""
    if os.path.exists(INGEST_SETTINGS_FILE):
        try:
            with open(INGEST_SETTINGS_FILE, "r") as f:
                data = json.load(f)
                # Merge with defaults (file values override defaults)
                return {**DEFAULT_INGEST_SETTINGS, **data}
        except Exception as e:
            print(f"[Config] Error reading ingest_settings.json: {e}")
            return DEFAULT_INGEST_SETTINGS.copy()
    return DEFAULT_INGEST_SETTINGS.copy()


def save_ingest_settings(settings: Dict) -> bool:
    """Save ingest settings to file"""
    try:
        with open(INGEST_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        print(f"[Config] Ingest settings saved")
        return True
    except Exception as exc:
        print(f"[Config] Failed to persist ingest settings: {exc}")
        return False


# Load ingest settings on module import
CURRENT_INGEST_SETTINGS = load_ingest_settings()
print(
    f"[Config] Ingest Settings: ingest_enabled={CURRENT_INGEST_SETTINGS['ingest_enabled']}, "
    f"enrich_enabled={CURRENT_INGEST_SETTINGS['enrich_enabled']}, "
    f"mc_min=${CURRENT_INGEST_SETTINGS['mc_min']}"
)
