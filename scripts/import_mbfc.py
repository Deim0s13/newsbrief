#!/usr/bin/env python3
"""
Import MBFC source credibility data.

CLI script to manually import/refresh credibility data from the MBFC
community dataset. Primarily for testing and debugging - the app will
auto-import on startup and refresh weekly via scheduler.

Usage:
    python scripts/import_mbfc.py [--force]

Options:
    --force     Import even if data already exists (updates all records)

Part of Issue #271: Import and auto-refresh MBFC source credibility data
"""

import argparse
import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Must set DATABASE_URL before importing app modules
if not os.environ.get("DATABASE_URL"):
    print("Error: DATABASE_URL environment variable required")
    print("Example: DATABASE_URL=postgresql://user:pass@localhost:5432/newsbrief")
    sys.exit(1)

from app.credibility_import import (
    get_credibility_count,
    import_mbfc_sources,
    is_credibility_data_empty,
)


def main():
    parser = argparse.ArgumentParser(
        description="Import MBFC source credibility data"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Import even if data already exists",
    )
    args = parser.parse_args()

    # Check current state
    count = get_credibility_count()
    print(f"Current credibility records: {count}")

    if count > 0 and not args.force:
        print(
            "\nData already exists. Use --force to refresh all records."
        )
        print("Or use the API: POST /api/credibility/refresh")
        return

    if count > 0:
        print("\n--force specified, will update existing records...")

    # Run import
    print("\nFetching MBFC data...")
    stats = import_mbfc_sources()

    # Print results
    print("\n" + "=" * 50)
    print("Import Complete")
    print("=" * 50)
    print(f"Total records:  {stats.total_records}")
    print(f"Inserted:       {stats.inserted}")
    print(f"Updated:        {stats.updated}")
    print(f"Skipped:        {stats.skipped}")
    print(f"Failed:         {stats.failed}")
    print(f"Duration:       {stats.duration_ms}ms")
    print(f"Dataset version: {stats.dataset_version}")

    if stats.errors:
        print(f"\nErrors ({len(stats.errors)}):")
        for error in stats.errors[:5]:
            print(f"  - {error}")
        if len(stats.errors) > 5:
            print(f"  ... and {len(stats.errors) - 5} more")

    # Final count
    final_count = get_credibility_count()
    print(f"\nFinal record count: {final_count}")


if __name__ == "__main__":
    main()
