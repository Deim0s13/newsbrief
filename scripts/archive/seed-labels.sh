#!/usr/bin/env bash
set -euo pipefail

: "${REPO:?Set REPO to <owner>/<repo>}"

if ! command -v jq >/dev/null; then
  echo "jq is required (brew install jq)"; exit 1
fi

# Parse arguments
FORCE=false
LABELS_FILE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --force)
      FORCE=true
      shift
      ;;
    *)
      LABELS_FILE="$1"
      shift
      ;;
  esac
done

# Use provided file or default labels
if [[ -n "$LABELS_FILE" && -f "$LABELS_FILE" ]]; then
  LABELS_JSON=$(cat "$LABELS_FILE")
else
  LABELS_JSON='[
    {"name":"epic:ingestion","color":"1f77b4","description":"Feed ingestion and extraction"},
    {"name":"epic:summaries","color":"ff7f0e","description":"Summarization with Ollama"},
    {"name":"epic:ranking","color":"2ca02c","description":"Ranking and topic routing"},
    {"name":"epic:ui","color":"d62728","description":"Frontend/UI improvements"},
    {"name":"epic:embeddings","color":"9467bd","description":"Embeddings, clustering, semantic features"},
    {"name":"epic:search","color":"8c564b","description":"Search and Q&A"},
    {"name":"epic:ops","color":"e377c2","description":"Ops, health, testing"},
    {"name":"epic:apple-containers","color":"7f7f7f","description":"Experiment with Apple Containers runtime"},
    {"name":"in-progress","color":"0052cc","description":"Work has started"},
    {"name":"priority:P0","color":"d73a4a","description":"Critical / must do"},
    {"name":"priority:P1","color":"fbca04","description":"High"},
    {"name":"priority:P2","color":"0e8a16","description":"Medium"},
    {"name":"priority:P3","color":"c5def5","description":"Low"}
  ]'
fi

while read -r row; do
  name=$(echo "$row" | jq -r '.name')
  color=$(echo "$row" | jq -r '.color')
  desc=$(echo "$row" | jq -r '.description')

  if gh label list --repo "$REPO" --json name --jq '.[].name' | grep -Fx "$name" >/dev/null; then
    if [ "$FORCE" = true ]; then
      gh label edit "$name" --repo "$REPO" --color "$color" --description "$desc" >/dev/null
      echo "Updated label: $name"
    else
      echo "label with name \"$name\" already exists; use \`--force\` to update its color and description"
    fi
  else
    gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" >/dev/null
    echo "Created label: $name"
  fi
done < <(echo "$LABELS_JSON" | jq -c '.[]')
