#!/usr/bin/env python3
"""
Migration script to rename existing analysis and axiom files to new ID-based naming convention.

This script:
1. Reads all tokens from the database
2. For each token, finds its corresponding files (analysis_results and axiom_exports)
3. Renames files to the new format: {id}_{sanitized-name}.json
4. Updates database with new file paths
5. Creates trash directories if they don't exist
"""

import os
import shutil
import sqlite3
from typing import Optional

from analyzed_tokens_db import (
    ANALYSIS_RESULTS_DIR,
    AXIOM_EXPORTS_DIR,
    get_analysis_file_path,
    get_axiom_file_path,
    get_db_connection,
    sanitize_filename,
)


def find_analysis_file(token_name: str) -> Optional[str]:
    """
    Find the analysis results file for a token by name.
    Returns the full path if found, None otherwise.
    """
    # Try the sanitized version used in current code
    safe_name = token_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ("_", "-"))
    filename = f"{safe_name}.json"
    filepath = os.path.join(ANALYSIS_RESULTS_DIR, filename)

    if os.path.exists(filepath):
        return filepath

    # Try variations
    for file in os.listdir(ANALYSIS_RESULTS_DIR):
        if file.endswith(".json") and not file.startswith("trash"):
            # Simple case-insensitive match
            if file.lower() == filename.lower():
                return os.path.join(ANALYSIS_RESULTS_DIR, file)

    return None


def find_axiom_file(acronym: str) -> Optional[str]:
    """
    Find the most recent axiom export file for a token by acronym.
    Returns the full path if found, None otherwise.
    """
    # Look for files matching the acronym pattern
    matching_files = []
    for file in os.listdir(AXIOM_EXPORTS_DIR):
        if file.startswith(f"{acronym}_") and file.endswith(".json"):
            filepath = os.path.join(AXIOM_EXPORTS_DIR, file)
            matching_files.append(filepath)

    if not matching_files:
        return None

    # Return the most recently modified file
    matching_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return matching_files[0]


def migrate_token_files(token_id: int, token_name: str, acronym: str):
    """
    Migrate files for a single token.

    Args:
        token_id: Database ID of the token
        token_name: Name of the token
        acronym: Token acronym

    Returns:
        Tuple of (analysis_migrated, axiom_migrated)
    """
    analysis_migrated = False
    axiom_migrated = False

    # Get new file paths
    new_analysis_path = get_analysis_file_path(token_id, token_name, in_trash=False)
    new_axiom_path = get_axiom_file_path(token_id, acronym, in_trash=False)

    # Migrate analysis file
    old_analysis_file = find_analysis_file(token_name)
    if old_analysis_file and os.path.exists(old_analysis_file):
        try:
            # Only rename if it's different from the new path
            if os.path.abspath(old_analysis_file) != os.path.abspath(new_analysis_path):
                shutil.move(old_analysis_file, new_analysis_path)
                print(
                    f"  [OK] Renamed analysis file: {os.path.basename(old_analysis_file)} -> {os.path.basename(new_analysis_path)}"
                )
            else:
                print(f"  = Analysis file already has correct name: {os.path.basename(new_analysis_path)}")
            analysis_migrated = True
        except Exception as e:
            print(f"  [WARN] Failed to rename analysis file: {e}")
    else:
        print(f"  - No analysis file found for '{token_name}'")

    # Migrate axiom file
    old_axiom_file = find_axiom_file(acronym)
    if old_axiom_file and os.path.exists(old_axiom_file):
        try:
            # Only rename if it's different from the new path
            if os.path.abspath(old_axiom_file) != os.path.abspath(new_axiom_path):
                shutil.move(old_axiom_file, new_axiom_path)
                print(
                    f"  [OK] Renamed axiom file: {os.path.basename(old_axiom_file)} -> {os.path.basename(new_axiom_path)}"
                )
            else:
                print(f"  = Axiom file already has correct name: {os.path.basename(new_axiom_path)}")
            axiom_migrated = True
        except Exception as e:
            print(f"  [WARN] Failed to rename axiom file: {e}")
    else:
        print(f"  - No axiom file found for acronym '{acronym}'")

    return (analysis_migrated, axiom_migrated)


def main():
    """Main migration function"""
    print("=" * 70)
    print("File Migration Script - ID-Based Naming Convention")
    print("=" * 70)

    # Create trash directories
    os.makedirs(os.path.join(ANALYSIS_RESULTS_DIR, "trash"), exist_ok=True)
    os.makedirs(os.path.join(AXIOM_EXPORTS_DIR, "trash"), exist_ok=True)
    print("\n[OK] Ensured trash directories exist")

    # Get all non-deleted tokens from database
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, token_name, acronym, analysis_file_path, axiom_file_path
            FROM analyzed_tokens
            WHERE is_deleted = 0
            ORDER BY id
        """
        )
        tokens = cursor.fetchall()

        if not tokens:
            print("\n[ERROR] No tokens found in database")
            return

        print(f"\nFound {len(tokens)} tokens to migrate\n")

        migrated_analysis = 0
        migrated_axiom = 0

        for token in tokens:
            token_id = token[0]
            token_name = token[1]
            acronym = token[2]
            existing_analysis_path = token[3]
            existing_axiom_path = token[4]

            print(f"\n[{token_id}] {token_name} ({acronym})")

            # Skip if already migrated (has file paths in database)
            if existing_analysis_path and existing_axiom_path:
                if os.path.exists(existing_analysis_path) and os.path.exists(existing_axiom_path):
                    print(f"  [SKIP] Already migrated (file paths exist in database)")
                    continue

            # Migrate files
            analysis_ok, axiom_ok = migrate_token_files(token_id, token_name, acronym)

            if analysis_ok:
                migrated_analysis += 1
            if axiom_ok:
                migrated_axiom += 1

            # Update database with new file paths
            if analysis_ok or axiom_ok:
                new_analysis_path = get_analysis_file_path(token_id, token_name, in_trash=False)
                new_axiom_path = get_axiom_file_path(token_id, acronym, in_trash=False)

                cursor.execute(
                    """
                    UPDATE analyzed_tokens
                    SET analysis_file_path = ?, axiom_file_path = ?
                    WHERE id = ?
                """,
                    (new_analysis_path, new_axiom_path, token_id),
                )
                conn.commit()
                print(f"  [OK] Updated database with file paths")

        print("\n" + "=" * 70)
        print("Migration Complete!")
        print("=" * 70)
        print(f"Analysis files migrated: {migrated_analysis}/{len(tokens)}")
        print(f"Axiom files migrated:    {migrated_axiom}/{len(tokens)}")
        print("=" * 70)


if __name__ == "__main__":
    main()
