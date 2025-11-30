"""
Centralized API Credit Tracking Module
======================================
Provides atomic tracking, persistence, and reporting for all Helius API credit usage.

Features:
- Atomic credit recording with operation context
- Persistent storage in SQLite for historical analysis
- Daily/hourly aggregation and budgeting
- Operation-level cost constants for transparency
- Thread-safe singleton pattern

Usage:
    from meridinate.credit_tracker import credit_tracker, CreditOperation

    # Record a credit usage
    credit_tracker.record(CreditOperation.WALLET_BALANCE, credits=1, context={"wallet": "..."})

    # Get today's usage
    today_credits = credit_tracker.get_daily_usage()

    # Get usage by operation type
    breakdown = credit_tracker.get_usage_by_operation()
"""

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from meridinate import settings


class CreditOperation(str, Enum):
    """
    Enumeration of all Helius API operations and their credit costs.

    Keeping costs as enum values enables:
    - Type-safe operation references
    - Centralized cost updates
    - Easy auditing of credit-consuming operations
    """

    # Standard RPC calls (1 credit each)
    WALLET_BALANCE = "wallet_balance"  # getBalance
    TOKEN_METADATA = "token_metadata"  # getAsset (DAS API)
    ACCOUNT_OWNER = "account_owner"  # getAccountInfo
    TOKEN_LARGEST_ACCOUNTS = "token_largest_accounts"  # getTokenLargestAccounts
    GET_TRANSACTION = "get_transaction"  # getTransaction (per tx)
    SIGNATURES_FOR_ADDRESS = "signatures_for_address"  # getSignaturesForAddress
    TOKEN_ACCOUNTS = "token_accounts"  # getTokenAccountsByOwner

    # Enhanced API calls (higher cost)
    TRANSACTIONS_FOR_ADDRESS = "transactions_for_address"  # 100 credits per call

    # Composite operations (for reporting, actual credits are sum of components)
    TOKEN_ANALYSIS = "token_analysis"  # Full token analysis
    TOP_HOLDERS_FETCH = "top_holders_fetch"  # Top holders lookup
    MARKET_CAP_REFRESH = "market_cap_refresh"  # Market cap update
    WALLET_REFRESH = "wallet_refresh"  # Wallet balance refresh
    POSITION_CHECK = "position_check"  # MTEW position check


# Credit costs per operation (used for estimation, actual cost comes from API)
CREDIT_COSTS: Dict[CreditOperation, int] = {
    CreditOperation.WALLET_BALANCE: 1,
    CreditOperation.TOKEN_METADATA: 1,
    CreditOperation.ACCOUNT_OWNER: 1,
    CreditOperation.TOKEN_LARGEST_ACCOUNTS: 1,
    CreditOperation.GET_TRANSACTION: 1,
    CreditOperation.SIGNATURES_FOR_ADDRESS: 1,
    CreditOperation.TOKEN_ACCOUNTS: 10,
    CreditOperation.TRANSACTIONS_FOR_ADDRESS: 100,
    CreditOperation.POSITION_CHECK: 10,
}


@dataclass
class CreditTransaction:
    """Represents a single credit usage event."""

    id: Optional[int]
    operation: str
    credits: int
    timestamp: datetime
    token_id: Optional[int]
    wallet_address: Optional[str]
    context: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "operation": self.operation,
            "credits": self.credits,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "token_id": self.token_id,
            "wallet_address": self.wallet_address,
            "context": self.context,
        }


@dataclass
class CreditUsageStats:
    """Aggregated credit usage statistics."""

    total_credits: int
    period_start: datetime
    period_end: datetime
    by_operation: Dict[str, int]
    transaction_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_credits": self.total_credits,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "by_operation": self.by_operation,
            "transaction_count": self.transaction_count,
        }


@dataclass
class OperationLogEntry:
    """Represents a high-level operation log entry."""

    id: Optional[int]
    operation: str
    label: str
    credits: int
    call_count: int
    timestamp: datetime
    context: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "operation": self.operation,
            "label": self.label,
            "credits": self.credits,
            "call_count": self.call_count,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "context": self.context,
        }


class CreditTracker:
    """
    Centralized credit tracking with persistent storage.

    Thread-safe singleton that records all API credit usage
    to SQLite for historical analysis and budgeting.
    """

    _instance: Optional["CreditTracker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CreditTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._db_path = settings.DATABASE_FILE
        self._session_credits = 0
        self._init_schema()
        self._initialized = True

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize credit tracking tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Credit transactions table - stores every credit usage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credit_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    credits INTEGER NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    token_id INTEGER,
                    wallet_address TEXT,
                    context_json TEXT,
                    FOREIGN KEY (token_id) REFERENCES analyzed_tokens(id) ON DELETE SET NULL
                )
            """)

            # Indices for efficient querying
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_credit_tx_timestamp
                ON credit_transactions(timestamp DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_credit_tx_operation
                ON credit_transactions(operation)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_credit_tx_token
                ON credit_transactions(token_id)
            """)

            # Daily aggregates table - precomputed for fast queries
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credit_daily_aggregates (
                    date TEXT PRIMARY KEY,
                    total_credits INTEGER DEFAULT 0,
                    by_operation_json TEXT,
                    transaction_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Operation log table - persisted high-level operations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    label TEXT NOT NULL,
                    credits INTEGER NOT NULL DEFAULT 0,
                    call_count INTEGER NOT NULL DEFAULT 1,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context_json TEXT
                )
            """)

            # Index for efficient recent operations lookup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_operation_log_timestamp
                ON operation_log(timestamp DESC)
            """)

            print("[CreditTracker] Schema initialized")

    def record(
        self,
        operation: CreditOperation,
        credits: int = 1,
        token_id: Optional[int] = None,
        wallet_address: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Record a credit usage event.

        Args:
            operation: The type of API operation
            credits: Number of credits consumed (default: 1)
            token_id: Associated token ID (if applicable)
            wallet_address: Associated wallet address (if applicable)
            context: Additional context data (stored as JSON)

        Returns:
            The transaction ID
        """
        import json

        with self._get_connection() as conn:
            cursor = conn.cursor()

            context_json = json.dumps(context) if context else None

            cursor.execute("""
                INSERT INTO credit_transactions
                    (operation, credits, token_id, wallet_address, context_json)
                VALUES (?, ?, ?, ?, ?)
            """, (operation.value, credits, token_id, wallet_address, context_json))

            tx_id = cursor.lastrowid

            # Update session counter
            self._session_credits += credits

            # Update daily aggregate
            self._update_daily_aggregate(cursor, operation.value, credits)

            return tx_id

    def record_batch(
        self,
        operation: CreditOperation,
        credits: int,
        count: int,
        token_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Record a batch of identical credit operations efficiently.

        Args:
            operation: The type of API operation
            credits: Total credits consumed
            count: Number of operations in the batch
            token_id: Associated token ID (if applicable)
            context: Additional context data

        Returns:
            The transaction ID
        """
        batch_context = context or {}
        batch_context["batch_count"] = count
        return self.record(operation, credits, token_id, context=batch_context)

    def _update_daily_aggregate(self, cursor: sqlite3.Cursor, operation: str, credits: int):
        """Update the daily aggregate table incrementally."""
        import json

        today = datetime.now().strftime("%Y-%m-%d")

        # Get existing aggregate
        cursor.execute("""
            SELECT total_credits, by_operation_json, transaction_count
            FROM credit_daily_aggregates
            WHERE date = ?
        """, (today,))

        row = cursor.fetchone()

        if row:
            total = row["total_credits"] + credits
            count = row["transaction_count"] + 1
            by_op = json.loads(row["by_operation_json"] or "{}")
            by_op[operation] = by_op.get(operation, 0) + credits

            cursor.execute("""
                UPDATE credit_daily_aggregates
                SET total_credits = ?, by_operation_json = ?, transaction_count = ?, updated_at = CURRENT_TIMESTAMP
                WHERE date = ?
            """, (total, json.dumps(by_op), count, today))
        else:
            by_op = {operation: credits}
            cursor.execute("""
                INSERT INTO credit_daily_aggregates (date, total_credits, by_operation_json, transaction_count)
                VALUES (?, ?, ?, 1)
            """, (today, credits, json.dumps(by_op)))

    def get_session_credits(self) -> int:
        """Get credits used in the current session."""
        return self._session_credits

    def get_daily_usage(self, date: Optional[datetime] = None) -> CreditUsageStats:
        """
        Get credit usage for a specific day.

        Args:
            date: The date to query (default: today)

        Returns:
            CreditUsageStats for the day
        """
        import json

        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y-%m-%d")
        period_start = datetime.strptime(date_str, "%Y-%m-%d")
        period_end = period_start + timedelta(days=1)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT total_credits, by_operation_json, transaction_count
                FROM credit_daily_aggregates
                WHERE date = ?
            """, (date_str,))

            row = cursor.fetchone()

            if row:
                return CreditUsageStats(
                    total_credits=row["total_credits"],
                    period_start=period_start,
                    period_end=period_end,
                    by_operation=json.loads(row["by_operation_json"] or "{}"),
                    transaction_count=row["transaction_count"],
                )
            else:
                return CreditUsageStats(
                    total_credits=0,
                    period_start=period_start,
                    period_end=period_end,
                    by_operation={},
                    transaction_count=0,
                )

    def get_usage_range(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> CreditUsageStats:
        """
        Get credit usage for a date range.

        Args:
            start_date: Start of the range
            end_date: End of the range (default: now)

        Returns:
            Aggregated CreditUsageStats for the range
        """
        import json

        if end_date is None:
            end_date = datetime.now()

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COALESCE(SUM(total_credits), 0) as total,
                    COALESCE(SUM(transaction_count), 0) as count
                FROM credit_daily_aggregates
                WHERE date >= ? AND date <= ?
            """, (start_str, end_str))

            totals = cursor.fetchone()

            # Get operation breakdown
            cursor.execute("""
                SELECT by_operation_json
                FROM credit_daily_aggregates
                WHERE date >= ? AND date <= ?
            """, (start_str, end_str))

            combined_ops: Dict[str, int] = {}
            for row in cursor.fetchall():
                if row["by_operation_json"]:
                    ops = json.loads(row["by_operation_json"])
                    for op, credits in ops.items():
                        combined_ops[op] = combined_ops.get(op, 0) + credits

            return CreditUsageStats(
                total_credits=totals["total"],
                period_start=start_date,
                period_end=end_date,
                by_operation=combined_ops,
                transaction_count=totals["count"],
            )

    def get_recent_transactions(
        self,
        limit: int = 100,
        operation: Optional[CreditOperation] = None,
        token_id: Optional[int] = None,
    ) -> List[CreditTransaction]:
        """
        Get recent credit transactions.

        Args:
            limit: Maximum number of transactions to return
            operation: Filter by operation type
            token_id: Filter by token ID

        Returns:
            List of CreditTransaction objects
        """
        import json

        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM credit_transactions WHERE 1=1"
            params: List[Any] = []

            if operation:
                query += " AND operation = ?"
                params.append(operation.value)

            if token_id:
                query += " AND token_id = ?"
                params.append(token_id)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)

            transactions = []
            for row in cursor.fetchall():
                context = json.loads(row["context_json"]) if row["context_json"] else None
                transactions.append(CreditTransaction(
                    id=row["id"],
                    operation=row["operation"],
                    credits=row["credits"],
                    timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
                    token_id=row["token_id"],
                    wallet_address=row["wallet_address"],
                    context=context,
                ))

            return transactions

    def get_token_credits(self, token_id: int) -> int:
        """Get total credits used for a specific token."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(credits), 0) as total
                FROM credit_transactions
                WHERE token_id = ?
            """, (token_id,))
            return cursor.fetchone()["total"]

    def estimate_operation_cost(self, operation: CreditOperation, count: int = 1) -> int:
        """
        Estimate the credit cost for an operation.

        Args:
            operation: The operation type
            count: Number of operations

        Returns:
            Estimated credits
        """
        base_cost = CREDIT_COSTS.get(operation, 1)
        return base_cost * count

    def record_operation(
        self,
        operation: str,
        label: str,
        credits: int = 0,
        call_count: int = 1,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Record a high-level operation to the persistent operation log.

        This creates a permanent record of user-facing operations like
        "Token Analysis", "Position Check", "Tier-1 Enrichment", etc.

        Args:
            operation: Operation type identifier (e.g., 'token_analysis', 'position_check')
            label: Human-readable label (e.g., 'Token Analysis', 'Position Check')
            credits: Total credits consumed by this operation
            call_count: Number of API calls made during this operation
            context: Additional context data (stored as JSON)

        Returns:
            The operation log entry ID
        """
        import json

        with self._get_connection() as conn:
            cursor = conn.cursor()

            context_json = json.dumps(context) if context else None

            cursor.execute("""
                INSERT INTO operation_log (operation, label, credits, call_count, context_json)
                VALUES (?, ?, ?, ?, ?)
            """, (operation, label, credits, call_count, context_json))

            entry_id = cursor.lastrowid

            # Prune old entries to keep only the latest 100
            cursor.execute("""
                DELETE FROM operation_log
                WHERE id NOT IN (
                    SELECT id FROM operation_log ORDER BY timestamp DESC LIMIT 100
                )
            """)

            return entry_id

    def get_recent_operations(self, limit: int = 30) -> List[OperationLogEntry]:
        """
        Get recent high-level operations from the persistent log.

        Args:
            limit: Maximum number of operations to return (default: 30)

        Returns:
            List of OperationLogEntry objects ordered by timestamp descending
        """
        import json

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, operation, label, credits, call_count, timestamp, context_json
                FROM operation_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

            entries = []
            for row in cursor.fetchall():
                context = json.loads(row["context_json"]) if row["context_json"] else None
                entries.append(OperationLogEntry(
                    id=row["id"],
                    operation=row["operation"],
                    label=row["label"],
                    credits=row["credits"],
                    call_count=row["call_count"],
                    timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
                    context=context,
                ))

            return entries


# Lazy singleton - initialized on first access to avoid database lock during imports
_credit_tracker_instance = None


def get_credit_tracker() -> CreditTracker:
    """Get the global credit tracker instance (lazy initialization)."""
    global _credit_tracker_instance
    if _credit_tracker_instance is None:
        _credit_tracker_instance = CreditTracker()
    return _credit_tracker_instance


# Module-level __getattr__ for lazy initialization of credit_tracker
# This allows `from credit_tracker import credit_tracker` to work
# while still deferring database initialization until first use
def __getattr__(name: str):
    if name == "credit_tracker":
        return get_credit_tracker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
