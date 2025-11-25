#!/usr/bin/env python3
"""
Script to create technical debt issues for v0.6.0 using GitHub CLI.
"""

import json
import subprocess
import sys
from pathlib import Path


def create_issue(title: str, body: str, labels: list[str], milestone: str) -> bool:
    """Create a GitHub issue using gh CLI."""
    
    # Build gh CLI command
    cmd = [
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
        "--milestone", milestone,
    ]
    
    # Add labels
    for label in labels:
        cmd.extend(["--label", label])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Created: {title}")
        print(f"   URL: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create: {title}")
        print(f"   Error: {e.stderr}")
        return False


def main():
    """Main function to import technical debt issues."""
    
    # Check if gh CLI is available
    try:
        subprocess.run(["gh", "auth", "status"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("❌ GitHub CLI not authenticated. Run: gh auth login")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ GitHub CLI (gh) not found. Install from: https://cli.github.com/")
        sys.exit(1)
    
    # Load issues from JSON
    json_path = Path(__file__).parent.parent / "docs" / "issues" / "TECHNICAL_DEBT_ISSUES.json"
    
    if not json_path.exists():
        print(f"❌ Issue file not found: {json_path}")
        sys.exit(1)
    
    with open(json_path, 'r') as f:
        issues = json.load(f)
    
    print(f"📋 Found {len(issues)} technical debt issues to create\n")
    
    # Create each issue
    success_count = 0
    for i, issue in enumerate(issues, 1):
        print(f"\n[{i}/{len(issues)}] Creating issue...")
        if create_issue(
            title=issue["title"],
            body=issue["body"],
            labels=issue["labels"],
            milestone=issue["milestone"]
        ):
            success_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Successfully created: {success_count}/{len(issues)} issues")
    if success_count < len(issues):
        print(f"❌ Failed: {len(issues) - success_count} issues")
        sys.exit(1)
    else:
        print("\n🎉 All technical debt issues created successfully!")


if __name__ == "__main__":
    main()

