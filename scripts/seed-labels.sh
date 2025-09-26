#!/usr/bin/env bash
set -euo pipefail

: "${REPO:?Set REPO to <owner>/<repo>}"

if ! command -v jq >/dev/null; then
  echo "jq is required (brew install jq)"; exit 1
fi

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

echo "$LABELS_JSON" | jq -c '.[]' | while read -r row; do
  name=$(echo "$row" | jq -r '.name')
  color=$(echo "$row" | jq -r '.color')
  desc=$(echo "$row" | jq -r '.description')

  if gh label view "$name" --repo "$REPO" >/dev/null 2>&1; then
    gh label edit "$name" --repo "$REPO" --color "$color" --description "$desc" >/dev/null
    echo "Updated label: $name"
  else
    gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" >/dev/null
    echo "Created label: $name"
  fi
done