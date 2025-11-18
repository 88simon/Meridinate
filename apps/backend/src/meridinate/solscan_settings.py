"""
Solscan settings management

Handles reading/writing Solscan URL parameters from action_wheel_settings.ini
"""

import os
from typing import Dict

# Path to the action wheel settings file (in parent directory of backend)
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
SOLSCAN_SETTINGS_FILE = os.path.join(PARENT_DIR, "action_wheel_settings.ini")

# Default Solscan settings
DEFAULT_SOLSCAN_SETTINGS = {
    "activity_type": "ACTIVITY_SPL_TRANSFER",
    "exclude_amount_zero": "true",
    "remove_spam": "true",
    "value": "100",
    "token_address": "So11111111111111111111111111111111111111111",
    "page_size": "10",
}


def load_solscan_settings() -> Dict[str, str]:
    """
    Load Solscan settings from action_wheel_settings.ini

    Returns:
        Dictionary of Solscan URL parameters
    """
    if not os.path.exists(SOLSCAN_SETTINGS_FILE):
        return DEFAULT_SOLSCAN_SETTINGS.copy()

    try:
        settings = DEFAULT_SOLSCAN_SETTINGS.copy()

        # Read the UTF-16 encoded INI file
        with open(SOLSCAN_SETTINGS_FILE, "r", encoding="utf-16-le") as f:
            content = f.read()

        # Parse the [Solscan] section
        in_solscan_section = False
        for line in content.splitlines():
            line = line.strip()

            if line == "[Solscan]":
                in_solscan_section = True
                continue
            elif line.startswith("[") and line.endswith("]"):
                in_solscan_section = False
                continue

            if in_solscan_section and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key in settings:
                    settings[key] = value

        return settings
    except Exception as e:
        print(f"[Solscan Settings] Error reading settings: {e}")
        return DEFAULT_SOLSCAN_SETTINGS.copy()


def save_solscan_settings(settings: Dict[str, str]) -> bool:
    """
    Save Solscan settings to action_wheel_settings.ini

    Args:
        settings: Dictionary of Solscan URL parameters to save

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read existing content
        if os.path.exists(SOLSCAN_SETTINGS_FILE):
            with open(SOLSCAN_SETTINGS_FILE, "r", encoding="utf-16-le") as f:
                lines = f.readlines()
        else:
            # Create new file with basic structure
            lines = [
                "[Hotkeys]\n",
                "WheelMenu=`\n",
                "[Actions]\n",
                "Wedge1=Solscan\n",
                "Wedge2=Exclude\n",
                "Wedge3=Monitor\n",
                "Wedge4=Defined.fi\n",
                "Wedge5=Analyze\n",
                "Wedge6=Cancel\n",
            ]

        # Remove existing [Solscan] section
        new_lines = []
        in_solscan_section = False
        for line in lines:
            stripped = line.strip()

            if stripped == "[Solscan]":
                in_solscan_section = True
                continue
            elif stripped.startswith("[") and stripped.endswith("]"):
                in_solscan_section = False

            if not in_solscan_section:
                new_lines.append(line)

        # Add [Solscan] section at the end
        new_lines.append("[Solscan]\n")
        for key, value in settings.items():
            new_lines.append(f"{key}={value}\n")

        # Write back to file with UTF-16-LE encoding
        with open(SOLSCAN_SETTINGS_FILE, "w", encoding="utf-16-le") as f:
            f.writelines(new_lines)

        print(f"[Solscan Settings] Saved settings: {settings}")
        return True
    except Exception as e:
        print(f"[Solscan Settings] Failed to save settings: {e}")
        return False


# Load settings on module import
CURRENT_SOLSCAN_SETTINGS = load_solscan_settings()
print(f"[Solscan Settings] Loaded: {CURRENT_SOLSCAN_SETTINGS}")
