#!/usr/bin/env python3
"""
Restore script for analyzed_tokens.db and related data.

Usage:
    python backend/restore_db.py backup_20250117_123456
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
DB_FILE = SCRIPT_DIR / "analyzed_tokens.db"
ANALYSIS_RESULTS_DIR = SCRIPT_DIR / "analysis_results"
AXIOM_EXPORTS_DIR = SCRIPT_DIR / "axiom_exports"
BACKUPS_DIR = SCRIPT_DIR / "backups"


def restore_backup(backup_name):
    """Restore from a timestamped backup."""

    backup_path = BACKUPS_DIR / backup_name

    if not backup_path.exists():
        print(f"[Restore] ERROR: Backup not found: {backup_name}")
        print(f"[Restore] Available backups:")
        os.system("python backend/backup_db.py list")
        return False

    print(f"[Restore] Restoring from: {backup_name}")

    # Read manifest
    manifest = backup_path / "MANIFEST.txt"
    if manifest.exists():
        print(f"\n[Restore] Backup info:")
        with open(manifest) as f:
            for line in f:
                print(f"  {line.strip()}")
        print()

    # Confirm with user
    response = input("[Restore] This will overwrite current data. Continue? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        print("[Restore] Cancelled")
        return False

    # Create safety backup of current state
    if DB_FILE.exists():
        safety_backup = DB_FILE.parent / f"analyzed_tokens_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_FILE, safety_backup)
        print(f"[Restore] OK Safety backup created: {safety_backup.name}")

    # Restore database
    db_backup = backup_path / "analyzed_tokens.db"
    if db_backup.exists():
        shutil.copy2(db_backup, DB_FILE)
        print(f"[Restore] OK Database restored")
    else:
        print(f"[Restore] WARNING: No database in backup")

    # Restore analysis results
    results_backup = backup_path / "analysis_results"
    if results_backup.exists():
        if ANALYSIS_RESULTS_DIR.exists():
            shutil.rmtree(ANALYSIS_RESULTS_DIR)
        shutil.copytree(results_backup, ANALYSIS_RESULTS_DIR)
        file_count = len(list(ANALYSIS_RESULTS_DIR.glob("*.json")))
        print(f"[Restore] OK Analysis results restored: {file_count} files")

    # Restore axiom exports
    axiom_backup = backup_path / "axiom_exports"
    if axiom_backup.exists():
        if AXIOM_EXPORTS_DIR.exists():
            shutil.rmtree(AXIOM_EXPORTS_DIR)
        shutil.copytree(axiom_backup, AXIOM_EXPORTS_DIR)
        file_count = len(list(AXIOM_EXPORTS_DIR.glob("*.json")))
        print(f"[Restore] OK Axiom exports restored: {file_count} files")

    print(f"\n[Restore] SUCCESS! Restore completed successfully!")
    print(f"[Restore] NOTE: Restart the backend server for changes to take effect")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/restore_db.py <backup_name>")
        print("\nAvailable backups:")
        os.system("python backend/backup_db.py list")
        sys.exit(1)

    backup_name = sys.argv[1]
    success = restore_backup(backup_name)
    sys.exit(0 if success else 1)
