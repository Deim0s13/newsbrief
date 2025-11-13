#!/usr/bin/env python3
"""
Identify and close obsolete issues that don't align with story-based architecture.
"""
import json
import subprocess
import sys
from pathlib import Path

OLD_ISSUES_FILE = Path(__file__).parent.parent / "data" / "issues.json"

# Issues to close - wrong direction or superseded
OBSOLETE_TITLES = [
    "Skim vs Detail view toggle",  # Wrong interpretation - was article-level, not story-level
    "Cluster duplicate articles",  # Superseded by story clustering
    "Background re-cluster job",  # Superseded by story generation
]

# Keep these - still relevant
KEEP_TITLES = [
    "Implement feed ingestion with RSS/Atom",  # Still needed
    "Add ETag/Last-Modified caching",  # Still needed
    "Global fetch cap per refresh",  # Still needed
    "Robots.txt compliance",  # Still needed
    "Structured JSON summaries with Ollama",  # Still needed
    "Long article map-reduce summarization",  # Still needed
    "Fallback summary display",  # Still needed
    "Implement ranking score",  # May be superseded by story importance
    "Topic routing (keywords + LLM fallback)",  # Still needed for article classification
    "Keyboard shortcuts",  # Nice to have, not priority
    "Dark mode toggle",  # Nice to have, not priority
    "Feed Manager page",  # Still needed
    "Store embeddings with Ollama",  # Future phase
    "Hybrid search (FTS + vectors)",  # Future phase
    "Grounded Q&A endpoint",  # Future phase
    "Health endpoints",  # Still needed
    "Structured logging",  # Still needed
    "Contract tests for summary JSON",  # Still needed
    "Basic ranking tests",  # May need update
]


def run_gh(args: list) -> tuple[bool, str]:
    """Run gh CLI command."""
    try:
        result = subprocess.run(
            ["gh"] + args, capture_output=True, text=True, check=False
        )
        return result.returncode == 0, result.stdout.strip()
    except FileNotFoundError:
        print("❌ GitHub CLI (gh) not found")
        sys.exit(1)


def get_all_issues():
    """Get all issues from GitHub."""
    success, output = run_gh(
        [
            "issue",
            "list",
            "--state",
            "all",
            "--json",
            "number,title,state",
            "--limit",
            "200",
        ]
    )

    if not success:
        print(f"❌ Failed to fetch issues: {output}")
        return []

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print(f"❌ Failed to parse issues JSON")
        return []


def close_issue(number: int, reason: str):
    """Close an issue with a comment."""
    # Add closing comment
    comment = f"Closing: {reason}\n\nSuperseded by story-based architecture. See docs/STORY_ARCHITECTURE_BACKLOG.md for new approach."

    success, _ = run_gh(["issue", "comment", str(number), "--body", comment])

    if not success:
        print(f"  ⚠️  Failed to add comment to #{number}")

    # Close issue
    success, _ = run_gh(["issue", "close", str(number)])

    if success:
        print(f"  ✅ Closed issue #{number}")
        return True
    else:
        print(f"  ❌ Failed to close issue #{number}")
        return False


def main():
    print("🧹 Cleaning up obsolete issues\n")

    # Check auth
    print("🔐 Checking GitHub CLI authentication...")
    success, output = run_gh(["auth", "status"])
    if not success:
        print("❌ GitHub CLI not authenticated")
        print("Please run: gh auth login")
        sys.exit(1)
    print("✅ Authenticated\n")

    # Get all issues
    print("📋 Fetching existing issues...")
    issues = get_all_issues()
    print(f"Found {len(issues)} total issues\n")

    if not issues:
        print("No issues found or error fetching")
        return

    # Identify obsolete issues
    print("🔍 Identifying obsolete issues...")
    to_close = []
    to_keep = []

    for issue in issues:
        if issue["state"] == "closed":
            continue

        title = issue["title"]
        number = issue["number"]

        if any(obs in title for obs in OBSOLETE_TITLES):
            to_close.append(
                (number, title, "Wrong direction - article-centric feature")
            )
        elif "Skim" in title and "Detail" in title:
            to_close.append(
                (
                    number,
                    title,
                    "Misunderstood requirement - was for articles, not stories",
                )
            )
        else:
            to_keep.append((number, title))

    if not to_close:
        print("✅ No obsolete issues found!\n")
        print("📋 Existing open issues:")
        for number, title in to_keep[:20]:
            print(f"  #{number}: {title}")
        return

    # Show what will be closed
    print(f"\n🗑️  Issues to close ({len(to_close)}):")
    for number, title, reason in to_close:
        print(f"  #{number}: {title}")
        print(f"         Reason: {reason}")

    print(f"\n✅ Issues to keep ({len(to_keep)}):")
    for number, title in to_keep[:10]:
        print(f"  #{number}: {title}")

    # Confirm
    print("\n" + "=" * 70)
    response = input("Close these obsolete issues? (yes/no): ").strip().lower()

    if response not in ("yes", "y"):
        print("❌ Cancelled. No issues closed.")
        return

    # Close issues
    print("\n🗑️  Closing obsolete issues...")
    closed_count = 0

    for number, title, reason in to_close:
        print(f"\nClosing #{number}: {title[:60]}...")
        if close_issue(number, reason):
            closed_count += 1

    print("\n" + "=" * 70)
    print(f"✅ Closed {closed_count} obsolete issues")
    print("=" * 70)
    print("\n🎯 Next: Run scripts/import_story_issues_simple.py to add new issues")


if __name__ == "__main__":
    main()
