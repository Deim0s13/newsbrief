#!/usr/bin/env bash
set -euo pipefail

: "${REPO:?Set REPO to <owner>/<repo>}"
FILE="${1:-data/issues.json}"

if ! command -v jq >/dev/null; then
  echo "jq is required (brew install jq)"; exit 1
fi

jq -c '.[]' "$FILE" | while read -r row; do
  title=$(echo "$row" | jq -r '.title')
  body=$(echo "$row" | jq -r '.body // ""')
  labels=$(echo "$row" | jq -r '.labels | join(",")')

  # Optional: skip if an issue with same title already exists
  # if gh issue list --repo "$REPO" --search "in:title \"$title\"" --json title \
  #      | jq -e "any(.[]; .title == \"$title\")" >/dev/null; then
  #   echo "Skip (exists): $title"
  #   continue
  # fi

  if [ -n "$labels" ]; then
    gh issue create --repo "$REPO" --title "$title" --body "$body" --label "$labels" >/dev/null
  else
    gh issue create --repo "$REPO" --title "$title" --body "$body" >/dev/null
  fi
  echo "Created: $title"
done
