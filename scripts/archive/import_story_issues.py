#!/usr/bin/env python3
"""
Bulk import story architecture issues to GitHub.
Creates labels and issues from story-architecture-issues.json.
"""
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests package required. Install with: pip install requests")
    sys.exit(1)

# Configuration
REPO_OWNER = "Deim0s13"
REPO_NAME = "newsbrief"
ISSUES_FILE = Path(__file__).parent.parent / "data" / "story-architecture-issues.json"

# GitHub token from environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN environment variable required")
    print("Create a token at: https://github.com/settings/tokens")
    print("Required scopes: repo, write:org (for projects)")
    sys.exit(1)

# API setup
BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def create_label(name: str, color: str, description: str = "") -> bool:
    """Create a label if it doesn't exist."""
    url = f"{BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}/labels"

    # Check if label exists
    response = requests.get(url, headers=HEADERS)
    if response.ok:
        existing = {label["name"] for label in response.json()}
        if name in existing:
            print(f"  ℹ️  Label '{name}' already exists")
            return True

    # Create label
    data = {"name": name, "color": color, "description": description}
    response = requests.post(url, headers=HEADERS, json=data)

    if response.status_code == 201:
        print(f"  ✅ Created label '{name}'")
        return True
    else:
        print(f"  ⚠️  Failed to create label '{name}': {response.status_code}")
        return False


def create_issue(title: str, body: str, labels: list) -> dict:
    """Create a GitHub issue."""
    url = f"{BASE_URL}/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    data = {
        "title": title,
        "body": body,
        "labels": labels,
    }

    response = requests.post(url, headers=HEADERS, json=data)

    if response.status_code == 201:
        issue = response.json()
        print(f"  ✅ Created issue #{issue['number']}: {title}")
        return issue
    else:
        print(f"  ❌ Failed to create issue '{title}': {response.status_code}")
        print(f"     Response: {response.text}")
        return None


def main():
    print(f"🚀 Importing story architecture issues to {REPO_OWNER}/{REPO_NAME}\n")

    # Load issues
    if not ISSUES_FILE.exists():
        print(f"❌ Issues file not found: {ISSUES_FILE}")
        sys.exit(1)

    with open(ISSUES_FILE) as f:
        issues = json.load(f)

    print(f"📋 Found {len(issues)} issues to create\n")

    # Define and create labels
    print("🏷️  Creating labels...")
    labels_to_create = [
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

    for name, color, description in labels_to_create:
        create_label(name, color, description)

    print()

    # Create issues
    print("📝 Creating issues...")
    created_count = 0
    failed_count = 0

    for issue_data in issues:
        result = create_issue(
            title=issue_data["title"],
            body=issue_data["body"],
            labels=issue_data.get("labels", []),
        )

        if result:
            created_count += 1
        else:
            failed_count += 1

    print()
    print("=" * 60)
    print(f"✅ Successfully created: {created_count} issues")
    if failed_count > 0:
        print(f"❌ Failed: {failed_count} issues")
    print("=" * 60)
    print()
    print("🎯 Next steps:")
    print("1. Visit https://github.com/{}/{}/issues".format(REPO_OWNER, REPO_NAME))
    print("2. Issues will auto-sync to Project #7 via project-automation workflow")
    print("3. Review and adjust priorities/assignments as needed")


if __name__ == "__main__":
    main()
