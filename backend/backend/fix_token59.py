import analyzed_tokens_db as db

# Fix token 59 - restore correct metadata from successful analysis run #37
with db.get_db_connection() as conn:
    cursor = conn.cursor()

    # Update the token metadata to match the successful analysis
    cursor.execute(
        """
        UPDATE analyzed_tokens
        SET token_name = ?,
            token_symbol = ?,
            acronym = ?,
            wallets_found = ?,
            analysis_file_path = ?,
            axiom_file_path = ?
        WHERE id = 59
    """,
        (
            "Incognito",
            "INCOG",
            "INCOG",
            10,
            r"C:\Users\simon\OneDrive\Desktop\solscan_hotkey\backend\analysis_results\59_incognito.json",
            r"C:\Users\simon\OneDrive\Desktop\solscan_hotkey\backend\axiom_exports\59_incog.json",
        ),
    )

    conn.commit()

print("[OK] Fixed token 59: Restored as Incognito/INCOG with 10 wallets")
