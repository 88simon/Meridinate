"""
SQLite Database Maintenance Script
Performs VACUUM, ANALYZE, and integrity checks to keep the database optimized

Usage:
    python scripts/db_maintenance.py [--vacuum] [--analyze] [--integrity-check] [--all]

Options:
    --vacuum            Reclaim unused space and defragment the database
    --analyze           Update query planner statistics
    --integrity-check   Check database integrity
    --all              Run all maintenance tasks (default if no options specified)
    --auto-vacuum       Enable auto-vacuum mode for future operations
    --stats            Show database statistics

Examples:
    python scripts/db_maintenance.py --all
    python scripts/db_maintenance.py --vacuum --analyze
    python scripts/db_maintenance.py --stats
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.meridinate import settings


def get_db_size(db_path: str) -> Tuple[float, str]:
    """Get database file size in human-readable format"""
    size_bytes = os.path.getsize(db_path)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return size_bytes, unit
        size_bytes /= 1024.0
    return size_bytes, "TB"


def print_db_stats(conn: sqlite3.Connection, db_path: str):
    """Print database statistics"""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    # File size
    size, unit = get_db_size(db_path)
    print(f"File size: {size:.2f} {unit}")

    # Page count and size
    cursor = conn.cursor()
    cursor.execute("PRAGMA page_count")
    page_count = cursor.fetchone()[0]

    cursor.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]

    print(f"Page count: {page_count:,}")
    print(f"Page size: {page_size:,} bytes")
    print(f"Total pages size: {(page_count * page_size / 1024 / 1024):.2f} MB")

    # Free pages
    cursor.execute("PRAGMA freelist_count")
    free_pages = cursor.fetchone()[0]
    free_space_mb = (free_pages * page_size / 1024 / 1024)

    print(f"Free pages: {free_pages:,}")
    print(f"Free space: {free_space_mb:.2f} MB ({(free_pages / max(page_count, 1) * 100):.1f}%)")

    # Table row counts
    print("\nTable Row Counts:")
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    tables = cursor.fetchall()

    for (table_name,) in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  {table_name}: {count:,} rows")

    print("=" * 60 + "\n")


def run_vacuum(conn: sqlite3.Connection, db_path: str):
    """Run VACUUM to reclaim space and defragment"""
    print("\n[VACUUM] Starting database compaction...")

    size_before, unit_before = get_db_size(db_path)
    print(f"[VACUUM] Size before: {size_before:.2f} {unit_before}")

    start_time = datetime.now()
    conn.execute("VACUUM")
    duration = (datetime.now() - start_time).total_seconds()

    size_after, unit_after = get_db_size(db_path)
    saved = (size_before - size_after) if unit_before == unit_after else 0

    print(f"[VACUUM] Size after: {size_after:.2f} {unit_after}")
    if saved > 0:
        print(f"[VACUUM] Space reclaimed: {saved:.2f} {unit_before}")
    print(f"[VACUUM] Completed in {duration:.2f} seconds")


def run_analyze(conn: sqlite3.Connection):
    """Run ANALYZE to update query planner statistics"""
    print("\n[ANALYZE] Updating query planner statistics...")

    start_time = datetime.now()
    conn.execute("ANALYZE")
    duration = (datetime.now() - start_time).total_seconds()

    print(f"[ANALYZE] Completed in {duration:.2f} seconds")


def run_integrity_check(conn: sqlite3.Connection):
    """Run integrity check"""
    print("\n[INTEGRITY CHECK] Checking database integrity...")

    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    results = cursor.fetchall()

    if results == [("ok",)]:
        print("[INTEGRITY CHECK] Database integrity: OK")
    else:
        print("[INTEGRITY CHECK] Issues found:")
        for (msg,) in results:
            print(f"  - {msg}")


def enable_auto_vacuum(conn: sqlite3.Connection):
    """Enable auto-vacuum mode"""
    print("\n[AUTO-VACUUM] Enabling auto-vacuum mode...")

    cursor = conn.cursor()
    cursor.execute("PRAGMA auto_vacuum")
    current_mode = cursor.fetchone()[0]

    if current_mode == 0:  # None
        print("[AUTO-VACUUM] Current mode: NONE")
        print("[AUTO-VACUUM] Setting mode to FULL (requires VACUUM to take effect)")
        conn.execute("PRAGMA auto_vacuum = FULL")
        conn.execute("VACUUM")
        print("[AUTO-VACUUM] Auto-vacuum enabled")
    elif current_mode == 1:  # Full
        print("[AUTO-VACUUM] Auto-vacuum already enabled (FULL mode)")
    elif current_mode == 2:  # Incremental
        print("[AUTO-VACUUM] Auto-vacuum already enabled (INCREMENTAL mode)")


def main():
    parser = argparse.ArgumentParser(
        description="SQLite database maintenance script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM operation")
    parser.add_argument("--analyze", action="store_true", help="Run ANALYZE operation")
    parser.add_argument("--integrity-check", action="store_true", help="Run integrity check")
    parser.add_argument("--auto-vacuum", action="store_true", help="Enable auto-vacuum mode")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--all", action="store_true", help="Run all maintenance tasks")

    args = parser.parse_args()

    # If no options specified, run all by default
    if not any([args.vacuum, args.analyze, args.integrity_check, args.auto_vacuum, args.stats, args.all]):
        args.all = True

    # Get database path
    db_path = settings.DATABASE_FILE

    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    print(f"Database: {db_path}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Create backup before maintenance
    backup_dir = Path(db_path).parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"pre_maintenance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

    print(f"\n[BACKUP] Creating safety backup: {backup_path.name}")
    import shutil
    shutil.copy2(db_path, backup_path)
    print("[BACKUP] Backup created successfully")

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)

        # Show stats if requested or if running all
        if args.stats or args.all:
            print_db_stats(conn, db_path)

        # Run integrity check first
        if args.integrity_check or args.all:
            run_integrity_check(conn)

        # Run ANALYZE
        if args.analyze or args.all:
            run_analyze(conn)

        # Run VACUUM (most impactful, do last)
        if args.vacuum or args.all:
            run_vacuum(conn, db_path)

        # Enable auto-vacuum if requested
        if args.auto_vacuum:
            enable_auto_vacuum(conn)

        # Show final stats
        if args.vacuum or args.all:
            print_db_stats(conn, db_path)

        conn.close()

        print("\n" + "=" * 60)
        print("MAINTENANCE COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"Backup location: {backup_path}")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nError during maintenance: {str(e)}")
        print(f"Database backup available at: {backup_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
