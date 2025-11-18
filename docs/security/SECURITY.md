# Security and Data Privacy Notice

This repository contains research data, private watchlists, and API credentials. Keep every sensitive artifact on your local machine and out of version control.

## High-Risk Paths (Do Not Share)

| Path | Contains | Risk | Protection |
| --- | --- | --- | --- |
| `backend/axiom_exports/` | Buyer export bundles | Reveals trading playbooks | git-ignored |
| `backend/analysis_results/` | Raw job output, CSV/JSON | Full transaction research set | git-ignored |
| `backend/analyzed_tokens.db` and `backend/solscan_monitor.db` | Token + wallet history | Complete trading history | git-ignored |
| `backend/monitored_addresses.json` | Current watchlist | Leaks addresses of interest | git-ignored |
| `backend/config.json` | Helius API key + thresholds | API key theft and quota drain | git-ignored |

Never push these files, zip them for others, or upload them to cloud storage without encryption.

## Safe Sharing

You can safely share:
- AutoHotkey sources (`action_wheel.ahk`, helpers under `Lib/`)
- Backend source files (`backend/*.py`, excluding configs with secrets)
- Documentation (`README.md`, files under `docs/`)
- Configuration templates (`backend/config.example.json`)
- Browser helpers (`userscripts/`)

## Best Practices

- Keep sensitive folders on encrypted disks or password-protected backups.
- Review `.gitignore` before adding new artifacts under `backend/`.
- Rotate API keys immediately if logs or screen recordings capture them.
- Clear browser consoles and terminal buffers before streaming or screenshotting.

## If You Leak Data

1. Revoke exposed API keys.
2. Treat any revealed wallet addresses as compromised.
3. Use `git filter-repo` or BFG Repo-Cleaner to purge the files from history.
4. Re-clone a clean working tree once remediation is complete.

## Questions

When in doubt, do not share it. Keeping your datasets private is the only way to protect the edge that Gun Del Sol gives you.
