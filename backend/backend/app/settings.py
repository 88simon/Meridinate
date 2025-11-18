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

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_FILE = os.path.join(SCRIPT_DIR, "analyzed_tokens.db")
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "api_settings.json")
DATA_FILE = os.path.join(SCRIPT_DIR, "monitored_addresses.json")
ANALYSIS_RESULTS_DIR = os.path.join(SCRIPT_DIR, "analysis_results")
AXIOM_EXPORTS_DIR = os.path.join(SCRIPT_DIR, "axiom_exports")

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

    # Try config.json (look in the backend directory where this script is located)
    config_file = os.path.join(SCRIPT_DIR, "config.json")
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
