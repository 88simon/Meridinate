"""
Database Migration: Fix UNIQUE constraint to allow token re-analysis
Changes: UNIQUE(token_id, wallet_address) -> UNIQUE(analysis_run_id, wallet_address)
"""

import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "analyzed_tokens.db"
BACKUP_PATH = f'analyzed_tokens_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'


def migrate():
    print(f"[Migration] Starting database migration...")
    print(f"[Migration] Database: {DB_PATH}")

    # Create backup
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"[Migration] Backup created: {BACKUP_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if migration is needed
        cursor.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='early_buyer_wallets'
        """
        )
        result = cursor.fetchone()

        if result and "UNIQUE(token_id, wallet_address)" in result[0]:
            print("[Migration] Old schema detected, migrating...")

            # Step 1: Rename old table
            cursor.execute("ALTER TABLE early_buyer_wallets RENAME TO early_buyer_wallets_old")
            print("[Migration] Renamed old table")

            # Step 2: Create new table with correct schema
            cursor.execute(
                """
                CREATE TABLE early_buyer_wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    analysis_run_id INTEGER NOT NULL,
                    wallet_address TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    first_buy_usd REAL,
                    total_usd REAL,
                    transaction_count INTEGER,
                    average_buy_usd REAL,
                    first_buy_timestamp TIMESTAMP,
                    axiom_name TEXT,
                    wallet_balance_usd REAL,
                    FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE CASCADE,
                    FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE,
                    UNIQUE(analysis_run_id, wallet_address)
                )
            """
            )
            print("[Migration] Created new table with correct schema")

            # Step 3: Create analysis_run entries for old data (if missing)
            cursor.execute(
                """
                SELECT DISTINCT token_id FROM early_buyer_wallets_old
                WHERE analysis_run_id IS NULL
            """
            )
            tokens_without_runs = cursor.fetchall()

            for (token_id,) in tokens_without_runs:
                # Create an analysis run for this token
                cursor.execute(
                    """
                    INSERT INTO analysis_runs (token_id, wallets_found, credits_used)
                    VALUES (?, 0, 0)
                """,
                    (token_id,),
                )
                new_run_id = cursor.lastrowid

                # Update old records to use this run_id
                cursor.execute(
                    """
                    UPDATE early_buyer_wallets_old
                    SET analysis_run_id = ?
                    WHERE token_id = ? AND analysis_run_id IS NULL
                """,
                    (new_run_id, token_id),
                )

            print(f"[Migration] Created {len(tokens_without_runs)} missing analysis runs")

            # Step 4: Copy data from old table
            cursor.execute(
                """
                INSERT INTO early_buyer_wallets
                (id, token_id, analysis_run_id, wallet_address, position,
                 first_buy_usd, total_usd, transaction_count, average_buy_usd,
                 first_buy_timestamp, axiom_name, wallet_balance_usd)
                SELECT id, token_id, analysis_run_id, wallet_address, position,
                       first_buy_usd, total_usd, transaction_count, average_buy_usd,
                       first_buy_timestamp, axiom_name, wallet_balance_usd
                FROM early_buyer_wallets_old
            """
            )
            rows_migrated = cursor.rowcount
            print(f"[Migration] Migrated {rows_migrated} wallet records")

            # Step 5: Drop old table
            cursor.execute("DROP TABLE early_buyer_wallets_old")
            print("[Migration] Dropped old table")

            conn.commit()
            print("[Migration] SUCCESS - Migration completed successfully!")
            print(f"[Migration] You can now re-analyze tokens without errors")

        elif result and "UNIQUE(analysis_run_id, wallet_address)" in result[0]:
            print("[Migration] SUCCESS - Database already has correct schema, no migration needed")
        else:
            print("[Migration] WARNING - Unknown schema state")

    except Exception as e:
        conn.rollback()
        print(f"[Migration] ERROR - Error during migration: {e}")
        print(f"[Migration] Database has been rolled back")
        print(f"[Migration] Backup is available at: {BACKUP_PATH}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
