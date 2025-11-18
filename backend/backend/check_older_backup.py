import sqlite3

# Check the older backup
print("=" * 80)
print("CHECKING OLDER BACKUP: analyzed_tokens_backup_20251110_072955.db")
print("=" * 80)

conn = sqlite3.connect("analyzed_tokens_backup_20251110_072955.db")
cursor = conn.cursor()

# Check total wallets
cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
total = cursor.fetchone()[0]
print(f"\nTotal wallets in OLDER BACKUP: {total}")

# Check distinct tokens
cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
tokens = cursor.fetchone()[0]
print(f"Distinct tokens in OLDER BACKUP: {tokens}")

# Check for multi-token wallets
cursor.execute(
    """
    SELECT wallet_address, COUNT(DISTINCT token_id) as cnt
    FROM early_buyer_wallets
    GROUP BY wallet_address
    HAVING cnt >= 2
    LIMIT 10
"""
)
multi = cursor.fetchall()
print(f"\nMulti-token wallets in OLDER BACKUP: {len(multi)}")
for row in multi[:5]:
    print(f"  {row[0][:12]}... appears in {row[1]} tokens")

# Check analyzed_tokens count
cursor.execute("SELECT COUNT(*) FROM analyzed_tokens WHERE is_deleted = 0 OR is_deleted IS NULL")
token_count = cursor.fetchone()[0]
print(f"\nActive tokens in analyzed_tokens table: {token_count}")

# Check if this backup has the schema with analysis_run_id
cursor.execute("PRAGMA table_info(early_buyer_wallets)")
columns = cursor.fetchall()
has_analysis_run_id = any(col[1] == "analysis_run_id" for col in columns)
print(f"Has analysis_run_id column: {has_analysis_run_id}")

conn.close()

print("\n" + "=" * 80)
print("CURRENT DATABASE: analyzed_tokens.db")
print("=" * 80)

conn = sqlite3.connect("analyzed_tokens.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
total_current = cursor.fetchone()[0]
print(f"\nTotal wallets in CURRENT: {total_current}")

cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
tokens_current = cursor.fetchone()[0]
print(f"Distinct tokens in CURRENT: {tokens_current}")

cursor.execute("SELECT COUNT(*) FROM analyzed_tokens WHERE is_deleted = 0 OR is_deleted IS NULL")
token_count_current = cursor.fetchone()[0]
print(f"Active tokens in analyzed_tokens table: {token_count_current}")

conn.close()
