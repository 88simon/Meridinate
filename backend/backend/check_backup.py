import sqlite3

# Check the most recent backup
print("=" * 80)
print("CHECKING BACKUP: analyzed_tokens_backup_20251110_073039.db")
print("=" * 80)

conn = sqlite3.connect("analyzed_tokens_backup_20251110_073039.db")
cursor = conn.cursor()

# Check total wallets
cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
total = cursor.fetchone()[0]
print(f"\nTotal wallets in BACKUP: {total}")

# Check distinct tokens
cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
tokens = cursor.fetchone()[0]
print(f"Distinct tokens in BACKUP: {tokens}")

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
print(f"\nMulti-token wallets in BACKUP: {len(multi)}")
for row in multi[:5]:
    print(f"  {row[0][:12]}... appears in {row[1]} tokens")

# Check analyzed_tokens count
cursor.execute("SELECT COUNT(*) FROM analyzed_tokens")
token_count = cursor.fetchone()[0]
print(f"\nTotal tokens in analyzed_tokens table: {token_count}")

conn.close()

print("\n" + "=" * 80)
print("COMPARING TO CURRENT DATABASE: analyzed_tokens.db")
print("=" * 80)

conn = sqlite3.connect("analyzed_tokens.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
total_current = cursor.fetchone()[0]
print(f"\nTotal wallets in CURRENT: {total_current}")

cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
tokens_current = cursor.fetchone()[0]
print(f"Distinct tokens in CURRENT: {tokens_current}")

cursor.execute("SELECT COUNT(*) FROM analyzed_tokens")
token_count_current = cursor.fetchone()[0]
print(f"Total tokens in analyzed_tokens table: {token_count_current}")

print(f"\n🚨 DATA LOSS SUMMARY:")
print(f"   Wallet records lost: {total - total_current}")
print(f"   Token coverage lost: {tokens - tokens_current} tokens")

conn.close()
