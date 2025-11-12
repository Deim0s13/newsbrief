#!/usr/bin/env python3
"""
Bulk import story architecture issues using GitHub CLI (gh).
Simpler alternative that doesn't require token management.
"""
import json
import subprocess
import sys
from pathlib import Path

# Configuration
ISSUES_FILE = Path(__file__).parent.parent / "data" / "story-architecture-issues.json"


def run_gh(args: list) -> tuple[bool, str]:
    """Run gh CLI command and return success status and output."""
    try:
        result = subprocess.run(
            ["gh"] + args, capture_output=True, text=True, check=False
        )
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        print("❌ GitHub CLI (gh) not found. Install from: https://cli.github.com/")
        sys.exit(1)


def check_auth() -> bool:
    """Check if gh is authenticated."""
    success, output = run_gh(["auth", "status"])
    return success


def create_label(name: str, color: str, description: str) -> bool:
    """Create a label using gh CLI."""
    # Check if exists
    success, output = run_gh(["label", "list", "--json", "name"])
    if success and f'"{name}"' in output:
        print(f"  ℹ️  Label '{name}' already exists")
        return True

    # Create label
    success, output = run_gh(
        ["label", "create", name, "--color", color, "--description", description]
    )

    if success:
        print(f"  ✅ Created label '{name}'")
        return True
    else:
        print(f"  ⚠️  Failed to create label '{name}'")
        return False


def create_issue(title: str, body: str, labels: list) -> bool:
    """Create an issue using gh CLI."""
    args = ["issue", "create", "--title", title, "--body", body]

    if labels:
        for label in labels:
            args.extend(["--label", label])

    success, output = run_gh(args)

    if success:
        # Extract issue number from output
        issue_num = output.strip().split("/")[-1] if "/" in output else "?"
        print(f"  ✅ Created issue #{issue_num}: {title[:60]}...")
        return True
    else:
        print(f"  ❌ Failed to create issue '{title[:60]}...'")
        print(f"     {output[:100]}")
        return False


def main():
    print("🚀 Importing story architecture issues to GitHub\n")

    # Check authentication
    print("🔐 Checking GitHub CLI authentication...")
    if not check_auth():
        print("❌ GitHub CLI not authenticated")
        print("Please run: gh auth login")
        sys.exit(1)
    print("✅ Authenticated\n")

    # Load issues
    if not ISSUES_FILE.exists():
        print(f"❌ Issues file not found: {ISSUES_FILE}")
        sys.exit(1)

    with open(ISSUES_FILE) as f:
        issues = json.load(f)

    print(f"📋 Found {len(issues)} issues to create\n")

    # Create labels
    print("🏷️  Creating labels...")
    labels = [
        # Epic labels
        ("epic:stories", "7B68EE", "Story-based architecture epic"),
        ("epic:ui", "1D76DB", "User interface improvements"),
        ("epic:ops", "0E8A16", "Operations and DevOps"),
        # Priority labels
        ("priority:p0", "D73A4A", "Critical - Blocking priority"),
        ("priority:p1", "FBCA04", "High priority"),
        ("priority:p2", "0E8A16", "Medium priority"),
        # Phase labels
        ("phase:planning", "BFD4F2", "Planning and design phase"),
        ("phase:infrastructure", "D4C5F9", "Infrastructure and foundation"),
        ("phase:clustering", "C2E0C6", "Clustering and intelligence"),
        ("phase:synthesis", "FEF2C0", "AI synthesis and generation"),
        ("phase:scheduling", "F9D0C4", "Scheduling and automation"),
        ("phase:ui", "D4E5FF", "User interface implementation"),
        ("phase:api", "FAD8C7", "API development"),
        ("phase:interests", "FDD7E4", "Interest-based filtering"),
        ("phase:testing", "EDEDED", "Testing and quality assurance"),
        ("phase:documentation", "D4F4DD", "Documentation"),
    ]

    for name, color, description in labels:
        create_label(name, color, description)

    print()

    # Create issues
    print("📝 Creating issues...\n")
    created = 0
    failed = 0

    for issue_data in issues:
        if create_issue(
            title=issue_data["title"],
            body=issue_data["body"],
            labels=issue_data.get("labels", []),
        ):
            created += 1
        else:
            failed += 1

    print()
    print("=" * 70)
    print(f"✅ Successfully created: {created} issues")
    if failed > 0:
        print(f"❌ Failed: {failed} issues")
    print("=" * 70)
    print()
    print("🎯 Next steps:")
    print("1. Visit https://github.com/Deim0s13/newsbrief/issues")
    print("2. Issues will auto-sync to Project #7 via project-automation workflow")
    print("3. Review and adjust priorities/assignments as needed")


if __name__ == "__main__":
    main()
