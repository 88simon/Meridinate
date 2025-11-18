import sqlite3

conn = sqlite3.connect("analyzed_tokens.db")
cursor = conn.cursor()

# Check total wallets
cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
total = cursor.fetchone()[0]
print(f"Total wallets in DB: {total}")

# Check distinct tokens
cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
tokens = cursor.fetchone()[0]
print(f"Distinct tokens: {tokens}")

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
print(f"\nMulti-token wallets found: {len(multi)}")
for row in multi:
    print(f"  {row[0][:12]}... appears in {row[1]} tokens")

# Check if is_deleted column exists and its values
cursor.execute("SELECT COUNT(*) FROM analyzed_tokens WHERE is_deleted = 0 OR is_deleted IS NULL")
active_tokens = cursor.fetchone()[0]
print(f"\nActive (non-deleted) tokens: {active_tokens}")

conn.close()
