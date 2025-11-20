# Meridinate AutoHotkey Action Wheel

Desktop automation tool for Meridinate - provides quick access to Solana analysis tools via a mouse-driven radial menu.

## Overview

The **Action Wheel** is a Windows-only AutoHotkey v2 script that provides instant access to Solana blockchain analysis tools without leaving your browser. Activate it with a hotkey (default: backtick `` ` ``), then click or use keyboard shortcuts to trigger actions.

## Features

### Radial Menu System

- **Mouse-driven Interface** - Visual wheel menu with 6 action wedges
- **Keyboard Shortcuts** - Press 1-6 to select actions without moving mouse
- **Real-time Hover States** - Visual feedback for current selection
- **Customizable Hotkey** - Default backtick `` ` ``, configurable via settings dialog

### Available Actions

1. **Solscan** (Wedge 1) - Opens wallet address in Solscan with custom filters
2. **Exclude** (Wedge 2) - Adds wallet to exclusion list and reloads Solscan page
3. **Monitor** (Wedge 3) - Reserved for future monitoring features
4. **Defined.fi** (Wedge 4) - Opens wallet in Defined.fi DEX aggregator
5. **Analyze** (Wedge 5) - Reserved for quick token analysis
6. **Cancel** (Wedge 6) - Closes menu without action

### Solscan Integration

- **Dynamic URL Generation** - Builds Solscan URLs with filters from settings
- **Activity Type Filtering** - Transfer, Mint, Burn, Create Account, Close Account, Set Authority, Staking operations
- **Minimum Value Filter** - Excludes transactions below specified USD value
- **Token Address Filter** - Filter by SOL or any SPL token (defaults to SOL)
- **Exclude Amount Zero** - Hide zero-amount transactions
- **Remove Spam** - Filter out spam transactions
- **Page Size Control** - Results per page (10, 20, 30, 40, 60, 100)

### Settings Synchronization

- **Web UI Integration** - Settings configured in Meridinate dashboard auto-sync to AutoHotkey
- **Shared Settings File** - `apps/backend/action_wheel_settings.ini` used by both web app and AutoHotkey
- **Auto-reload** - Changes from web UI take effect after script reload
- **UTF-16 LE Encoding** - Proper encoding for Windows INI file format

## Requirements

- **Windows OS** - AutoHotkey v2 is Windows-only
- **AutoHotkey v2.0+** - [Download from autohotkey.com](https://www.autohotkey.com/)
- **Meridinate Backend** - Settings file at `apps/backend/action_wheel_settings.ini`

## Installation

1. **Install AutoHotkey v2:**
   - Download from https://www.autohotkey.com/
   - Install latest v2.x version (not v1.x)

2. **Run the script:**
   ```cmd
   # From monorepo root
   cd tools\autohotkey
   action_wheel.ahk
   ```

3. **Verify installation:**
   - AutoHotkey icon appears in system tray
   - Press backtick `` ` `` to test menu activation

## Usage

### Using the Action Wheel

1. **Navigate to any Solscan wallet page** so the script can grab the address.
2. **Press backtick** `` ` `` to display the radial menu.
3. **Choose an action** (mouse or number key):
   - **1 – Solscan**: opens the same wallet with your configured filters (min value, spam, etc.).
   - **2 – Exclude**: appends the current wallet to the URL’s `to_address=!Wallet1,!Wallet2,...` filter and reloads the page.
   - **4 – Defined.fi**: jumps to the wallet on Defined.fi for quick context.
   - **3/5** remain reserved, **6** cancels.
4. **Reload the script** after changing settings via the dashboard so the new parameters apply.

## Configuration

### Settings File Location

```
C:\Meridinate\apps\backend\action_wheel_settings.ini
```

**Important:** This file is shared with the web application. Changes made in the Meridinate dashboard will automatically sync to AutoHotkey after script reload.

### Settings Format

```ini
[Hotkeys]
WheelMenu=`

[Actions]
Wedge1=Solscan
Wedge2=Exclude
Wedge3=Monitor
Wedge4=Defined.fi
Wedge5=Analyze
Wedge6=Cancel

[Solscan]
activity_type=ACTIVITY_SPL_TRANSFER
exclude_amount_zero=true
remove_spam=true
value=80
token_address=So11111111111111111111111111111111111111111
page_size=30
```

### Changing Settings

**Method 1: Web UI (Recommended)**

1. Open Meridinate dashboard at http://localhost:3000
2. Click Settings icon in sidebar
3. Modify Solscan settings
4. Settings auto-save after 300ms
5. **Reload AutoHotkey script** (right-click tray icon → Reload Script)

**Method 2: Manual Edit**

1. Close AutoHotkey script
2. Edit `apps/backend/action_wheel_settings.ini` with text editor
3. Save with UTF-16 LE encoding
4. Restart AutoHotkey script

### Activity Type Values

Must match Solscan's exact constants:

**Token Operations:**
- `ACTIVITY_SPL_TRANSFER` - Transfer transactions
- `ACTIVITY_SPL_MINT` - Mint operations
- `ACTIVITY_SPL_BURN` - Burn operations
- `ACTIVITY_SPL_CREATE_ACCOUNT` - Account creation
- `ACTIVITY_SPL_CLOSE_ACCOUNT` - Account closure
- `ACTIVITY_SPL_SET_OWNER_AUTHORITY` - Authority changes

**Staking Operations:**
- `ACTIVITY_SPL_TOKEN_SPLIT_STAKE` - Stake splitting
- `ACTIVITY_SPL_TOKEN_MERGE_STAKE` - Stake merging
- `ACTIVITY_SPL_TOKEN_WITHDRAW_STAKE` - Stake withdrawal
- `ACTIVITY_SPL_VOTE_WITHDRAW` - Vote withdrawal

## Troubleshooting

### Script Won't Load

**Error: "AutoHotkey version 2.0 or higher is required"**

Solution: Install AutoHotkey v2.x from https://www.autohotkey.com/

### Menu Not Appearing

1. Check system tray for AutoHotkey icon
2. Try different hotkey if backtick conflicts
3. Restart script: Right-click tray icon → Reload Script

### Settings Not Syncing

**Problem:** Web UI changes don't appear in AutoHotkey

**Solution:**
1. Verify settings file exists: `apps/backend/action_wheel_settings.ini`
2. Check file encoding is UTF-16 LE (Windows default)
3. Reload AutoHotkey script after web UI changes
4. Check script console for errors (right-click tray icon → Open)

### Solscan Links Show "No Data"

**Problem:** Clicking Solscan action shows page with no transactions

**Root Causes:**
- Wrong parameter order (fixed as of Nov 20, 2025)
- Incorrect activity type value
- Settings file not synced

**Solution:**
1. Update to latest action_wheel.ahk script
2. Verify settings in web UI match desired filters
3. Reload AutoHotkey script
4. Test with known wallet address

### URL Extraction Fails

**Problem:** Script can't extract wallet address from browser

**Causes:**
- Not on Solscan page
- URL structure changed
- Browser address bar blocked

**Solution:**
1. Ensure you're on solscan.io/account/{ADDRESS} page
2. Check script console for regex match errors
3. Update the Solscan URL regex in `action_wheel.ahk` if their page structure changes

## Technical Details

### URL Parameter Order (Critical)

Solscan requires specific parameter order for filters to work:

```
?activity_type={TYPE}&
 exclude_amount_zero={BOOL}&
 remove_spam={BOOL}&
 token_address={ADDRESS}&
 value={MIN}&
 value=undefined&
 page_size={SIZE}#transfers
```

**Order matters!** `token_address` MUST come before `value` parameters.

### GDI+ Graphics

The action wheel uses Windows GDI+ for rendering:
- Anti-aliased circles and wedges
- Smooth gradients for hover states
- Hardware-accelerated drawing
- 60fps hover animations

### Settings File Encoding

- **Encoding:** UTF-16 LE (Windows standard)
- **Format:** INI file with sections
- **Shared:** Both backend and AutoHotkey use same file
- **Path:** Relative from script directory: `..\..\apps\backend\action_wheel_settings.ini`

### Browser Automation

The script uses clipboard-based URL extraction:
1. Saves current clipboard
2. Sends Ctrl+L to focus address bar
3. Sends Ctrl+C to copy URL
4. Extracts wallet address via regex
5. Restores original clipboard

**Limitations:**
- Requires browser to be active window
- Clipboard temporarily overwritten
- 100ms delays for clipboard operations

## Development

### File Structure

```
tools/autohotkey/
├── action_wheel.ahk          # Main script
└── README.md                 # This file
```

### Key Functions

**LoadSettings()** - Reads hotkeys and actions from INI file at startup

**SaveSettings()** - Writes hotkeys and actions to INI file

**OpenSolscan(address)** - Opens Solscan with filters from the shared INI file and builds URLs in the required parameter order

**ReloadPageWithExclusions(mainAddress, exclusionsList)** - Reloads Solscan with the `to_address=!Wallet1,!Wallet2` filter applied using the same shared settings

**GetAddressAndExclusionsFromURL()** - Extracts wallet address and exclusion parameters from the active browser URL via regex

### Updating URL Format

If Solscan changes their URL structure:

1. **Test manually** on solscan.io to get correct format
2. **Update `OpenSolscan()`** so it emits the new parameter order/values
3. **Update `ReloadPageWithExclusions()`** to mirror those changes for exclusion reloads
4. **Test with real wallet addresses**
5. **Update this README** with new format

### Adding New Actions

1. **Add function** for new action (follow existing patterns)
2. **Update `WheelMenuActions`** array so the new wedge appears in the menu
3. **Add case** in menu selection handler
4. **Document** in this README

## Security Notes

- Script has full browser access (can read URLs, manipulate clipboard)
- No network access beyond opening URLs
- No file access beyond settings INI
- No registry modifications
- No process injection
- All actions require explicit user activation

## Support

For issues or questions:
1. Check this README troubleshooting section
2. Verify settings file format and encoding
3. Check AutoHotkey console for errors
4. Review PROJECT_BLUEPRINT.md for system architecture
5. Test with minimal settings (Transfer, SOL token, value=0)

---

**Part of the Meridinate monorepo.** See [root README](../../README.md) for full project documentation.
