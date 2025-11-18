import sqlite3

print("=" * 80)
print("INVESTIGATING DATA LOSS CAUSE")
print("=" * 80)

# Check what happened with the backup before restore
print("\n[1] Checking 'before restore' backup (the corrupted one):")
conn = sqlite3.connect("analyzed_tokens_backup_before_restore.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
print(f"   Wallet records: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
print(f"   Distinct tokens: {cursor.fetchone()[0]}")

# Check if there was a problem with token_id references
cursor.execute(
    """
    SELECT token_id, COUNT(*) as cnt
    FROM early_buyer_wallets
    GROUP BY token_id
    ORDER BY cnt DESC
"""
)
print(f"   Token distribution:")
for row in cursor.fetchall():
    print(f"      Token ID {row[0]}: {row[1]} wallets")

# Check analyzed_tokens table
cursor.execute("SELECT COUNT(*) FROM analyzed_tokens")
total_tokens = cursor.fetchone()[0]
print(f"   Total tokens in analyzed_tokens: {total_tokens}")

conn.close()

print("\n[2] Checking current (restored) database:")
conn = sqlite3.connect("analyzed_tokens.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM early_buyer_wallets")
print(f"   Wallet records: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(DISTINCT token_id) FROM early_buyer_wallets")
print(f"   Distinct tokens: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM analyzed_tokens")
print(f"   Total tokens in analyzed_tokens: {cursor.fetchone()[0]}")

# Check if any new tokens were added after backup
cursor.execute(
    """
    SELECT id, token_name, token_symbol, created_at
    FROM analyzed_tokens
    ORDER BY created_at DESC
    LIMIT 5
"""
)
print(f"\n   Most recent tokens:")
for row in cursor.fetchall():
    print(f"      ID {row[0]}: {row[1]} ({row[2]}) - {row[3]}")

conn.close()

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print("The database was restored successfully from the backup.")
print("If any tokens were analyzed AFTER the backup time (07:29:55),")
print("those will need to be re-analyzed.")
