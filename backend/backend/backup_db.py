#!/usr/bin/env python3
"""
Backup script for analyzed_tokens.db and related data.
Run this before pulls/merges, migrations, or major changes.

Usage:
    python backend/backup_db.py
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_FILE = SCRIPT_DIR / "analyzed_tokens.db"
ANALYSIS_RESULTS_DIR = SCRIPT_DIR / "analysis_results"
AXIOM_EXPORTS_DIR = SCRIPT_DIR / "axiom_exports"
BACKUPS_DIR = SCRIPT_DIR / "backups"


def create_backup():
    """Create timestamped backup of database and data directories."""

    if not DB_FILE.exists():
        print(f"[Backup] Database not found at {DB_FILE}")
        return False

    # Create backups directory if it doesn't exist
    BACKUPS_DIR.mkdir(exist_ok=True)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = BACKUPS_DIR / backup_name
    backup_path.mkdir(exist_ok=True)

    print(f"[Backup] Creating backup: {backup_name}")

    # Backup database
    db_backup = backup_path / "analyzed_tokens.db"
    shutil.copy2(DB_FILE, db_backup)
    print(f"[Backup] OK Database backed up: {db_backup.name}")

    # Get database stats
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM analyzed_tokens")
    token_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM wallet_tags")
    tag_count = cursor.fetchone()[0]
    conn.close()

    print(f"[Backup]   - {token_count} tokens")
    print(f"[Backup]   - {tag_count} wallet tags")

    # Backup analysis results if directory exists
    if ANALYSIS_RESULTS_DIR.exists():
        results_backup = backup_path / "analysis_results"
        shutil.copytree(ANALYSIS_RESULTS_DIR, results_backup)
        file_count = len(list(results_backup.glob("*.json")))
        print(f"[Backup] OK Analysis results backed up: {file_count} files")

    # Backup axiom exports if directory exists
    if AXIOM_EXPORTS_DIR.exists():
        axiom_backup = backup_path / "axiom_exports"
        shutil.copytree(AXIOM_EXPORTS_DIR, axiom_backup)
        file_count = len(list(axiom_backup.glob("*.json")))
        print(f"[Backup] OK Axiom exports backed up: {file_count} files")

    # Create manifest file
    manifest = backup_path / "MANIFEST.txt"
    with open(manifest, "w") as f:
        f.write(f"Backup created: {datetime.now().isoformat()}\n")
        f.write(f"Database: {DB_FILE}\n")
        f.write(f"Tokens: {token_count}\n")
        f.write(f"Tags: {tag_count}\n")

    print(f"\n[Backup] SUCCESS! Backup completed successfully!")
    print(f"[Backup] Location: {backup_path}")
    print(f"\n[Backup] To restore this backup:")
    print(f"[Backup]   python backend/restore_db.py {backup_name}")

    return True


def list_backups():
    """List all available backups."""
    if not BACKUPS_DIR.exists():
        print("[Backup] No backups directory found")
        return

    backups = sorted(BACKUPS_DIR.glob("backup_*"), reverse=True)

    if not backups:
        print("[Backup] No backups found")
        return

    print(f"\n[Backup] Available backups ({len(backups)}):")
    for backup in backups[:10]:  # Show last 10
        manifest = backup / "MANIFEST.txt"
        if manifest.exists():
            with open(manifest) as f:
                first_line = f.readline().strip()
                print(f"  - {backup.name}: {first_line}")
        else:
            print(f"  - {backup.name}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_backups()
    else:
        success = create_backup()
        sys.exit(0 if success else 1)
