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
from typing import Dict, List, Optional

# Use absolute path to ensure database is always in the backend directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(SCRIPT_DIR, "analyzed_tokens.db")
ANALYSIS_RESULTS_DIR = os.path.join(SCRIPT_DIR, "analysis_results")
AXIOM_EXPORTS_DIR = os.path.join(SCRIPT_DIR, "axiom_exports")


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
                market_cap_updated_at TIMESTAMP
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

        # Verify all required columns exist (safeguard against data loss)
        print("[Database] Verifying schema integrity...")
        cursor.execute("PRAGMA table_info(analyzed_tokens)")
        columns = {row[1] for row in cursor.fetchall()}

        required_columns = {
            "id", "token_address", "token_name", "token_symbol", "acronym",
            "analysis_timestamp", "first_buy_timestamp", "wallets_found",
            "axiom_json", "webhook_id", "credits_used", "last_analysis_credits",
            "is_deleted", "deleted_at", "analysis_file_path", "axiom_file_path",
            "market_cap_usd", "market_cap_usd_current", "market_cap_updated_at",
            "market_cap_ath", "market_cap_ath_timestamp", "market_cap_usd_previous"
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

    Returns:
        token_id: Database ID of the saved token
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert or update analyzed token
        cursor.execute(
            """
            INSERT INTO analyzed_tokens (
                token_address, token_name, token_symbol, acronym,
                first_buy_timestamp, wallets_found, axiom_json, credits_used, last_analysis_credits,
                market_cap_usd, market_cap_usd_current, market_cap_ath, market_cap_ath_timestamp, market_cap_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                market_cap_usd = excluded.market_cap_usd
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
            first_buy_usd = round(total_usd)
            transaction_count = bidder.get("transaction_count", 1)
            average_buy_usd = bidder.get("average_buy_usd", total_usd)
            wallet_balance_usd = bidder.get("wallet_balance_usd")
            axiom_name = f"({index}/{max_wallets})${first_buy_usd}|{acronym}"

            cursor.execute(
                """
                INSERT OR IGNORE INTO early_buyer_wallets (
                    token_id, analysis_run_id, wallet_address, position, first_buy_usd,
                    total_usd, transaction_count, average_buy_usd,
                    first_buy_timestamp, axiom_name, wallet_balance_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    token_id,
                    analysis_run_id,
                    bidder["wallet_address"],
                    index,
                    first_buy_usd,
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
            SET wallet_balance_usd = ?
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


# Initialize database on module import
init_database()
