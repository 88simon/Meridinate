"""
============================================================================
Database Module - SENSITIVE DATA STORAGE
============================================================================
This module stores analyzed tokens and wallet activity in SQLite.

⚠️  SECURITY WARNING - CONTAINS SENSITIVE TRADING DATA  ⚠️

The database file (analyzed_tokens.db) contains:
- Wallet addresses of early buyers you discovered
- Token analysis results revealing your research
- Trading strategies and patterns

This data should NEVER be committed to version control or shared publicly.
The database files are protected by .gitignore.

============================================================================
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

# Centralized paths (keep DB and artifacts under apps/backend/data)
from meridinate import settings

# Import credit tracker lazily to avoid circular imports
_credit_tracker_initialized = False

DATABASE_FILE = settings.DATABASE_FILE
ANALYSIS_RESULTS_DIR = settings.ANALYSIS_RESULTS_DIR
AXIOM_EXPORTS_DIR = settings.AXIOM_EXPORTS_DIR


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """
    Sanitize a string for use in filenames.

    Args:
        text: Text to sanitize
        max_length: Maximum length of output

    Returns:
        Sanitized filename-safe string
    """
    # Convert to lowercase
    text = text.lower()
    # Replace spaces with hyphens
    text = text.replace(" ", "-")
    # Remove any character that isn't alphanumeric or hyphen
    text = "".join(c for c in text if c.isalnum() or c == "-")
    # Remove consecutive hyphens
    while "--" in text:
        text = text.replace("--", "-")
    # Trim hyphens from start/end
    text = text.strip("-")
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text


def get_analysis_file_path(token_id: int, token_name: str, in_trash: bool = False) -> str:
    """
    Generate the file path for analysis results JSON.

    Format: {id}_{sanitized-name}.json
    Example: 20_eugene-the-meme.json
    """
    sanitized_name = sanitize_filename(token_name)
    filename = f"{token_id}_{sanitized_name}.json"

    if in_trash:
        return os.path.join(ANALYSIS_RESULTS_DIR, "trash", filename)
    else:
        return os.path.join(ANALYSIS_RESULTS_DIR, filename)


def get_axiom_file_path(token_id: int, acronym: str, in_trash: bool = False) -> str:
    """
    Generate the file path for Axiom export JSON.

    Format: {id}_{acronym}.json
    Example: 20_em.json
    """
    sanitized_acronym = sanitize_filename(acronym, max_length=10)
    filename = f"{token_id}_{sanitized_acronym}.json"

    if in_trash:
        return os.path.join(AXIOM_EXPORTS_DIR, "trash", filename)
    else:
        return os.path.join(AXIOM_EXPORTS_DIR, filename)


def move_files_to_trash(token_id: int):
    """
    Move token files to trash folders.

    Returns:
        Tuple of (analysis_moved, axiom_moved)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT analysis_file_path, axiom_file_path
            FROM analyzed_tokens
            WHERE id = ?
        """,
            (token_id,),
        )
        row = cursor.fetchone()

        if not row:
            return (False, False)

        analysis_path, axiom_path = row[0], row[1]
        analysis_moved = False
        axiom_moved = False

        # Create trash directories if they don't exist
        os.makedirs(os.path.join(ANALYSIS_RESULTS_DIR, "trash"), exist_ok=True)
        os.makedirs(os.path.join(AXIOM_EXPORTS_DIR, "trash"), exist_ok=True)

        # Move analysis file
        if analysis_path and os.path.exists(analysis_path):
            trash_path = analysis_path.replace(ANALYSIS_RESULTS_DIR, os.path.join(ANALYSIS_RESULTS_DIR, "trash"))
            try:
                os.rename(analysis_path, trash_path)
                cursor.execute("UPDATE analyzed_tokens SET analysis_file_path = ? WHERE id = ?", (trash_path, token_id))
                analysis_moved = True
            except Exception as e:
                print(f"[WARN] Failed to move analysis file: {e}")

        # Move axiom file
        if axiom_path and os.path.exists(axiom_path):
            trash_path = axiom_path.replace(AXIOM_EXPORTS_DIR, os.path.join(AXIOM_EXPORTS_DIR, "trash"))
            try:
                os.rename(axiom_path, trash_path)
                cursor.execute("UPDATE analyzed_tokens SET axiom_file_path = ? WHERE id = ?", (trash_path, token_id))
                axiom_moved = True
            except Exception as e:
                print(f"[WARN] Failed to move axiom file: {e}")

        conn.commit()
        return (analysis_moved, axiom_moved)


def restore_files_from_trash(token_id: int):
    """
    Restore token files from trash folders.

    Returns:
        Tuple of (analysis_restored, axiom_restored)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT analysis_file_path, axiom_file_path
            FROM analyzed_tokens
            WHERE id = ?
        """,
            (token_id,),
        )
        row = cursor.fetchone()

        if not row:
            return (False, False)

        analysis_path, axiom_path = row[0], row[1]
        analysis_restored = False
        axiom_restored = False

        # Restore analysis file
        if analysis_path and "trash" in analysis_path and os.path.exists(analysis_path):
            restored_path = analysis_path.replace(os.path.join(ANALYSIS_RESULTS_DIR, "trash"), ANALYSIS_RESULTS_DIR)
            try:
                os.rename(analysis_path, restored_path)
                cursor.execute(
                    "UPDATE analyzed_tokens SET analysis_file_path = ? WHERE id = ?", (restored_path, token_id)
                )
                analysis_restored = True
            except Exception as e:
                print(f"[WARN] Failed to restore analysis file: {e}")

        # Restore axiom file
        if axiom_path and "trash" in axiom_path and os.path.exists(axiom_path):
            restored_path = axiom_path.replace(os.path.join(AXIOM_EXPORTS_DIR, "trash"), AXIOM_EXPORTS_DIR)
            try:
                os.rename(axiom_path, restored_path)
                cursor.execute("UPDATE analyzed_tokens SET axiom_file_path = ? WHERE id = ?", (restored_path, token_id))
                axiom_restored = True
            except Exception as e:
                print(f"[WARN] Failed to restore axiom file: {e}")

        conn.commit()
        return (analysis_restored, axiom_restored)


def delete_token_files(token_id: int):
    """
    Permanently delete token files.

    Returns:
        Tuple of (analysis_deleted, axiom_deleted)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT analysis_file_path, axiom_file_path
            FROM analyzed_tokens
            WHERE id = ?
        """,
            (token_id,),
        )
        row = cursor.fetchone()

        if not row:
            return (False, False)

        analysis_path, axiom_path = row[0], row[1]
        analysis_deleted = False
        axiom_deleted = False

        # Delete analysis file
        if analysis_path and os.path.exists(analysis_path):
            try:
                os.remove(analysis_path)
                analysis_deleted = True
            except Exception as e:
                print(f"[WARN] Failed to delete analysis file: {e}")

        # Delete axiom file
        if axiom_path and os.path.exists(axiom_path):
            try:
                os.remove(axiom_path)
                axiom_deleted = True
            except Exception as e:
                print(f"[WARN] Failed to delete axiom file: {e}")

        return (analysis_deleted, axiom_deleted)


def update_token_file_paths(token_id: int, analysis_path: str, axiom_path: str) -> bool:
    """
    Update the file paths for a token in the database.

    Args:
        token_id: ID of the token to update
        analysis_path: Path to the analysis results file
        axiom_path: Path to the axiom export file

    Returns:
        True if successful, False otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE analyzed_tokens
            SET analysis_file_path = ?, axiom_file_path = ?
            WHERE id = ?
        """,
            (analysis_path, axiom_path, token_id),
        )
        return cursor.rowcount > 0


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    # Ensure database directory exists
    db_dir = os.path.dirname(DATABASE_FILE)
    os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_database():
    """Initialize database schema"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Analyzed tokens table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analyzed_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_address TEXT UNIQUE NOT NULL,
                token_name TEXT,
                token_symbol TEXT,
                acronym TEXT,
                analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                first_buy_timestamp TIMESTAMP,
                wallets_found INTEGER DEFAULT 0,
                axiom_json TEXT,
                webhook_id TEXT,
                credits_used INTEGER DEFAULT 0,
                last_analysis_credits INTEGER DEFAULT 0,
                is_deleted BOOLEAN DEFAULT 0,
                deleted_at TIMESTAMP,
                analysis_file_path TEXT,
                axiom_file_path TEXT,
                market_cap_usd REAL,
                market_cap_usd_current REAL,
                market_cap_updated_at TIMESTAMP,
                gem_status TEXT,
                state_version INTEGER DEFAULT 0
            )
        """
        )

        # Analysis runs table - tracks each time we analyze a token
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id INTEGER NOT NULL,
                analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                wallets_found INTEGER DEFAULT 0,
                credits_used INTEGER DEFAULT 0,
                FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE CASCADE
            )
        """
        )

        # Early buyer wallets table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS early_buyer_wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id INTEGER NOT NULL,
                analysis_run_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                position INTEGER NOT NULL,
                first_buy_usd REAL,
                first_buy_tokens REAL,
                entry_market_cap REAL,
                total_usd REAL,
                transaction_count INTEGER,
                average_buy_usd REAL,
                first_buy_timestamp TIMESTAMP,
                axiom_name TEXT,
                wallet_balance_usd REAL,
                wallet_balance_usd_previous REAL,
                wallet_balance_updated_at TIMESTAMP,
                FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE CASCADE,
                FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE,
                UNIQUE(analysis_run_id, wallet_address)
            )
        """
        )

        # Wallet activity events table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id INTEGER NOT NULL,
                transaction_signature TEXT UNIQUE,
                timestamp TIMESTAMP,
                activity_type TEXT,
                description TEXT,
                sol_amount REAL,
                token_amount REAL,
                recipient_address TEXT,
                FOREIGN KEY (wallet_id) REFERENCES early_buyer_wallets(id) ON DELETE CASCADE
            )
        """
        )

        # Wallet tags table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                tag TEXT NOT NULL,
                is_kol BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(wallet_address, tag)
            )
        """
        )

        # Token tags table (for GEM/DUD and other token classifications)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS token_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(token_id, tag),
                FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE CASCADE
            )
        """
        )

        # Create indices for better query performance
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_token_address
            ON analyzed_tokens(token_address)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_address
            ON early_buyer_wallets(wallet_address)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_activity_timestamp
            ON wallet_activity(timestamp DESC)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_tags_address
            ON wallet_tags(wallet_address)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_token_tags_token_id
            ON token_tags(token_id)
        """
        )

        # NEW: Critical performance indices
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_is_deleted_timestamp
            ON analyzed_tokens(is_deleted, analysis_timestamp DESC)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_token_analysis_run
            ON early_buyer_wallets(token_id, analysis_run_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_token_timestamp
            ON analysis_runs(token_id, analysis_timestamp DESC)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_tags_tag
            ON wallet_tags(tag)
        """
        )

        # Multi-token wallet metadata table - tracks which wallets are "new" to the multi-token panel
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS multi_token_wallet_metadata (
                wallet_address TEXT PRIMARY KEY,
                marked_new BOOLEAN DEFAULT 0,
                marked_at_analysis_id INTEGER,
                marked_at_timestamp TIMESTAMP
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_multi_token_metadata_marked
            ON multi_token_wallet_metadata(marked_new, marked_at_timestamp DESC)
        """
        )

        # MTEW (Multi-Token Early Wallet) Position Tracking table
        # Tracks positions of MTEWs in tokens they're early in, enabling win rate calculation
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS mtew_token_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                token_id INTEGER NOT NULL,

                -- Entry data (captured at scan time)
                entry_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                entry_market_cap REAL,
                entry_balance REAL,
                entry_balance_usd REAL,

                -- Position tracking (updated by scheduler)
                still_holding BOOLEAN DEFAULT 1,
                current_balance REAL,
                current_balance_usd REAL,
                position_checked_at TIMESTAMP,

                -- Exit tracking (when sold)
                exit_detected_at TIMESTAMP,
                exit_market_cap REAL,

                -- Multi-buy/sell aggregate tracking
                total_bought_tokens REAL DEFAULT 0,
                total_bought_usd REAL DEFAULT 0,
                total_sold_tokens REAL DEFAULT 0,
                total_sold_usd REAL DEFAULT 0,
                avg_entry_price REAL,  -- total_bought_usd / total_bought_tokens
                realized_pnl REAL DEFAULT 0,  -- Profit from sells
                buy_count INTEGER DEFAULT 1,
                sell_count INTEGER DEFAULT 0,

                -- Derived metrics (updated periodically)
                pnl_ratio REAL,  -- For holding: current_mc / entry_mc. For sold: exit_price / entry_price
                fpnl_ratio REAL,  -- Fumbled PnL: current_mc / entry_mc (what they missed by selling)

                UNIQUE(wallet_address, token_id),
                FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE CASCADE
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mtew_positions_wallet
            ON mtew_token_positions(wallet_address)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mtew_positions_token
            ON mtew_token_positions(token_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mtew_positions_stale
            ON mtew_token_positions(still_holding, position_checked_at)
        """
        )

        # Wallet metrics table - aggregated win/loss stats per wallet
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_metrics (
                wallet_address TEXT PRIMARY KEY,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                total_positions INTEGER DEFAULT 0,
                win_rate REAL,
                avg_pnl_ratio REAL,
                metrics_updated_at TIMESTAMP
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wallet_metrics_win_rate
            ON wallet_metrics(win_rate DESC)
        """
        )

        # SWAB (Smart Wallet Archive Builder) Settings table
        # Stores configuration for auto-check scheduling and filtering
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS swab_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),  -- Singleton row
                auto_check_enabled BOOLEAN DEFAULT 0,
                check_interval_minutes INTEGER DEFAULT 30,
                daily_credit_budget INTEGER DEFAULT 500,
                stale_threshold_minutes INTEGER DEFAULT 15,
                min_token_count INTEGER DEFAULT 2,
                last_check_at TIMESTAMP,
                credits_used_today INTEGER DEFAULT 0,
                credits_reset_date TEXT,  -- YYYY-MM-DD format
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert default settings row if not exists
        cursor.execute(
            """
            INSERT OR IGNORE INTO swab_settings (id, auto_check_enabled, check_interval_minutes,
                daily_credit_budget, stale_threshold_minutes, min_token_count)
            VALUES (1, 0, 30, 500, 15, 2)
        """
        )

        # Run migrations to add new columns to existing tables
        # Check if total_usd column exists in early_buyer_wallets, if not add it
        cursor.execute("PRAGMA table_info(early_buyer_wallets)")
        ebw_columns = [col[1] for col in cursor.fetchall()]

        if "total_usd" not in ebw_columns:
            print("[Database] Migrating: Adding total_usd column...")
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN total_usd REAL")

        if "transaction_count" not in ebw_columns:
            print("[Database] Migrating: Adding transaction_count column...")
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN transaction_count INTEGER")

        if "average_buy_usd" not in ebw_columns:
            print("[Database] Migrating: Adding average_buy_usd column...")
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN average_buy_usd REAL")

        if "wallet_balance_usd" not in ebw_columns:
            print("[Database] Migrating: Adding wallet_balance_usd column...")
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN wallet_balance_usd REAL")
        if "wallet_balance_usd_previous" not in ebw_columns:
            print("[Database] Migrating: Adding wallet_balance_usd_previous column...")
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN wallet_balance_usd_previous REAL")
        if "wallet_balance_updated_at" not in ebw_columns:
            print("[Database] Migrating: Adding wallet_balance_updated_at column...")
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN wallet_balance_updated_at TIMESTAMP")

        # Check if credits_used and last_analysis_credits columns exist in analyzed_tokens, if not add them
        cursor.execute("PRAGMA table_info(analyzed_tokens)")
        at_columns = [col[1] for col in cursor.fetchall()]

        if "credits_used" not in at_columns:
            print("[Database] Migrating: Adding credits_used column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN credits_used INTEGER DEFAULT 0")

        if "last_analysis_credits" not in at_columns:
            print("[Database] Migrating: Adding last_analysis_credits column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN last_analysis_credits INTEGER DEFAULT 0")

        if "market_cap_usd" not in at_columns:
            print("[Database] Migrating: Adding market_cap_usd column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN market_cap_usd REAL")

        if "market_cap_usd_current" not in at_columns:
            print("[Database] Migrating: Adding market_cap_usd_current column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN market_cap_usd_current REAL")

        if "market_cap_updated_at" not in at_columns:
            print("[Database] Migrating: Adding market_cap_updated_at column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN market_cap_updated_at TIMESTAMP")

        if "market_cap_ath" not in at_columns:
            print("[Database] Migrating: Adding market_cap_ath column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN market_cap_ath REAL")

        if "market_cap_ath_timestamp" not in at_columns:
            print("[Database] Migrating: Adding market_cap_ath_timestamp column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN market_cap_ath_timestamp TIMESTAMP")

        if "market_cap_usd_previous" not in at_columns:
            print("[Database] Migrating: Adding market_cap_usd_previous column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN market_cap_usd_previous REAL")

        if "gem_status" not in at_columns:
            print("[Database] Migrating: Adding gem_status column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN gem_status TEXT")

        if "state_version" not in at_columns:
            print("[Database] Migrating: Adding state_version column for optimistic locking...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN state_version INTEGER DEFAULT 0")
            # Backfill existing rows with 0 (ALTER TABLE DEFAULT only applies to new rows)
            cursor.execute("UPDATE analyzed_tokens SET state_version = 0 WHERE state_version IS NULL")

        if "top_holders_json" not in at_columns:
            print("[Database] Migrating: Adding top_holders_json column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN top_holders_json TEXT")

        if "top_holders_updated_at" not in at_columns:
            print("[Database] Migrating: Adding top_holders_updated_at column...")
            cursor.execute("ALTER TABLE analyzed_tokens ADD COLUMN top_holders_updated_at TIMESTAMP")

        # Fix ISO-format timestamps (convert to SQLite format)
        # Old format: 2025-01-15T12:34:56.123456
        # New format: 2025-01-15 12:34:56
        cursor.execute(
            """
            SELECT COUNT(*) FROM analyzed_tokens
            WHERE market_cap_ath_timestamp LIKE '%T%'
            """
        )
        iso_count = cursor.fetchone()[0]
        if iso_count > 0:
            print(f"[Database] Migrating: Fixing {iso_count} ISO-format timestamps in market_cap_ath_timestamp...")
            # Replace 'T' with space and truncate microseconds
            cursor.execute(
                """
                UPDATE analyzed_tokens
                SET market_cap_ath_timestamp = substr(replace(market_cap_ath_timestamp, 'T', ' '), 1, 19)
                WHERE market_cap_ath_timestamp LIKE '%T%'
                """
            )
            print(f"[Database] Fixed {iso_count} timestamps")

        # Initialize market_cap_ath from original market_cap_usd for tokens where ATH is not set
        # This ensures the "Highest" includes the original analysis market cap
        cursor.execute(
            """
            SELECT COUNT(*) FROM analyzed_tokens
            WHERE market_cap_ath IS NULL
            AND market_cap_usd IS NOT NULL
            AND market_cap_usd > 0
            """
        )
        uninitialized_count = cursor.fetchone()[0]
        if uninitialized_count > 0:
            print(
                f"[Database] Migrating: Initializing market_cap_ath from market_cap_usd for {uninitialized_count} tokens..."
            )
            cursor.execute(
                """
                UPDATE analyzed_tokens
                SET market_cap_ath = market_cap_usd,
                    market_cap_ath_timestamp = analysis_timestamp
                WHERE market_cap_ath IS NULL
                AND market_cap_usd IS NOT NULL
                AND market_cap_usd > 0
                """
            )
            print(f"[Database] Initialized {uninitialized_count} ATH values from analysis market cap")

        # Migration for analysis_run_id column in early_buyer_wallets
        if "analysis_run_id" not in ebw_columns:
            print("[Database] Migrating: Adding analysis_run_id column to early_buyer_wallets...")
            print("[Database] Warning: Existing wallet records will be linked to a default analysis run")

            # Add the column (allowing NULL temporarily for migration)
            cursor.execute("ALTER TABLE early_buyer_wallets ADD COLUMN analysis_run_id INTEGER")

            # For each existing token, create an analysis_run entry
            cursor.execute("SELECT DISTINCT token_id FROM early_buyer_wallets WHERE analysis_run_id IS NULL")
            token_ids = cursor.fetchall()

            for row in token_ids:
                token_id = row[0]
                # Get the token's analysis timestamp
                cursor.execute(
                    "SELECT analysis_timestamp, wallets_found, last_analysis_credits FROM analyzed_tokens WHERE id = ?",
                    (token_id,),
                )
                token_data = cursor.fetchone()

                if token_data:
                    analysis_timestamp, wallets_found, credits = token_data[0], token_data[1], token_data[2]

                    # Create an analysis run for this token
                    cursor.execute(
                        """
                        INSERT INTO analysis_runs (token_id, analysis_timestamp, wallets_found, credits_used)
                        VALUES (?, ?, ?, ?)
                    """,
                        (token_id, analysis_timestamp, wallets_found or 0, credits or 0),
                    )

                    analysis_run_id = cursor.lastrowid

                    # Link all existing wallets for this token to this analysis run
                    cursor.execute(
                        """
                        UPDATE early_buyer_wallets
                        SET analysis_run_id = ?
                        WHERE token_id = ? AND analysis_run_id IS NULL
                    """,
                        (analysis_run_id, token_id),
                    )

            print("[Database] Migration complete: Existing wallets linked to analysis runs")

        # Migration for is_kol column in wallet_tags
        cursor.execute("PRAGMA table_info(wallet_tags)")
        wt_columns = [col[1] for col in cursor.fetchall()]

        if "is_kol" not in wt_columns:
            print("[Database] Migrating: Adding is_kol column to wallet_tags...")
            cursor.execute("ALTER TABLE wallet_tags ADD COLUMN is_kol BOOLEAN DEFAULT 0")

        # Migration for mtew_token_positions - add tracking_enabled column
        cursor.execute("PRAGMA table_info(mtew_token_positions)")
        mtp_columns = [col[1] for col in cursor.fetchall()]

        if "tracking_enabled" not in mtp_columns:
            print("[Database] Migrating: Adding tracking_enabled column to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN tracking_enabled BOOLEAN DEFAULT 1")

        if "tracking_stopped_at" not in mtp_columns:
            print("[Database] Migrating: Adding tracking_stopped_at column to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN tracking_stopped_at TIMESTAMP")

        if "tracking_stopped_reason" not in mtp_columns:
            print("[Database] Migrating: Adding tracking_stopped_reason column to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN tracking_stopped_reason TEXT")

        # Migration for entry balance tracking (USD PnL calculation)
        if "entry_balance" not in mtp_columns:
            print("[Database] Migrating: Adding entry_balance column to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN entry_balance REAL")

        if "entry_balance_usd" not in mtp_columns:
            print("[Database] Migrating: Adding entry_balance_usd column to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN entry_balance_usd REAL")

        # Migration for multi-buy/sell aggregate tracking
        if "total_bought_tokens" not in mtp_columns:
            print("[Database] Migrating: Adding multi-buy/sell tracking columns to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN total_bought_tokens REAL DEFAULT 0")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN total_bought_usd REAL DEFAULT 0")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN total_sold_tokens REAL DEFAULT 0")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN total_sold_usd REAL DEFAULT 0")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN avg_entry_price REAL")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN realized_pnl REAL DEFAULT 0")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN buy_count INTEGER DEFAULT 1")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN sell_count INTEGER DEFAULT 0")
            # Backfill existing positions: set total_bought from entry_balance
            cursor.execute("""
                UPDATE mtew_token_positions
                SET total_bought_tokens = COALESCE(entry_balance, 0),
                    total_bought_usd = COALESCE(entry_balance_usd, 0),
                    avg_entry_price = CASE
                        WHEN entry_balance > 0 AND entry_balance_usd > 0
                        THEN entry_balance_usd / entry_balance
                        ELSE NULL
                    END
                WHERE total_bought_tokens IS NULL OR total_bought_tokens = 0
            """)
            print("[Database] Backfilled aggregate tracking data from entry balances")

        # Migration for FPnL (Fumbled PnL) tracking
        if "fpnl_ratio" not in mtp_columns:
            print("[Database] Migrating: Adding fpnl_ratio column to mtew_token_positions...")
            cursor.execute("ALTER TABLE mtew_token_positions ADD COLUMN fpnl_ratio REAL")

        # Verify all required columns exist (safeguard against data loss)
        print("[Database] Verifying schema integrity...")
        cursor.execute("PRAGMA table_info(analyzed_tokens)")
        columns = {row[1] for row in cursor.fetchall()}

        required_columns = {
            "id",
            "token_address",
            "token_name",
            "token_symbol",
            "acronym",
            "analysis_timestamp",
            "first_buy_timestamp",
            "wallets_found",
            "axiom_json",
            "webhook_id",
            "credits_used",
            "last_analysis_credits",
            "is_deleted",
            "deleted_at",
            "analysis_file_path",
            "axiom_file_path",
            "market_cap_usd",
            "market_cap_usd_current",
            "market_cap_updated_at",
            "market_cap_ath",
            "market_cap_ath_timestamp",
            "market_cap_usd_previous",
            "top_holders_json",
            "top_holders_updated_at",
        }

        missing_columns = required_columns - columns
        if missing_columns:
            error_msg = f"[Database] CRITICAL: Missing required columns: {missing_columns}\n"
            error_msg += f"[Database] Database schema is incomplete. Expected {len(required_columns)} columns, found {len(columns)}.\n"
            error_msg += f"[Database] This usually means the database file was replaced or corrupted.\n"
            error_msg += f"[Database] To recover: Run 'python backend/restore_db.py <backup_name>'"
            print(error_msg)
            raise RuntimeError(f"Database schema verification failed: missing columns {missing_columns}")

        print(f"[Database] OK Schema verified: {len(columns)} columns present")
        print("[Database] Schema initialized successfully")

        # Initialize credit tracker (creates credit_transactions table)
        global _credit_tracker_initialized
        if not _credit_tracker_initialized:
            from meridinate.credit_tracker import credit_tracker  # noqa: F401

            _credit_tracker_initialized = True
            print("[Database] Credit tracker initialized")


def save_analyzed_token(
    token_address: str,
    token_name: str,
    token_symbol: str,
    acronym: str,
    early_bidders: List[Dict],
    axiom_json: List[Dict],
    first_buy_timestamp: Optional[str] = None,
    credits_used: int = 0,
    max_wallets: int = 10,
    market_cap_usd: Optional[float] = None,
    top_holders: Optional[List[Dict]] = None,
) -> int:
    """
    Save analyzed token and its early buyers.

    Args:
        token_address: Solana token mint address
        token_name: Token name
        token_symbol: Token symbol
        acronym: Generated acronym
        early_bidders: List of early buyer wallet data
        axiom_json: Axiom wallet tracker export JSON
        first_buy_timestamp: Timestamp of first buy transaction
        credits_used: Helius API credits used for this analysis
        max_wallets: Maximum number of wallets to save
        market_cap_usd: Market capitalization in USD (optional)
        top_holders: List of top token holders data (optional)

    Returns:
        token_id: Database ID of the saved token
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Prepare top holders JSON
        top_holders_json_str = json.dumps(top_holders) if top_holders else None

        # Insert or update analyzed token
        cursor.execute(
            """
            INSERT INTO analyzed_tokens (
                token_address, token_name, token_symbol, acronym,
                first_buy_timestamp, wallets_found, axiom_json, credits_used, last_analysis_credits,
                market_cap_usd, market_cap_usd_current, market_cap_ath, market_cap_ath_timestamp, market_cap_updated_at,
                top_holders_json, top_holders_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(token_address) DO UPDATE SET
                token_name = excluded.token_name,
                token_symbol = excluded.token_symbol,
                acronym = excluded.acronym,
                analysis_timestamp = CURRENT_TIMESTAMP,
                first_buy_timestamp = excluded.first_buy_timestamp,
                wallets_found = excluded.wallets_found,
                axiom_json = excluded.axiom_json,
                credits_used = analyzed_tokens.credits_used + excluded.credits_used,
                last_analysis_credits = excluded.last_analysis_credits,
                market_cap_usd = excluded.market_cap_usd,
                top_holders_json = excluded.top_holders_json,
                top_holders_updated_at = CASE WHEN excluded.top_holders_json IS NOT NULL THEN CURRENT_TIMESTAMP ELSE analyzed_tokens.top_holders_updated_at END
        """,
            (
                token_address,
                token_name,
                token_symbol,
                acronym,
                first_buy_timestamp,
                len(early_bidders),
                json.dumps(axiom_json),
                credits_used,
                credits_used,
                market_cap_usd,
                market_cap_usd,  # Initialize current to same as analysis value
                market_cap_usd,  # Initialize ATH to same as analysis value
                top_holders_json_str,
            ),
        )

        # Get the token ID
        cursor.execute("SELECT id FROM analyzed_tokens WHERE token_address = ?", (token_address,))
        token_id = cursor.fetchone()["id"]

        # Create a new analysis run entry for this analysis
        cursor.execute(
            """
            INSERT INTO analysis_runs (token_id, wallets_found, credits_used)
            VALUES (?, ?, ?)
        """,
            (token_id, len(early_bidders), credits_used),
        )

        analysis_run_id = cursor.lastrowid
        print(f"[Database] Created analysis run #{analysis_run_id} for token {acronym}")

        # Insert early buyer wallets linked to this analysis run
        # Use INSERT OR IGNORE to skip wallets that already exist (UNIQUE constraint on token_id + wallet_address)
        # This avoids wasteful DELETE operations since earliest buyers never change (immutable blockchain data)
        inserted_count = 0
        skipped_count = 0

        for index, bidder in enumerate(early_bidders[:max_wallets], start=1):
            total_usd = bidder.get("total_usd", 0)
            # Use actual first_buy_usd from transaction, fallback to rounded total if not available
            first_buy_usd = bidder.get("first_buy_usd") or round(total_usd)
            first_buy_tokens = bidder.get("first_buy_tokens")
            entry_market_cap = bidder.get("entry_market_cap")
            transaction_count = bidder.get("transaction_count", 1)
            average_buy_usd = bidder.get("average_buy_usd", total_usd)
            wallet_balance_usd = bidder.get("wallet_balance_usd")
            axiom_name = f"({index}/{max_wallets})${round(first_buy_usd)}|{acronym}"

            cursor.execute(
                """
                INSERT OR IGNORE INTO early_buyer_wallets (
                    token_id, analysis_run_id, wallet_address, position, first_buy_usd,
                    first_buy_tokens, entry_market_cap,
                    total_usd, transaction_count, average_buy_usd,
                    first_buy_timestamp, axiom_name, wallet_balance_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    token_id,
                    analysis_run_id,
                    bidder["wallet_address"],
                    index,
                    first_buy_usd,
                    first_buy_tokens,
                    entry_market_cap,
                    total_usd,
                    transaction_count,
                    average_buy_usd,
                    bidder.get("first_buy_time"),
                    axiom_name,
                    wallet_balance_usd,
                ),
            )

            # Track if this was a new insert or ignored duplicate
            if cursor.rowcount > 0:
                inserted_count += 1
            else:
                skipped_count += 1

        if skipped_count > 0:
            print(
                f"[Database] Saved token {acronym}: {inserted_count} new wallets, {skipped_count} already existed (run #{analysis_run_id})"
            )
        else:
            print(f"[Database] Saved token {acronym} with {inserted_count} wallets (run #{analysis_run_id})")
        return token_id


def get_analyzed_tokens(limit: int = 50, include_deleted: bool = False) -> List[Dict]:
    """Get list of analyzed tokens, most recent first"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if include_deleted:
            cursor.execute(
                """
                SELECT
                    id, token_address, token_name, token_symbol, acronym,
                    analysis_timestamp, first_buy_timestamp, wallets_found, credits_used, last_analysis_credits,
                    is_deleted, deleted_at
                FROM analyzed_tokens
                ORDER BY analysis_timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    id, token_address, token_name, token_symbol, acronym,
                    analysis_timestamp, first_buy_timestamp, wallets_found, credits_used, last_analysis_credits,
                    is_deleted, deleted_at
                FROM analyzed_tokens
                WHERE is_deleted = 0 OR is_deleted IS NULL
                ORDER BY analysis_timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )

        tokens = []
        for row in cursor.fetchall():
            token_dict = dict(row)

            # Get wallet addresses for this token (from most recent analysis)
            cursor.execute(
                """
                SELECT DISTINCT ebw.wallet_address
                FROM early_buyer_wallets ebw
                JOIN analysis_runs ar ON ebw.analysis_run_id = ar.id
                WHERE ebw.token_id = ?
                ORDER BY ar.analysis_timestamp DESC
                LIMIT 10
            """,
                (token_dict["id"],),
            )

            wallet_addresses = [row[0] for row in cursor.fetchall()]
            token_dict["wallet_addresses"] = wallet_addresses

            tokens.append(token_dict)

        return tokens


def get_token_details(token_id: int) -> Optional[Dict]:
    """Get detailed information about a specific analyzed token"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get token info
        cursor.execute(
            """
            SELECT * FROM analyzed_tokens WHERE id = ?
        """,
            (token_id,),
        )

        token = cursor.fetchone()
        if not token:
            return None

        token_dict = dict(token)

        # Parse axiom_json back to list
        if token_dict.get("axiom_json"):
            token_dict["axiom_json"] = json.loads(token_dict["axiom_json"])

        # Get associated wallets from the most recent analysis run
        cursor.execute(
            """
            SELECT ebw.* FROM early_buyer_wallets ebw
            JOIN analysis_runs ar ON ebw.analysis_run_id = ar.id
            WHERE ebw.token_id = ?
            ORDER BY ar.analysis_timestamp DESC, ebw.position ASC
        """,
            (token_id,),
        )

        token_dict["wallets"] = [dict(row) for row in cursor.fetchall()]

        return token_dict


def get_token_analysis_history(token_id: int) -> List[Dict]:
    """
    Get all analysis runs for a token, most recent first.
    Each run includes its wallets.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all analysis runs for this token
        cursor.execute(
            """
            SELECT id, analysis_timestamp, wallets_found, credits_used
            FROM analysis_runs
            WHERE token_id = ?
            ORDER BY analysis_timestamp DESC
        """,
            (token_id,),
        )

        runs = []
        for run_row in cursor.fetchall():
            run_dict = dict(run_row)

            # Get wallets for this specific run
            cursor.execute(
                """
                SELECT * FROM early_buyer_wallets
                WHERE analysis_run_id = ?
                ORDER BY position ASC
            """,
                (run_dict["id"],),
            )

            run_dict["wallets"] = [dict(w) for w in cursor.fetchall()]
            runs.append(run_dict)

        return runs


def get_wallet_activity(wallet_id: int, limit: int = 50) -> List[Dict]:
    """Get activity history for a specific wallet"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM wallet_activity
            WHERE wallet_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (wallet_id, limit),
        )

        return [dict(row) for row in cursor.fetchall()]


def save_wallet_activity(
    wallet_address: str,
    transaction_signature: str,
    timestamp: str,
    activity_type: str,
    description: str,
    sol_amount: float = 0.0,
    token_amount: float = 0.0,
    recipient_address: str = None,
) -> bool:
    """Save a wallet activity event"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Find wallet_id
        cursor.execute(
            """
            SELECT id FROM early_buyer_wallets
            WHERE wallet_address = ?
            LIMIT 1
        """,
            (wallet_address,),
        )

        wallet = cursor.fetchone()
        if not wallet:
            return False  # Wallet not being tracked

        wallet_id = wallet["id"]

        # Insert activity (ignore duplicates)
        try:
            cursor.execute(
                """
                INSERT INTO wallet_activity (
                    wallet_id, transaction_signature, timestamp,
                    activity_type, description, sol_amount,
                    token_amount, recipient_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    wallet_id,
                    transaction_signature,
                    timestamp,
                    activity_type,
                    description,
                    sol_amount,
                    token_amount,
                    recipient_address,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            # Duplicate transaction signature
            return False


def get_recent_activity(limit: int = 100) -> List[Dict]:
    """Get recent wallet activity across all tracked wallets"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                wa.*,
                ebw.wallet_address,
                ebw.axiom_name,
                at.token_name,
                at.acronym
            FROM wallet_activity wa
            JOIN early_buyer_wallets ebw ON wa.wallet_id = ebw.id
            JOIN analyzed_tokens at ON ebw.token_id = at.id
            ORDER BY wa.timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        return [dict(row) for row in cursor.fetchall()]


def delete_analyzed_token(token_id: int) -> bool:
    """
    Delete an analyzed token and all associated data.

    This will CASCADE delete:
    - The token record from analyzed_tokens
    - All associated wallets from early_buyer_wallets
    - All wallet activity from wallet_activity

    Args:
        token_id: Database ID of the token to delete

    Returns:
        True if deleted successfully, False if token not found
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if token exists
        cursor.execute("SELECT id FROM analyzed_tokens WHERE id = ?", (token_id,))
        if not cursor.fetchone():
            return False

        # Delete token (CASCADE will delete wallets and activity)
        cursor.execute("DELETE FROM analyzed_tokens WHERE id = ?", (token_id,))

        print(f"[Database] Deleted token ID {token_id} and all associated data")
        return True


def search_tokens(query: str) -> List[Dict]:
    """
    Search tokens by token address, token name, symbol, acronym, or wallet address.
    Returns list of tokens that match the search (case-insensitive).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        search_pattern = f"%{query}%"

        # Search by token fields OR tokens that have matching wallets
        cursor.execute(
            """
            SELECT DISTINCT
                at.id, at.token_address, at.token_name, at.token_symbol, at.acronym,
                at.analysis_timestamp, at.first_buy_timestamp, at.wallets_found,
                at.credits_used, at.last_analysis_credits
            FROM analyzed_tokens at
            WHERE at.token_address LIKE ? COLLATE NOCASE
               OR at.token_name LIKE ? COLLATE NOCASE
               OR at.token_symbol LIKE ? COLLATE NOCASE
               OR at.acronym LIKE ? COLLATE NOCASE
               OR at.id IN (
                   SELECT DISTINCT token_id
                   FROM early_buyer_wallets
                   WHERE wallet_address LIKE ? COLLATE NOCASE
               )
            ORDER BY at.analysis_timestamp DESC
        """,
            (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern),
        )

        tokens = []
        for row in cursor.fetchall():
            tokens.append(dict(row))

        return tokens


def get_multi_token_wallets(min_tokens: int = 2) -> List[Dict]:
    """
    Find wallets that appear in multiple analyzed tokens.
    Returns list of wallets with their token appearances.

    Args:
        min_tokens: Minimum number of tokens a wallet must appear in (default: 2)

    Returns:
        List of dicts with wallet_address, token_count, and list of tokens
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Find wallets that appear in multiple tokens
        # OPTIMIZED: Use CTE with window function instead of correlated subquery
        cursor.execute(
            """
            WITH latest_balances AS (
                SELECT
                    ebw.wallet_address,
                    ebw.wallet_balance_usd,
                    ar.analysis_timestamp,
                    ROW_NUMBER() OVER (
                        PARTITION BY ebw.wallet_address
                        ORDER BY ar.analysis_timestamp DESC
                    ) as rn
                FROM early_buyer_wallets ebw
                JOIN analysis_runs ar ON ebw.analysis_run_id = ar.id
                WHERE ebw.wallet_balance_usd IS NOT NULL
            )
            SELECT
                ebw.wallet_address,
                COUNT(DISTINCT ebw.token_id) as token_count,
                GROUP_CONCAT(DISTINCT at.token_name || ' (' || at.token_symbol || ')') as token_names,
                GROUP_CONCAT(DISTINCT at.token_address) as token_addresses,
                GROUP_CONCAT(DISTINCT ebw.token_id) as token_ids,
                lb.wallet_balance_usd
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens at ON ebw.token_id = at.id
            LEFT JOIN latest_balances lb ON lb.wallet_address = ebw.wallet_address AND lb.rn = 1
            WHERE (at.is_deleted = 0 OR at.is_deleted IS NULL)
            GROUP BY ebw.wallet_address
            HAVING COUNT(DISTINCT ebw.token_id) >= ?
            ORDER BY token_count DESC, ebw.wallet_address
        """,
            (min_tokens,),
        )

        wallets = []
        for row in cursor.fetchall():
            wallets.append(
                {
                    "wallet_address": row[0],
                    "token_count": row[1],
                    "token_names": row[2].split(",") if row[2] else [],
                    "token_addresses": row[3].split(",") if row[3] else [],
                    "token_ids": [int(x) for x in row[4].split(",")] if row[4] else [],
                    "wallet_balance_usd": row[5],
                    "wallet_balance_usd_previous": row[6] if len(row) > 6 else None,
                    "wallet_balance_updated_at": row[7] if len(row) > 7 else None,
                }
            )

        return wallets


def update_wallet_balance(wallet_address: str, balance_usd: float) -> bool:
    """
    Update the wallet balance for a given wallet address in all instances.

    Args:
        wallet_address: The wallet address to update
        balance_usd: The new balance in USD

    Returns:
        True if at least one row was updated, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update balance in early_buyer_wallets table
        cursor.execute(
            """
            UPDATE early_buyer_wallets
            SET wallet_balance_usd_previous = wallet_balance_usd,
                wallet_balance_usd = ?,
                wallet_balance_updated_at = CURRENT_TIMESTAMP
            WHERE wallet_address = ?
        """,
            (balance_usd, wallet_address),
        )

        rows_updated = cursor.getrowcount()
        conn.commit()
        return rows_updated > 0

    except Exception as e:
        print(f"Error updating wallet balance for {wallet_address}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def add_wallet_tag(wallet_address: str, tag: str, is_kol: bool = False) -> bool:
    """
    Add a tag to a wallet address.

    Args:
        wallet_address: The wallet address to tag
        tag: The tag to add
        is_kol: Whether this is a KOL (Key Opinion Leader) tag

    Returns:
        True if tag was added, False if it already existed
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO wallet_tags (wallet_address, tag, is_kol)
                VALUES (?, ?, ?)
            """,
                (wallet_address, tag, 1 if is_kol else 0),
            )
            return True
        except sqlite3.IntegrityError:
            # Tag already exists for this wallet
            return False


def remove_wallet_tag(wallet_address: str, tag: str) -> bool:
    """
    Remove a tag from a wallet address.

    Args:
        wallet_address: The wallet address
        tag: The tag to remove

    Returns:
        True if tag was removed, False if it didn't exist
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM wallet_tags
            WHERE wallet_address = ? AND tag = ?
        """,
            (wallet_address, tag),
        )
        return cursor.rowcount > 0


def get_wallet_tags(wallet_address: str) -> List[Dict]:
    """
    Get all tags for a wallet address.

    Args:
        wallet_address: The wallet address

    Returns:
        List of tag dictionaries with 'tag' and 'is_kol' fields
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT tag, is_kol FROM wallet_tags
            WHERE wallet_address = ?
            ORDER BY created_at DESC
        """,
            (wallet_address,),
        )
        return [{"tag": row[0], "is_kol": bool(row[1])} for row in cursor.fetchall()]


def get_multi_wallet_tags(wallet_addresses: List[str]) -> Dict[str, List[Dict]]:
    """
    Get tags for multiple wallet addresses in a single query (batch operation).

    This fixes the N+1 query problem by fetching all tags in one database query
    instead of making separate queries for each wallet address.

    Args:
        wallet_addresses: List of wallet addresses to fetch tags for

    Returns:
        Dictionary mapping wallet_address -> list of tag dicts with 'tag' and 'is_kol' fields
    """
    if not wallet_addresses:
        return {}

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Create placeholders for IN clause
        placeholders = ",".join("?" * len(wallet_addresses))

        # Single query fetches all tags for all wallets
        cursor.execute(
            f"""
            SELECT wallet_address, tag, is_kol
            FROM wallet_tags
            WHERE wallet_address IN ({placeholders})
            ORDER BY wallet_address, created_at DESC
        """,
            wallet_addresses,
        )

        # Group results by wallet address
        result = {addr: [] for addr in wallet_addresses}
        for row in cursor.fetchall():
            wallet_addr, tag, is_kol = row
            result[wallet_addr].append({"tag": tag, "is_kol": bool(is_kol)})

        return result


def get_all_tags() -> List[str]:
    """
    Get all unique tags across all wallets.

    Returns:
        List of unique tag strings
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT tag FROM wallet_tags
            ORDER BY tag
        """
        )
        return [row[0] for row in cursor.fetchall()]


def get_wallets_by_tag(tag: str) -> List[str]:
    """
    Get all wallet addresses with a specific tag.

    Args:
        tag: The tag to search for

    Returns:
        List of wallet addresses
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT wallet_address FROM wallet_tags
            WHERE tag = ?
            ORDER BY created_at DESC
        """,
            (tag,),
        )
        return [row[0] for row in cursor.fetchall()]


def get_all_tagged_wallets() -> List[Dict]:
    """
    Get all wallets that have at least one tag (Codex).

    Returns:
        List of dictionaries with wallet_address and tags
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT wallet_address FROM wallet_tags
            ORDER BY created_at DESC
        """
        )
        wallets = []
        for row in cursor.fetchall():
            wallet_address = row[0]
            tags = get_wallet_tags(wallet_address)
            wallets.append({"wallet_address": wallet_address, "tags": tags})
        return wallets


def soft_delete_token(token_id: int) -> bool:
    """
    Soft delete a token (mark as deleted and move files to trash).

    Args:
        token_id: ID of the token to soft delete

    Returns:
        True if successful, False otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE analyzed_tokens
            SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (token_id,),
        )
        success = cursor.rowcount > 0

        if success:
            # Move files to trash
            move_files_to_trash(token_id)

        return success


def restore_token(token_id: int) -> bool:
    """
    Restore a soft-deleted token (restore from trash).

    Args:
        token_id: ID of the token to restore

    Returns:
        True if successful, False otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE analyzed_tokens
            SET is_deleted = 0, deleted_at = NULL
            WHERE id = ?
        """,
            (token_id,),
        )
        success = cursor.rowcount > 0

        if success:
            # Restore files from trash
            restore_files_from_trash(token_id)

        return success


def permanent_delete_token(token_id: int) -> bool:
    """
    Permanently delete a token and all its associated data.
    This action cannot be undone.

    Args:
        token_id: ID of the token to permanently delete

    Returns:
        True if successful, False otherwise
    """
    # Delete files first (before database record is gone)
    delete_token_files(token_id)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Delete token (CASCADE will handle related records)
        cursor.execute("DELETE FROM analyzed_tokens WHERE id = ?", (token_id,))
        return cursor.rowcount > 0


def get_deleted_tokens(limit: int = 50) -> List[Dict]:
    """
    Get list of soft-deleted tokens, most recently deleted first.

    Args:
        limit: Maximum number of tokens to return

    Returns:
        List of deleted token dictionaries
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id, token_address, token_name, token_symbol, acronym,
                analysis_timestamp, first_buy_timestamp, wallets_found, credits_used, last_analysis_credits,
                is_deleted, deleted_at
            FROM analyzed_tokens
            WHERE is_deleted = 1
            ORDER BY deleted_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        tokens = []
        for row in cursor.fetchall():
            tokens.append(dict(row))

        return tokens


def update_token_market_cap(token_id: int, market_cap_usd: Optional[float]) -> None:
    """
    Update current market cap for a token.

    Args:
        token_id: Database ID of the token
        market_cap_usd: Current market capitalization in USD
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE analyzed_tokens
            SET market_cap_usd_current = ?,
                market_cap_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (market_cap_usd, token_id),
        )

        print(
            f"[Database] Updated market cap for token {token_id}: ${market_cap_usd:,.2f}"
            if market_cap_usd
            else f"[Database] Updated market cap for token {token_id}: N/A"
        )


def update_token_market_cap_with_ath(
    token_id: int, market_cap_usd: Optional[float], market_cap_ath: Optional[float], ath_timestamp: Optional[str]
) -> None:
    """
    Update current market cap and optionally highest observed market cap.

    Note: This tracks the highest market cap we've observed through our scans,
    not the true all-time high (which would require historical data we don't have).

    If ath_timestamp is provided, it means a new peak was reached and both
    market_cap_ath and ath_timestamp will be updated. Otherwise, only
    market_cap_usd_current is updated (preserving existing peak).

    Args:
        token_id: Database ID of the token
        market_cap_usd: Current market capitalization in USD
        market_cap_ath: Highest market cap observed in USD (only updated if ath_timestamp is provided)
        ath_timestamp: Timestamp when new peak occurred (None = don't update peak)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if ath_timestamp is not None:
            # New peak reached - update both current and highest
            # Save old current to previous before updating
            cursor.execute(
                """
                UPDATE analyzed_tokens
                SET market_cap_usd_previous = market_cap_usd_current,
                    market_cap_usd_current = ?,
                    market_cap_ath = ?,
                    market_cap_ath_timestamp = ?,
                    market_cap_updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (market_cap_usd, market_cap_ath, ath_timestamp, token_id),
            )
            print(f"[Database] New peak market cap for token {token_id}: ${market_cap_ath:,.2f}")
        else:
            # No new peak - only update current market cap
            # Save old current to previous before updating
            cursor.execute(
                """
                UPDATE analyzed_tokens
                SET market_cap_usd_previous = market_cap_usd_current,
                    market_cap_usd_current = ?,
                    market_cap_updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (market_cap_usd, token_id),
            )

        print(
            f"[Database] Updated market cap for token {token_id}: ${market_cap_usd:,.2f}"
            if market_cap_usd
            else f"[Database] Updated market cap for token {token_id}: N/A"
        )


def update_multi_token_wallet_metadata(token_id: int, min_tokens: int = 2) -> int:
    """
    Update multi-token wallet metadata after an analysis completes.

    This function:
    1. Identifies wallets that just crossed the multi-token threshold (2+ tokens)
    2. Marks them as "new" in the multi_token_wallet_metadata table
    3. Clears the "new" flag from previously marked wallets

    Args:
        token_id: ID of the token that was just analyzed
        min_tokens: Minimum number of tokens to be considered multi-token (default: 2)

    Returns:
        Number of newly marked wallets
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get current multi-token wallets (wallets appearing in 2+ non-deleted tokens)
        cursor.execute(
            """
            SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON ebw.token_id = t.id
            WHERE t.deleted_at IS NULL
            GROUP BY ebw.wallet_address
            HAVING COUNT(DISTINCT ebw.token_id) >= ?
        """,
            (min_tokens,),
        )
        current_multi_token_wallets = {row[0] for row in cursor.fetchall()}

        # Get multi-token wallets EXCLUDING the just-analyzed token
        # (to identify which wallets just crossed the threshold)
        cursor.execute(
            """
            SELECT ebw.wallet_address, COUNT(DISTINCT ebw.token_id) as token_count
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON ebw.token_id = t.id
            WHERE t.deleted_at IS NULL AND ebw.token_id != ?
            GROUP BY ebw.wallet_address
            HAVING COUNT(DISTINCT ebw.token_id) >= ?
        """,
            (token_id, min_tokens),
        )
        previous_multi_token_wallets = {row[0] for row in cursor.fetchall()}

        # Wallets that just crossed the threshold (new to multi-token panel)
        newly_added_wallets = current_multi_token_wallets - previous_multi_token_wallets

        # Clear the "new" flag from all previously marked wallets
        cursor.execute("UPDATE multi_token_wallet_metadata SET marked_new = 0")

        # Mark newly added wallets as new
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for wallet_address in newly_added_wallets:
            cursor.execute(
                """
                INSERT OR REPLACE INTO multi_token_wallet_metadata
                (wallet_address, marked_new, marked_at_analysis_id, marked_at_timestamp)
                VALUES (?, 1, ?, ?)
            """,
                (wallet_address, token_id, timestamp),
            )

        if newly_added_wallets:
            print(
                f"[Database] Marked {len(newly_added_wallets)} wallet(s) as NEW in multi-token panel "
                f"after analyzing token {token_id}"
            )

        return len(newly_added_wallets)


# =============================================================================
# MTEW Position Tracking Functions
# =============================================================================


def upsert_mtew_position(
    wallet_address: str,
    token_id: int,
    entry_market_cap: Optional[float] = None,
    still_holding: bool = True,
    current_balance: Optional[float] = None,
    current_balance_usd: Optional[float] = None,
    entry_balance: Optional[float] = None,
    entry_balance_usd: Optional[float] = None,
    entry_timestamp: Optional[str] = None,
    avg_entry_price: Optional[float] = None,
    total_bought_tokens: Optional[float] = None,
    total_bought_usd: Optional[float] = None,
) -> int:
    """
    Insert or update MTEW position for a token.

    Args:
        wallet_address: MTEW wallet address
        token_id: Token ID from analyzed_tokens
        entry_market_cap: Market cap at time of scan (entry point)
        still_holding: Whether wallet still holds the token
        current_balance: Current token balance
        current_balance_usd: Current token balance in USD
        entry_balance: Token balance at entry (only set on INSERT)
        entry_balance_usd: USD value at entry (only set on INSERT)
        entry_timestamp: Actual first buy timestamp (from early_buyer_wallets)
        avg_entry_price: Average entry price per token (from early_buyer_wallets)
        total_bought_tokens: Total tokens bought (from early_buyer_wallets)
        total_bought_usd: Total USD spent on buys (from early_buyer_wallets)

    Returns:
        Position ID
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Use provided avg_entry_price, or calculate from entry_balance data as fallback
        final_avg_entry_price = avg_entry_price
        if final_avg_entry_price is None and entry_balance_usd and entry_balance and entry_balance > 0:
            final_avg_entry_price = entry_balance_usd / entry_balance

        # Use provided totals, or fall back to entry balance values
        final_total_tokens = total_bought_tokens if total_bought_tokens is not None else (entry_balance or 0)
        final_total_usd = total_bought_usd if total_bought_usd is not None else (entry_balance_usd or 0)

        # Entry values and aggregate initializers are only set on INSERT, not updated on conflict
        # If no entry_timestamp provided, falls back to CURRENT_TIMESTAMP via DEFAULT
        cursor.execute(
            """
            INSERT INTO mtew_token_positions
                (wallet_address, token_id, entry_market_cap, still_holding,
                 current_balance, current_balance_usd, entry_balance, entry_balance_usd,
                 entry_timestamp, total_bought_tokens, total_bought_usd, avg_entry_price,
                 buy_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, 1)
            ON CONFLICT(wallet_address, token_id) DO UPDATE SET
                still_holding = excluded.still_holding,
                current_balance = excluded.current_balance,
                current_balance_usd = excluded.current_balance_usd,
                position_checked_at = CURRENT_TIMESTAMP
        """,
            (wallet_address, token_id, entry_market_cap, still_holding,
             current_balance, current_balance_usd, entry_balance, entry_balance_usd,
             entry_timestamp, final_total_tokens, final_total_usd, final_avg_entry_price),
        )

        # Get the position ID
        cursor.execute(
            "SELECT id FROM mtew_token_positions WHERE wallet_address = ? AND token_id = ?",
            (wallet_address, token_id),
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def get_stale_mtew_positions(older_than_minutes: int = 15, limit: int = 100) -> List[Dict]:
    """
    Get MTEW positions that haven't been checked recently.

    Only returns positions for wallets that meet the MTEW→SWAB gate
    (min_token_count from settings).

    Args:
        older_than_minutes: Only return positions not checked in this many minutes
        limit: Maximum number of positions to return

    Returns:
        List of position dicts with wallet_address, token_id, token_address
    """
    settings = get_swab_settings()
    min_token_count = settings["min_token_count"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                p.id,
                p.wallet_address,
                p.token_id,
                t.token_address,
                p.entry_market_cap,
                p.still_holding,
                p.position_checked_at,
                p.current_balance,
                p.entry_balance,
                p.avg_entry_price,
                p.total_bought_usd
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE p.still_holding = 1
            AND (p.tracking_enabled = 1 OR p.tracking_enabled IS NULL)
            AND (
                p.position_checked_at IS NULL
                OR p.position_checked_at < datetime('now', ?)
            )
            AND p.wallet_address IN (
                SELECT wallet_address
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens at ON ebw.token_id = at.id
                WHERE at.deleted_at IS NULL
                GROUP BY wallet_address
                HAVING COUNT(DISTINCT token_id) >= ?
            )
            ORDER BY p.position_checked_at ASC NULLS FIRST
            LIMIT ?
        """,
            (f"-{older_than_minutes} minutes", min_token_count, limit),
        )

        positions = []
        for row in cursor.fetchall():
            positions.append(
                {
                    "id": row[0],
                    "wallet_address": row[1],
                    "token_id": row[2],
                    "token_address": row[3],
                    "entry_market_cap": row[4],
                    "still_holding": bool(row[5]),
                    "position_checked_at": row[6],
                    "current_balance": row[7],
                    "entry_balance": row[8],
                    "avg_entry_price": row[9],
                    "total_bought_usd": row[10],
                }
            )

        return positions


def get_position_by_token_address(wallet_address: str, token_address: str) -> Optional[Dict]:
    """
    Look up any MTEW position by wallet address and token mint address.

    Used by webhook callbacks to find positions when a token transfer is detected.
    Returns position regardless of still_holding status (for buy re-entry detection).

    Args:
        wallet_address: MTEW wallet address
        token_address: Token mint address (from webhook transfer)

    Returns:
        Position dict if found, None otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                p.id,
                p.wallet_address,
                p.token_id,
                t.token_address,
                t.token_symbol,
                p.entry_market_cap,
                p.entry_timestamp,
                p.still_holding,
                p.current_balance,
                p.entry_balance,
                p.avg_entry_price,
                p.total_bought_usd,
                p.total_bought_tokens,
                p.tracking_enabled
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE p.wallet_address = ?
            AND t.token_address = ?
        """,
            (wallet_address, token_address),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "wallet_address": row[1],
            "token_id": row[2],
            "token_address": row[3],
            "token_symbol": row[4],
            "entry_market_cap": row[5],
            "entry_timestamp": row[6],
            "still_holding": bool(row[7]),
            "current_balance": row[8],
            "entry_balance": row[9],
            "avg_entry_price": row[10],
            "total_bought_usd": row[11],
            "total_bought_tokens": row[12],
            "tracking_enabled": bool(row[13]) if row[13] is not None else True,
        }


def get_active_position_by_token_address(wallet_address: str, token_address: str) -> Optional[Dict]:
    """
    Look up an active MTEW position by wallet address and token mint address.

    Used by webhook callbacks to find positions when a token transfer is detected.

    Args:
        wallet_address: MTEW wallet address
        token_address: Token mint address (from webhook transfer)

    Returns:
        Position dict if found and still holding, None otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                p.id,
                p.wallet_address,
                p.token_id,
                t.token_address,
                t.token_symbol,
                p.entry_market_cap,
                p.entry_timestamp,
                p.still_holding,
                p.current_balance,
                p.entry_balance,
                p.avg_entry_price,
                p.total_bought_usd,
                p.total_bought_tokens,
                p.tracking_enabled
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE p.wallet_address = ?
            AND t.token_address = ?
            AND p.still_holding = 1
            AND (p.tracking_enabled = 1 OR p.tracking_enabled IS NULL)
        """,
            (wallet_address, token_address),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "wallet_address": row[1],
            "token_id": row[2],
            "token_address": row[3],
            "token_symbol": row[4],
            "entry_market_cap": row[5],
            "entry_timestamp": row[6],
            "still_holding": bool(row[7]),
            "current_balance": row[8],
            "entry_balance": row[9],
            "avg_entry_price": row[10],
            "total_bought_usd": row[11],
            "total_bought_tokens": row[12],
            "tracking_enabled": bool(row[13]) if row[13] is not None else True,
        }


def get_positions_needing_reconciliation(token_id: Optional[int] = None) -> List[Dict]:
    """
    Get sold positions that need reconciliation (missing sell data).

    These are positions where:
    - still_holding = 0 (position is sold)
    - total_sold_usd = 0 OR sell_count = 0 (sell was never recorded with actual price)

    Args:
        token_id: Optional token ID to filter by. If None, returns all positions needing reconciliation.

    Returns:
        List of position dicts with wallet_address, token_id, token_address, etc.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        base_query = """
            SELECT
                p.id,
                p.wallet_address,
                p.token_id,
                t.token_address,
                t.token_symbol,
                p.entry_market_cap,
                p.entry_timestamp,
                p.entry_balance,
                p.avg_entry_price,
                p.total_bought_usd,
                p.total_bought_tokens,
                p.exit_detected_at,
                p.pnl_ratio
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE p.still_holding = 0
            AND (COALESCE(p.total_sold_usd, 0) = 0 OR COALESCE(p.sell_count, 0) = 0)
        """

        if token_id:
            cursor.execute(base_query + " AND p.token_id = ?", (token_id,))
        else:
            cursor.execute(base_query)

        rows = cursor.fetchall()

        positions = []
        for row in rows:
            positions.append({
                "id": row[0],
                "wallet_address": row[1],
                "token_id": row[2],
                "token_address": row[3],
                "token_symbol": row[4],
                "entry_market_cap": row[5],
                "entry_timestamp": row[6],
                "entry_balance": row[7],
                "avg_entry_price": row[8],
                "total_bought_usd": row[9],
                "total_bought_tokens": row[10],
                "exit_detected_at": row[11],
                "current_pnl_ratio": row[12],
            })

        return positions


def update_position_sell_reconciliation(
    wallet_address: str,
    token_id: int,
    tokens_sold: float,
    usd_received: float,
    exit_market_cap: Optional[float] = None,
) -> bool:
    """
    Update a sold position with reconciled sell data from Helius transaction history.

    This is specifically for reconciliation - it updates sell data for positions
    that were already marked as sold but lacked accurate price information.

    Calculates and updates:
    - total_sold_tokens, total_sold_usd, sell_count
    - realized_pnl (proceeds - cost basis)
    - pnl_ratio (exit_price / entry_price)

    Args:
        wallet_address: MTEW wallet address
        token_id: Token ID
        tokens_sold: Number of tokens sold
        usd_received: USD value received from the sell
        exit_market_cap: Market cap at time of exit (optional)

    Returns:
        True if updated successfully
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get the avg_entry_price for PnL calculation
        cursor.execute(
            """
            SELECT avg_entry_price, entry_market_cap
            FROM mtew_token_positions
            WHERE wallet_address = ? AND token_id = ?
        """,
            (wallet_address, token_id),
        )
        row = cursor.fetchone()

        if not row:
            return False

        avg_entry_price = row[0] or 0
        entry_mc = row[1]

        # Cost basis for sold tokens
        cost_basis = tokens_sold * avg_entry_price if avg_entry_price else 0
        realized_pnl = usd_received - cost_basis

        # Calculate actual PnL ratio from transaction prices
        pnl_ratio = None
        if tokens_sold > 0 and avg_entry_price and avg_entry_price > 0:
            exit_price_per_token = usd_received / tokens_sold
            pnl_ratio = exit_price_per_token / avg_entry_price

        # Calculate FPnL ratio if we have market cap data
        fpnl_ratio = None
        # Note: We can't calculate fpnl_ratio during reconciliation since we don't have
        # the current market cap at the time of reconciliation. It would need to be
        # recalculated separately.

        cursor.execute(
            """
            UPDATE mtew_token_positions
            SET total_sold_tokens = ?,
                total_sold_usd = ?,
                sell_count = 1,
                realized_pnl = ?,
                pnl_ratio = ?,
                exit_market_cap = COALESCE(?, exit_market_cap),
                position_checked_at = CURRENT_TIMESTAMP
            WHERE wallet_address = ? AND token_id = ?
        """,
            (tokens_sold, usd_received, realized_pnl, pnl_ratio,
             exit_market_cap, wallet_address, token_id),
        )

        return cursor.rowcount > 0


def update_mtew_position(
    wallet_address: str,
    token_id: int,
    still_holding: bool,
    current_balance: Optional[float] = None,
    current_balance_usd: Optional[float] = None,
    pnl_ratio: Optional[float] = None,
    fpnl_ratio: Optional[float] = None,
    exit_market_cap: Optional[float] = None,
) -> bool:
    """
    Update an existing MTEW position after checking.

    Args:
        wallet_address: MTEW wallet address
        token_id: Token ID
        still_holding: Whether wallet still holds
        current_balance: Current token balance (if holding)
        current_balance_usd: Current balance in USD (if holding)
        pnl_ratio: For holding: current_mc / entry_mc. For sold: exit_price / entry_price
        fpnl_ratio: Fumbled PnL (current_mc / entry_mc) - what they missed by selling
        exit_market_cap: Market cap when exit was detected (if not holding)

    Returns:
        True if updated successfully
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if still_holding:
            cursor.execute(
                """
                UPDATE mtew_token_positions
                SET still_holding = 1,
                    current_balance = ?,
                    current_balance_usd = ?,
                    pnl_ratio = ?,
                    position_checked_at = CURRENT_TIMESTAMP
                WHERE wallet_address = ? AND token_id = ?
            """,
                (current_balance, current_balance_usd, pnl_ratio, wallet_address, token_id),
            )
        else:
            # Mark as sold
            cursor.execute(
                """
                UPDATE mtew_token_positions
                SET still_holding = 0,
                    current_balance = 0,
                    current_balance_usd = 0,
                    pnl_ratio = ?,
                    fpnl_ratio = ?,
                    exit_detected_at = CURRENT_TIMESTAMP,
                    exit_market_cap = ?,
                    position_checked_at = CURRENT_TIMESTAMP
                WHERE wallet_address = ? AND token_id = ?
            """,
                (pnl_ratio, fpnl_ratio, exit_market_cap, wallet_address, token_id),
            )

        return cursor.rowcount > 0


def record_position_buy(
    wallet_address: str,
    token_id: int,
    tokens_bought: float,
    usd_amount: float,
    current_balance: float,
    current_balance_usd: Optional[float] = None,
) -> bool:
    """
    Record a buy transaction for a position (detected via balance increase).

    Updates aggregate tracking fields:
    - Adds to total_bought_tokens and total_bought_usd
    - Increments buy_count
    - Recalculates avg_entry_price

    Args:
        wallet_address: MTEW wallet address
        token_id: Token ID
        tokens_bought: Number of tokens bought in this transaction
        usd_amount: USD value of the buy
        current_balance: New current balance after buy
        current_balance_usd: Current balance in USD

    Returns:
        True if updated successfully
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE mtew_token_positions
            SET total_bought_tokens = COALESCE(total_bought_tokens, 0) + ?,
                total_bought_usd = COALESCE(total_bought_usd, 0) + ?,
                buy_count = COALESCE(buy_count, 1) + 1,
                avg_entry_price = (COALESCE(total_bought_usd, 0) + ?) /
                                  NULLIF(COALESCE(total_bought_tokens, 0) + ?, 0),
                current_balance = ?,
                current_balance_usd = ?,
                still_holding = 1,
                position_checked_at = CURRENT_TIMESTAMP
            WHERE wallet_address = ? AND token_id = ?
        """,
            (tokens_bought, usd_amount, usd_amount, tokens_bought,
             current_balance, current_balance_usd, wallet_address, token_id),
        )

        return cursor.rowcount > 0


def record_position_sell(
    wallet_address: str,
    token_id: int,
    tokens_sold: float,
    usd_received: float,
    current_balance: float,
    current_balance_usd: Optional[float] = None,
    is_full_exit: bool = False,
    exit_market_cap: Optional[float] = None,
    entry_market_cap: Optional[float] = None,
    current_market_cap: Optional[float] = None,
) -> bool:
    """
    Record a sell transaction for a position (detected via balance decrease).

    Updates aggregate tracking fields:
    - Adds to total_sold_tokens and total_sold_usd
    - Increments sell_count
    - Calculates realized_pnl for this sell (proceeds - cost basis)
    - Calculates pnl_ratio (actual exit price / entry price)
    - Calculates fpnl_ratio (fumbled PnL: current_mc / entry_mc - what they missed)

    Args:
        wallet_address: MTEW wallet address
        token_id: Token ID
        tokens_sold: Number of tokens sold in this transaction
        usd_received: USD value received from the sell
        current_balance: New current balance after sell
        current_balance_usd: Current balance in USD
        is_full_exit: If True, sets still_holding=0
        exit_market_cap: Market cap at time of exit (if full exit)
        entry_market_cap: Entry market cap for FPnL calculation
        current_market_cap: Current market cap for FPnL calculation

    Returns:
        True if updated successfully
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # First, get the current avg_entry_price and entry_market_cap
        cursor.execute(
            """
            SELECT avg_entry_price, total_bought_tokens, total_bought_usd, entry_market_cap
            FROM mtew_token_positions
            WHERE wallet_address = ? AND token_id = ?
        """,
            (wallet_address, token_id),
        )
        row = cursor.fetchone()

        if not row:
            return False

        avg_entry_price = row[0] or 0
        stored_entry_mc = row[3]
        # Use provided entry_market_cap or fall back to stored value
        effective_entry_mc = entry_market_cap or stored_entry_mc

        # Cost basis for sold tokens = tokens_sold * avg_entry_price
        cost_basis = tokens_sold * avg_entry_price if avg_entry_price else 0
        realized_pnl_delta = usd_received - cost_basis

        # Calculate actual PnL ratio from transaction prices (exit_price / entry_price)
        # This is the TRUE multiplier - what they actually made
        pnl_ratio = None
        if tokens_sold > 0 and avg_entry_price and avg_entry_price > 0:
            exit_price_per_token = usd_received / tokens_sold
            pnl_ratio = exit_price_per_token / avg_entry_price

        # Calculate FPnL ratio (Fumbled PnL) = current_mc / entry_mc
        # This shows what they WOULD have made if they held
        fpnl_ratio = None
        if effective_entry_mc and effective_entry_mc > 0 and current_market_cap:
            fpnl_ratio = current_market_cap / effective_entry_mc

        if is_full_exit:
            # Full exit - mark position as sold
            cursor.execute(
                """
                UPDATE mtew_token_positions
                SET total_sold_tokens = COALESCE(total_sold_tokens, 0) + ?,
                    total_sold_usd = COALESCE(total_sold_usd, 0) + ?,
                    sell_count = COALESCE(sell_count, 0) + 1,
                    realized_pnl = COALESCE(realized_pnl, 0) + ?,
                    pnl_ratio = ?,
                    fpnl_ratio = ?,
                    current_balance = 0,
                    current_balance_usd = 0,
                    still_holding = 0,
                    exit_detected_at = CURRENT_TIMESTAMP,
                    exit_market_cap = ?,
                    position_checked_at = CURRENT_TIMESTAMP
                WHERE wallet_address = ? AND token_id = ?
            """,
                (tokens_sold, usd_received, realized_pnl_delta, pnl_ratio, fpnl_ratio,
                 exit_market_cap, wallet_address, token_id),
            )
        else:
            # Partial sell - still holding
            cursor.execute(
                """
                UPDATE mtew_token_positions
                SET total_sold_tokens = COALESCE(total_sold_tokens, 0) + ?,
                    total_sold_usd = COALESCE(total_sold_usd, 0) + ?,
                    sell_count = COALESCE(sell_count, 0) + 1,
                    realized_pnl = COALESCE(realized_pnl, 0) + ?,
                    current_balance = ?,
                    current_balance_usd = ?,
                    position_checked_at = CURRENT_TIMESTAMP
                WHERE wallet_address = ? AND token_id = ?
            """,
                (tokens_sold, usd_received, realized_pnl_delta,
                 current_balance, current_balance_usd, wallet_address, token_id),
            )

        return cursor.rowcount > 0


def get_wallet_positions(wallet_address: str) -> List[Dict]:
    """
    Get all positions for a specific wallet.

    Args:
        wallet_address: Wallet address to query

    Returns:
        List of position dicts with token info and metrics
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                p.id,
                p.token_id,
                t.token_name,
                t.token_symbol,
                t.token_address,
                p.entry_timestamp,
                p.entry_market_cap,
                p.still_holding,
                p.current_balance,
                p.current_balance_usd,
                p.pnl_ratio,
                p.exit_detected_at,
                p.exit_market_cap,
                t.market_cap_usd_current
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE p.wallet_address = ?
            ORDER BY p.entry_timestamp DESC
        """,
            (wallet_address,),
        )

        positions = []
        for row in cursor.fetchall():
            positions.append(
                {
                    "id": row[0],
                    "token_id": row[1],
                    "token_name": row[2],
                    "token_symbol": row[3],
                    "token_address": row[4],
                    "entry_timestamp": row[5],
                    "entry_market_cap": row[6],
                    "still_holding": bool(row[7]),
                    "current_balance": row[8],
                    "current_balance_usd": row[9],
                    "pnl_ratio": row[10],
                    "exit_detected_at": row[11],
                    "exit_market_cap": row[12],
                    "current_market_cap": row[13],
                }
            )

        return positions


def calculate_wallet_metrics(wallet_address: str) -> Dict:
    """
    Calculate and update win rate metrics for a wallet based on positions.

    Args:
        wallet_address: Wallet address to calculate metrics for

    Returns:
        Dict with win_count, loss_count, win_rate, avg_pnl_ratio
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all positions with valid PnL ratios
        cursor.execute(
            """
            SELECT pnl_ratio
            FROM mtew_token_positions
            WHERE wallet_address = ?
            AND pnl_ratio IS NOT NULL
        """,
            (wallet_address,),
        )

        pnl_ratios = [row[0] for row in cursor.fetchall()]

        if not pnl_ratios:
            return {
                "win_count": 0,
                "loss_count": 0,
                "total_positions": 0,
                "win_rate": None,
                "avg_pnl_ratio": None,
            }

        win_count = sum(1 for pnl in pnl_ratios if pnl > 1.0)
        loss_count = sum(1 for pnl in pnl_ratios if pnl <= 1.0)
        total_positions = len(pnl_ratios)
        win_rate = win_count / total_positions if total_positions > 0 else 0
        avg_pnl_ratio = sum(pnl_ratios) / total_positions if total_positions > 0 else 0

        # Update wallet_metrics table
        cursor.execute(
            """
            INSERT INTO wallet_metrics
                (wallet_address, win_count, loss_count, total_positions, win_rate, avg_pnl_ratio, metrics_updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(wallet_address) DO UPDATE SET
                win_count = excluded.win_count,
                loss_count = excluded.loss_count,
                total_positions = excluded.total_positions,
                win_rate = excluded.win_rate,
                avg_pnl_ratio = excluded.avg_pnl_ratio,
                metrics_updated_at = CURRENT_TIMESTAMP
        """,
            (wallet_address, win_count, loss_count, total_positions, win_rate, avg_pnl_ratio),
        )

        return {
            "win_count": win_count,
            "loss_count": loss_count,
            "total_positions": total_positions,
            "win_rate": win_rate,
            "avg_pnl_ratio": avg_pnl_ratio,
        }


def get_wallet_metrics(wallet_address: str) -> Optional[Dict]:
    """
    Get cached wallet metrics.

    Args:
        wallet_address: Wallet address to query

    Returns:
        Dict with metrics or None if not calculated yet
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT win_count, loss_count, total_positions, win_rate, avg_pnl_ratio, metrics_updated_at
            FROM wallet_metrics
            WHERE wallet_address = ?
        """,
            (wallet_address,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "win_count": row[0],
            "loss_count": row[1],
            "total_positions": row[2],
            "win_rate": row[3],
            "avg_pnl_ratio": row[4],
            "metrics_updated_at": row[5],
        }


def get_multi_token_wallets_for_token(token_id: int, min_tokens: int = 2) -> List[str]:
    """
    Get wallets that are/will become MTEWs after this token scan.

    Args:
        token_id: The token being scanned
        min_tokens: Minimum tokens to qualify as MTEW (default: 2)

    Returns:
        List of wallet addresses that are or will become MTEWs
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get early buyers for this token
        cursor.execute(
            """
            SELECT DISTINCT wallet_address
            FROM early_buyer_wallets
            WHERE token_id = ?
        """,
            (token_id,),
        )
        token_wallets = {row[0] for row in cursor.fetchall()}

        # Get wallets that are already MTEWs (in 2+ tokens)
        cursor.execute(
            """
            SELECT wallet_address, COUNT(DISTINCT token_id) as token_count
            FROM early_buyer_wallets ebw
            JOIN analyzed_tokens t ON ebw.token_id = t.id
            WHERE t.deleted_at IS NULL
            GROUP BY wallet_address
            HAVING COUNT(DISTINCT token_id) >= ?
        """,
            (min_tokens,),
        )
        existing_mtews = {row[0] for row in cursor.fetchall()}

        # Wallets in this token that are MTEWs
        mtews_in_token = token_wallets & existing_mtews

        # Also check wallets that JUST became MTEWs with this token
        # (they were in exactly 1 other token before)
        cursor.execute(
            """
            SELECT wallet_address
            FROM (
                SELECT wallet_address, COUNT(DISTINCT token_id) as token_count
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL AND ebw.token_id != ?
                GROUP BY wallet_address
            )
            WHERE token_count = 1
        """,
            (token_id,),
        )
        wallets_with_one_other = {row[0] for row in cursor.fetchall()}
        newly_minted_mtews = token_wallets & wallets_with_one_other

        return list(mtews_in_token | newly_minted_mtews)


# =============================================================================
# SWAB (Smart Wallet Archive Builder) Functions
# =============================================================================


def get_swab_settings() -> Dict:
    """
    Get SWAB configuration settings.

    Returns:
        Dict with SWAB settings
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT auto_check_enabled, check_interval_minutes, daily_credit_budget,
                   stale_threshold_minutes, min_token_count, last_check_at,
                   credits_used_today, credits_reset_date, updated_at
            FROM swab_settings
            WHERE id = 1
        """
        )

        row = cursor.fetchone()
        if row:
            return {
                "auto_check_enabled": bool(row[0]),
                "check_interval_minutes": row[1],
                "daily_credit_budget": row[2],
                "stale_threshold_minutes": row[3],
                "min_token_count": row[4],
                "last_check_at": row[5],
                "credits_used_today": row[6] or 0,
                "credits_reset_date": row[7],
                "updated_at": row[8],
            }

        # Return defaults if not found
        return {
            "auto_check_enabled": False,
            "check_interval_minutes": 30,
            "daily_credit_budget": 500,
            "stale_threshold_minutes": 15,
            "min_token_count": 2,
            "last_check_at": None,
            "credits_used_today": 0,
            "credits_reset_date": None,
            "updated_at": None,
        }


def update_swab_settings(
    auto_check_enabled: Optional[bool] = None,
    check_interval_minutes: Optional[int] = None,
    daily_credit_budget: Optional[int] = None,
    stale_threshold_minutes: Optional[int] = None,
    min_token_count: Optional[int] = None,
) -> Dict:
    """
    Update SWAB configuration settings.

    Args:
        auto_check_enabled: Enable/disable auto-check
        check_interval_minutes: Interval between checks
        daily_credit_budget: Max credits per day for SWAB
        stale_threshold_minutes: Position is stale after this many minutes
        min_token_count: Minimum tokens for MTEW to be tracked

    Returns:
        Updated settings dict
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build dynamic update query
        updates = []
        params = []

        if auto_check_enabled is not None:
            updates.append("auto_check_enabled = ?")
            params.append(1 if auto_check_enabled else 0)

        if check_interval_minutes is not None:
            updates.append("check_interval_minutes = ?")
            params.append(check_interval_minutes)

        if daily_credit_budget is not None:
            updates.append("daily_credit_budget = ?")
            params.append(daily_credit_budget)

        if stale_threshold_minutes is not None:
            updates.append("stale_threshold_minutes = ?")
            params.append(stale_threshold_minutes)

        if min_token_count is not None:
            updates.append("min_token_count = ?")
            params.append(min_token_count)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE swab_settings SET {', '.join(updates)} WHERE id = 1"
            cursor.execute(query, params)

    return get_swab_settings()


def update_swab_last_check(credits_used: int = 0) -> None:
    """
    Update SWAB last check timestamp and credits used.

    Args:
        credits_used: Credits used in this check cycle
    """
    today = datetime.now().strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if we need to reset daily credits
        cursor.execute("SELECT credits_reset_date FROM swab_settings WHERE id = 1")
        row = cursor.fetchone()
        current_reset_date = row[0] if row else None

        if current_reset_date != today:
            # New day - reset credits
            cursor.execute(
                """
                UPDATE swab_settings
                SET last_check_at = CURRENT_TIMESTAMP,
                    credits_used_today = ?,
                    credits_reset_date = ?
                WHERE id = 1
            """,
                (credits_used, today),
            )
        else:
            # Same day - add to credits
            cursor.execute(
                """
                UPDATE swab_settings
                SET last_check_at = CURRENT_TIMESTAMP,
                    credits_used_today = credits_used_today + ?
                WHERE id = 1
            """,
                (credits_used,),
            )


def get_swab_positions(
    min_token_count: Optional[int] = None,
    status_filter: Optional[str] = None,  # 'holding', 'sold', 'stale', 'all'
    pnl_min: Optional[float] = None,
    pnl_max: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict:
    """
    Get positions for SWAB display with filters.

    Args:
        min_token_count: Minimum tokens for MTEW to be included
        status_filter: Filter by status ('holding', 'sold', 'stale', 'all')
        pnl_min: Minimum PnL ratio filter
        pnl_max: Maximum PnL ratio filter
        limit: Max positions to return
        offset: Pagination offset

    Returns:
        Dict with positions list and pagination info
    """
    if min_token_count is None:
        settings = get_swab_settings()
        min_token_count = settings["min_token_count"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Build WHERE clause - no longer filter by tracking_enabled by default
        # We want to show ALL positions (including sold/stopped) for qualifying wallets
        where_clauses = []
        params = []

        # Filter by MTEW token count
        where_clauses.append(
            """
            p.wallet_address IN (
                SELECT wallet_address
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL
                GROUP BY wallet_address
                HAVING COUNT(DISTINCT token_id) >= ?
            )
        """
        )
        params.append(min_token_count)

        # Status filter
        if status_filter == "holding":
            # Only active, still-holding positions
            where_clauses.append("p.still_holding = 1")
            where_clauses.append("(p.tracking_enabled = 1 OR p.tracking_enabled IS NULL)")
        elif status_filter == "sold":
            # Only sold positions (tracking stopped)
            where_clauses.append("p.still_holding = 0")
        elif status_filter == "stale":
            settings = get_swab_settings()
            where_clauses.append("p.still_holding = 1")
            where_clauses.append("(p.tracking_enabled = 1 OR p.tracking_enabled IS NULL)")
            where_clauses.append(
                "(p.position_checked_at IS NULL OR p.position_checked_at < datetime('now', ?))"
            )
            params.append(f"-{settings['stale_threshold_minutes']} minutes")
        # 'all' or None - show everything for qualifying wallets

        # PnL filters
        if pnl_min is not None:
            where_clauses.append("p.pnl_ratio >= ?")
            params.append(pnl_min)

        if pnl_max is not None:
            where_clauses.append("p.pnl_ratio <= ?")
            params.append(pnl_max)

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_query = f"""
            SELECT COUNT(*)
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE {where_sql}
        """
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Get positions with pagination
        query = f"""
            SELECT
                p.id,
                p.wallet_address,
                p.token_id,
                t.token_name,
                t.token_symbol,
                t.token_address,
                p.entry_timestamp,
                p.entry_market_cap,
                t.market_cap_usd_current,
                p.still_holding,
                p.current_balance,
                p.current_balance_usd,
                p.pnl_ratio,
                p.fpnl_ratio,
                p.exit_detected_at,
                p.exit_market_cap,
                p.position_checked_at,
                p.tracking_enabled,
                p.tracking_stopped_at,
                p.tracking_stopped_reason,
                p.entry_balance,
                p.entry_balance_usd,
                -- Calculate hold time in seconds
                CAST((julianday(COALESCE(p.exit_detected_at, 'now')) - julianday(p.entry_timestamp)) * 86400 AS INTEGER) as hold_time_seconds
            FROM mtew_token_positions p
            JOIN analyzed_tokens t ON p.token_id = t.id
            WHERE {where_sql}
            ORDER BY p.entry_timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor.execute(query, params)

        positions = []
        for row in cursor.fetchall():
            # Row indices:
            # 0: id, 1: wallet_address, 2: token_id, 3: token_name, 4: token_symbol,
            # 5: token_address, 6: entry_timestamp, 7: entry_market_cap, 8: market_cap_usd_current,
            # 9: still_holding, 10: current_balance, 11: current_balance_usd, 12: pnl_ratio,
            # 13: fpnl_ratio, 14: exit_detected_at, 15: exit_market_cap, 16: position_checked_at,
            # 17: tracking_enabled, 18: tracking_stopped_at, 19: tracking_stopped_reason,
            # 20: entry_balance, 21: entry_balance_usd, 22: hold_time_seconds
            entry_balance_usd = row[21]
            current_balance_usd = row[11]
            # Calculate USD PnL (realized or unrealized)
            pnl_usd = None
            if entry_balance_usd is not None and current_balance_usd is not None:
                pnl_usd = current_balance_usd - entry_balance_usd

            # Calculate FPnL dynamically for sold positions: current_mc / entry_mc
            # This shows what they would have NOW if they held (tracks current price)
            entry_mc = row[7]
            current_mc = row[8]
            stored_fpnl = row[13]
            still_holding = bool(row[9])

            # For sold positions, calculate dynamic FPnL from current market cap
            # For holding positions, use stored value (updated during position checks)
            if not still_holding and entry_mc and entry_mc > 0 and current_mc:
                dynamic_fpnl = current_mc / entry_mc
            else:
                dynamic_fpnl = stored_fpnl

            positions.append(
                {
                    "id": row[0],
                    "wallet_address": row[1],
                    "token_id": row[2],
                    "token_name": row[3],
                    "token_symbol": row[4],
                    "token_address": row[5],
                    "entry_timestamp": row[6],
                    "entry_market_cap": entry_mc,
                    "current_market_cap": current_mc,
                    "still_holding": still_holding,
                    "current_balance": row[10],
                    "current_balance_usd": row[11],
                    "pnl_ratio": row[12],
                    "fpnl_ratio": dynamic_fpnl,  # Dynamic for sold, stored for holding
                    "exit_detected_at": row[14],
                    "exit_market_cap": row[15],
                    "position_checked_at": row[16],
                    "tracking_enabled": bool(row[17]) if row[17] is not None else True,
                    "tracking_stopped_at": row[18],
                    "tracking_stopped_reason": row[19],
                    "entry_balance": row[20],
                    "entry_balance_usd": entry_balance_usd,
                    "pnl_usd": pnl_usd,
                    "hold_time_seconds": row[22],
                }
            )

        return {
            "positions": positions,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(positions) < total_count,
        }


def get_swab_wallet_summary(min_token_count: Optional[int] = None) -> List[Dict]:
    """
    Get aggregated wallet summary for SWAB display.

    Args:
        min_token_count: Minimum tokens for MTEW to be included

    Returns:
        List of wallet summaries with win rate, avg pnl, position counts
    """
    if min_token_count is None:
        settings = get_swab_settings()
        min_token_count = settings["min_token_count"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                p.wallet_address,
                COUNT(*) as total_positions,
                SUM(CASE WHEN p.still_holding = 1 AND p.tracking_enabled = 1 THEN 1 ELSE 0 END) as holding_count,
                SUM(CASE WHEN p.still_holding = 0 THEN 1 ELSE 0 END) as sold_count,
                SUM(CASE WHEN p.pnl_ratio > 1.0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN p.pnl_ratio <= 1.0 AND p.pnl_ratio IS NOT NULL THEN 1 ELSE 0 END) as loss_count,
                AVG(p.pnl_ratio) as avg_pnl_ratio,
                MAX(p.position_checked_at) as last_checked
            FROM mtew_token_positions p
            WHERE p.wallet_address IN (
                SELECT wallet_address
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL
                GROUP BY wallet_address
                HAVING COUNT(DISTINCT token_id) >= ?
            )
            GROUP BY p.wallet_address
            ORDER BY AVG(p.pnl_ratio) DESC NULLS LAST
        """,
            (min_token_count,),
        )

        wallets = []
        for row in cursor.fetchall():
            total = row[1]
            wins = row[4] or 0
            losses = row[5] or 0

            win_rate = None
            if wins + losses > 0:
                win_rate = wins / (wins + losses)

            wallets.append(
                {
                    "wallet_address": row[0],
                    "total_positions": total,
                    "holding_count": row[2] or 0,
                    "sold_count": row[3] or 0,
                    "win_count": wins,
                    "loss_count": losses,
                    "win_rate": win_rate,
                    "avg_pnl_ratio": row[6],
                    "last_checked": row[7],
                }
            )

        return wallets


def get_swab_stats() -> Dict:
    """
    Get overview statistics for SWAB.

    Returns:
        Dict with total positions, win rate, avg pnl, etc.
    """
    settings = get_swab_settings()
    min_token_count = settings["min_token_count"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get position counts - filtered by MTEW token count gate
        # Now counts ALL positions (including sold) for qualifying wallets
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_positions,
                SUM(CASE WHEN still_holding = 1 AND (tracking_enabled = 1 OR tracking_enabled IS NULL) THEN 1 ELSE 0 END) as holding,
                SUM(CASE WHEN still_holding = 0 THEN 1 ELSE 0 END) as sold,
                SUM(CASE WHEN pnl_ratio > 1.0 THEN 1 ELSE 0 END) as winners,
                SUM(CASE WHEN pnl_ratio <= 1.0 AND pnl_ratio IS NOT NULL THEN 1 ELSE 0 END) as losers,
                AVG(pnl_ratio) as avg_pnl,
                COUNT(DISTINCT wallet_address) as unique_wallets,
                COUNT(DISTINCT token_id) as unique_tokens
            FROM mtew_token_positions
            WHERE wallet_address IN (
                SELECT wallet_address
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL
                GROUP BY wallet_address
                HAVING COUNT(DISTINCT token_id) >= ?
            )
        """,
            (min_token_count,),
        )

        row = cursor.fetchone()
        total = row[0] or 0
        holding = row[1] or 0
        sold = row[2] or 0
        winners = row[3] or 0
        losers = row[4] or 0
        avg_pnl = row[5]
        unique_wallets = row[6] or 0
        unique_tokens = row[7] or 0

        # Win rate calculation
        win_rate = None
        if winners + losers > 0:
            win_rate = winners / (winners + losers)

        # Count stale positions - filtered by MTEW token count gate
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM mtew_token_positions
            WHERE still_holding = 1
            AND tracking_enabled = 1
            AND (position_checked_at IS NULL OR position_checked_at < datetime('now', ?))
            AND wallet_address IN (
                SELECT wallet_address
                FROM early_buyer_wallets ebw
                JOIN analyzed_tokens t ON ebw.token_id = t.id
                WHERE t.deleted_at IS NULL
                GROUP BY wallet_address
                HAVING COUNT(DISTINCT token_id) >= ?
            )
        """,
            (f"-{settings['stale_threshold_minutes']} minutes", min_token_count),
        )
        stale_count = cursor.fetchone()[0]

        # Estimate credits for checking stale positions
        estimated_credits = stale_count * 10  # 10 credits per position check

        return {
            "total_positions": total,
            "holding": holding,
            "sold": sold,
            "winners": winners,
            "losers": losers,
            "win_rate": win_rate,
            "avg_pnl_ratio": avg_pnl,
            "unique_wallets": unique_wallets,
            "unique_tokens": unique_tokens,
            "stale_positions": stale_count,
            "estimated_check_credits": estimated_credits,
            "credits_used_today": settings["credits_used_today"],
            "daily_credit_budget": settings["daily_credit_budget"],
            "credits_remaining": settings["daily_credit_budget"] - settings["credits_used_today"],
        }


def get_active_swab_wallets() -> List[str]:
    """
    Get all unique wallet addresses with active SWAB positions.

    Used to create a Helius webhook for real-time sell detection.
    Only returns wallets that:
    - Have at least one position still holding
    - Have tracking enabled

    Returns:
        List of unique wallet addresses
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT wallet_address
            FROM mtew_token_positions
            WHERE still_holding = 1
            AND (tracking_enabled = 1 OR tracking_enabled IS NULL)
            ORDER BY wallet_address
        """
        )

        return [row[0] for row in cursor.fetchall()]


def stop_tracking_position(position_id: int, reason: str = "manual") -> bool:
    """
    Stop tracking a specific position.

    Args:
        position_id: Position ID to stop tracking
        reason: Reason for stopping ('manual', 'sold', etc.)

    Returns:
        True if stopped successfully
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE mtew_token_positions
            SET tracking_enabled = 0,
                tracking_stopped_at = CURRENT_TIMESTAMP,
                tracking_stopped_reason = ?
            WHERE id = ?
        """,
            (reason, position_id),
        )

        return cursor.rowcount > 0


def stop_tracking_wallet_positions(wallet_address: str, reason: str = "manual") -> int:
    """
    Stop tracking all positions for a wallet.

    Args:
        wallet_address: Wallet address to stop tracking
        reason: Reason for stopping

    Returns:
        Number of positions stopped
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE mtew_token_positions
            SET tracking_enabled = 0,
                tracking_stopped_at = CURRENT_TIMESTAMP,
                tracking_stopped_reason = ?
            WHERE wallet_address = ?
            AND tracking_enabled = 1
        """,
            (reason, wallet_address),
        )

        return cursor.rowcount


def resume_tracking_position(position_id: int) -> bool:
    """
    Resume tracking a previously stopped position.

    Args:
        position_id: Position ID to resume tracking

    Returns:
        True if resumed successfully
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE mtew_token_positions
            SET tracking_enabled = 1,
                tracking_stopped_at = NULL,
                tracking_stopped_reason = NULL
            WHERE id = ?
        """,
            (position_id,),
        )

        return cursor.rowcount > 0


# =============================================================================
# Smart/Dumb Wallet Label Functions
# =============================================================================

# Constants for label thresholds
SMART_EXPECTANCY_THRESHOLD = 0.5
DUMB_EXPECTANCY_THRESHOLD = -0.2
MIN_CLOSED_POSITIONS = 5
PNL_CAP_MAX = 10.0  # Cap wins at 10x to prevent outlier skewing
PNL_CAP_MIN = 0.1   # Cap losses at 0.1x


def calculate_wallet_expectancy(wallet_address: str) -> Dict[str, Any]:
    """
    Calculate expectancy score for a wallet based on closed (sold) positions.

    Expectancy = (Win% × Avg_Capped_Win) - (Loss% × Avg_Capped_Loss)

    Where wins/losses are capped at PNL_CAP_MAX/PNL_CAP_MIN to prevent
    outliers from skewing the score.

    Args:
        wallet_address: Wallet address to calculate expectancy for

    Returns:
        Dict with expectancy score, win_rate, avg_pnl, closed_count, and suggested_label
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all closed positions (sold) with PnL data
        cursor.execute(
            """
            SELECT pnl_ratio
            FROM mtew_token_positions
            WHERE wallet_address = ?
            AND still_holding = 0
            AND pnl_ratio IS NOT NULL
        """,
            (wallet_address,),
        )

        pnl_values = [row[0] for row in cursor.fetchall()]

    if not pnl_values:
        return {
            "wallet_address": wallet_address,
            "expectancy": None,
            "win_rate": None,
            "avg_pnl": None,
            "closed_count": 0,
            "suggested_label": None,
        }

    # Cap PnL values to prevent outlier skewing
    capped_pnl = [
        max(PNL_CAP_MIN, min(PNL_CAP_MAX, pnl)) for pnl in pnl_values
    ]

    # Calculate metrics
    wins = [p for p in capped_pnl if p > 1.0]
    losses = [p for p in capped_pnl if p <= 1.0]

    win_count = len(wins)
    loss_count = len(losses)
    total = win_count + loss_count

    win_rate = win_count / total if total > 0 else 0

    # Average win size (excess over 1.0)
    avg_win_size = (sum(wins) / len(wins) - 1.0) if wins else 0

    # Average loss size (shortfall from 1.0)
    avg_loss_size = (1.0 - sum(losses) / len(losses)) if losses else 0

    # Expectancy formula
    loss_rate = 1 - win_rate
    expectancy = (win_rate * avg_win_size) - (loss_rate * avg_loss_size)

    # Average PnL (uncapped for display)
    avg_pnl = sum(pnl_values) / len(pnl_values)

    # Determine suggested label
    suggested_label = None
    if total >= MIN_CLOSED_POSITIONS:
        if expectancy > SMART_EXPECTANCY_THRESHOLD:
            suggested_label = "Smart"
        elif expectancy < DUMB_EXPECTANCY_THRESHOLD:
            suggested_label = "Dumb"

    return {
        "wallet_address": wallet_address,
        "expectancy": round(expectancy, 3),
        "win_rate": round(win_rate, 3),
        "avg_pnl": round(avg_pnl, 2),
        "closed_count": total,
        "suggested_label": suggested_label,
    }


def update_wallet_smart_dumb_label(wallet_address: str) -> Optional[str]:
    """
    Calculate expectancy and update Smart/Dumb label for a wallet.

    Removes any existing Smart/Dumb label and adds the new one if applicable.
    Uses hysteresis to prevent label flapping near thresholds.

    Args:
        wallet_address: Wallet address to update label for

    Returns:
        The new label ('Smart', 'Dumb', or None if unlabeled)
    """
    metrics = calculate_wallet_expectancy(wallet_address)
    suggested_label = metrics["suggested_label"]

    # Get current labels
    current_tags = get_wallet_tags(wallet_address)
    current_label = None
    for tag in current_tags:
        if tag["tag"] in ("Smart", "Dumb"):
            current_label = tag["tag"]
            break

    # Apply hysteresis - harder to remove a label than to gain it
    # If currently labeled, require stronger evidence to change
    if current_label == "Smart" and suggested_label != "Smart":
        # To lose Smart label, expectancy must drop below 0.3 (not just below 0.5)
        if metrics["expectancy"] is not None and metrics["expectancy"] > 0.3:
            suggested_label = "Smart"  # Keep Smart label

    if current_label == "Dumb" and suggested_label != "Dumb":
        # To lose Dumb label, expectancy must rise above 0.0 (not just above -0.2)
        if metrics["expectancy"] is not None and metrics["expectancy"] < 0.0:
            suggested_label = "Dumb"  # Keep Dumb label

    # Remove existing Smart/Dumb labels
    if current_label:
        remove_wallet_tag(wallet_address, current_label)

    # Add new label if applicable
    if suggested_label:
        add_wallet_tag(wallet_address, suggested_label, is_kol=False)

    return suggested_label


def batch_update_wallet_labels(wallet_addresses: List[str]) -> Dict[str, Optional[str]]:
    """
    Update Smart/Dumb labels for multiple wallets.

    Args:
        wallet_addresses: List of wallet addresses to update

    Returns:
        Dict mapping wallet_address -> new label (or None)
    """
    results = {}
    for wallet_address in wallet_addresses:
        results[wallet_address] = update_wallet_smart_dumb_label(wallet_address)
    return results


def get_all_wallet_expectancies(min_closed: int = MIN_CLOSED_POSITIONS) -> List[Dict]:
    """
    Get expectancy metrics for all wallets with sufficient closed positions.

    Args:
        min_closed: Minimum closed positions required

    Returns:
        List of wallet expectancy dicts sorted by expectancy descending
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all wallets with closed positions
        cursor.execute(
            """
            SELECT DISTINCT wallet_address
            FROM mtew_token_positions
            WHERE still_holding = 0
            AND pnl_ratio IS NOT NULL
        """
        )

        wallets = [row[0] for row in cursor.fetchall()]

    results = []
    for wallet in wallets:
        metrics = calculate_wallet_expectancy(wallet)
        if metrics["closed_count"] >= min_closed:
            results.append(metrics)

    # Sort by expectancy descending
    results.sort(key=lambda x: x["expectancy"] or 0, reverse=True)
    return results


def purge_swab_data() -> Dict[str, int]:
    """
    Purge all SWAB position tracking data for a fresh start.

    This deletes:
    - All records from mtew_token_positions
    - All records from mtew_wallet_metrics (if exists)

    Returns:
        Dict with positions_deleted and metrics_deleted counts
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Delete all positions
        cursor.execute("DELETE FROM mtew_token_positions")
        positions_deleted = cursor.rowcount

        # Delete all wallet metrics (if table exists)
        metrics_deleted = 0
        try:
            cursor.execute("DELETE FROM mtew_wallet_metrics")
            metrics_deleted = cursor.rowcount
        except Exception:
            # Table may not exist
            pass

        # Also remove Smart/Dumb tags from wallets
        try:
            cursor.execute(
                """
                DELETE FROM wallet_tags
                WHERE tag IN ('smart', 'dumb', 'Smart', 'Dumb')
                """
            )
        except Exception:
            pass

    return {
        "positions_deleted": positions_deleted,
        "metrics_deleted": metrics_deleted,
    }


# Initialize database on module import
init_database()
