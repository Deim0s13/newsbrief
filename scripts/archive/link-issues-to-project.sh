#!/usr/bin/env bash
# Link existing repo issues to a GitHub Project (v2), set Status/Epic, and VERIFY.
# Works on macOS bash 3.2+

set -euo pipefail

: "${OWNER:?Set OWNER (e.g., 'Deim0s13')}"
: "${REPO:?Set REPO (e.g., 'Deim0s13/newsbrief')}"

PROJECT_ID="${PROJECT_ID:-}"            # preferred (e.g., PVT_xxx)
PROJECT_NUMBER="${PROJECT_NUMBER:-}"    # alt
PROJECT_NAME="${PROJECT_NAME:-}"        # fallback

if ! command -v jq >/dev/null; then echo "jq required"; exit 1; fi
if ! command -v gh >/dev/null; then echo "gh required"; exit 1; fi

OWNER_LOGIN="${OWNER#@}"

# ---------- Resolve PROJECT_ID ----------
if [ -n "$PROJECT_ID" ]; then
  echo "Using provided PROJECT_ID=$PROJECT_ID"
else
  if [ -n "$PROJECT_NUMBER" ]; then
    PROJECT_ID=$(gh api graphql -f query='
      query($login:String!, $number:Int!){
        user(login:$login){ projectV2(number:$number){ id } }
        organization(login:$login){ projectV2(number:$number){ id } }
      }' -F login="$OWNER_LOGIN" -F number="$PROJECT_NUMBER" \
      --jq '.data.user.projectV2.id // .data.organization.projectV2.id')
  else
    PROJECT_ID=$(gh api graphql -f query='
      query($login:String!){
        user(login:$login){ projectsV2(first:50){ nodes { id title createdAt } } }
        organization(login:$login){ projectsV2(first:50){ nodes { id title createdAt } } }
      }' -F login="$OWNER_LOGIN" \
      --jq "((.data.user.projectsV2.nodes // []) + (.data.organization.projectsV2.nodes // []))
            | map(select(.title==\"${PROJECT_NAME}\")) | sort_by(.createdAt) | last | .id")
  fi
  [ -z "${PROJECT_ID:-}" -o "${PROJECT_ID}" = "null" ] && echo "❌ Could not resolve PROJECT_ID" && exit 1
  echo "Resolved PROJECT_ID=$PROJECT_ID"
fi

# ---------- Fetch fields ----------
FIELDS_JSON=$(gh api graphql -f query='
query($project:ID!){
  node(id:$project){
    ... on ProjectV2 {
      fields(first:50){
        nodes{
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField { id name options { id name } }
        }
      }
    }
  }
}' -F project="$PROJECT_ID")

STATUS_FIELD_ID=$(echo "$FIELDS_JSON" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .id')
EPIC_FIELD_ID=$(echo "$FIELDS_JSON"   | jq -r '.data.node.fields.nodes[] | select(.name=="Epic")   | .id')

[ -z "${STATUS_FIELD_ID:-}" -o "${STATUS_FIELD_ID}" = "null" ] && echo "❌ No 'Status' field found in project" && exit 1
[ -z "${EPIC_FIELD_ID:-}" -o "${EPIC_FIELD_ID}" = "null" ] && echo "ℹ️  No 'Epic' field found (epic:* labels will be ignored)"

# Gather Status options
STATUS_OPTIONS=()
while IFS= read -r opt; do [ -n "$opt" ] && STATUS_OPTIONS+=("$opt"); done < <(
  echo "$FIELDS_JSON" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .options[]?.name'
)
[ "${#STATUS_OPTIONS[@]}" -eq 0 ] && echo "❌ Status has 0 options" && exit 1

# Helper to match names (case-insensitive)
find_status_opt() {
  local pattern="$1"
  for opt in "${STATUS_OPTIONS[@]}"; do
    if printf "%s" "$opt" | awk "BEGIN{IGNORECASE=1} \$0 ~ /$pattern/ {print; exit}" >/dev/null; then
      echo "$opt"; return 0
    fi
  done
  echo ""
}

STATUS_OPEN_NAME="${STATUS_OPTIONS[0]}"
STATUS_DONE_NAME="$(find_status_opt 'done|complete|closed|resolved')"
STATUS_INPROG_NAME="$(find_status_opt 'in.?progress|progress|doing|wip|started')"
[ -z "$STATUS_DONE_NAME" ]   && STATUS_DONE_NAME="${STATUS_OPTIONS[${#STATUS_OPTIONS[@]}-1]}"
[ -z "$STATUS_INPROG_NAME" ] && STATUS_INPROG_NAME="$STATUS_OPEN_NAME"

echo "Status options detected:"
printf "  OPEN -> '%s'\n  WIP  -> '%s'\n  DONE -> '%s'\n" "$STATUS_OPEN_NAME" "$STATUS_INPROG_NAME" "$STATUS_DONE_NAME"

# ---------- helpers ----------
option_id_for() {
  local field_id="$1"; shift
  local name="$2"; shift
  echo "$FIELDS_JSON" | jq -r --arg fid "$field_id" --arg name "$name" '
    .data.node.fields.nodes[] | select(.id==$fid) | .options[]? | select(.name==$name) | .id
  '
}

set_single_select() {
  local item_id="$1"; shift
  local field_id="$2"; shift
  local option_name="${3:-}"; shift
  [ -z "$field_id" -o -z "$option_name" ] && return 0
  local oid; oid="$(option_id_for "$field_id" "$option_name")"
  if [ -z "$oid" -o "$oid" = "null" ]; then
    echo "   ⚠️  Option '$option_name' not found on field; skipping"
    return 0
  fi
  gh api graphql -f query='
  mutation($project:ID!,$item:ID!,$field:ID!,$opt:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project,itemId:$item,fieldId:$field,value:{ singleSelectOptionId:$opt }
    }){ projectV2Item { id } }
  }' -F project="$PROJECT_ID" -F item="$item_id" -F field="$field_id" -F opt="$oid" >/dev/null
}

add_or_find_item() {
  local content_id="$1"; shift
  local item_id
  item_id=$(gh api graphql -f query='
    mutation($project:ID!,$content:ID!){
      addProjectV2ItemById(input:{projectId:$project, contentId:$content}){ item { id } }
    }' -F project="$PROJECT_ID" -F content="$content_id" --jq '.data.addProjectV2ItemById.item.id' 2>/dev/null || true)
  if [ -n "$item_id" ] && [ "$item_id" != "null" ]; then echo "$item_id"; return 0; fi
  # find existing
  item_id=$(gh api graphql -f query='
    query($project:ID!){
      node(id:$project){
        ... on ProjectV2 {
          items(first:200){ nodes { id content { ... on Issue { id } ... on PullRequest { id } } } }
        }
      }
    }' -F project="$PROJECT_ID" \
    --jq '.data.node.items.nodes[] | select(.content != null) | .id + "|" + .content.id' \
    | awk -F'|' -v cid="$content_id" '$2==cid{print $1; exit}')
  echo "$item_id"
}

get_status_name() {
  local item_id="$1"; shift
  gh api graphql -f query='
  query($item:ID!){
    node(id:$item){
      ... on ProjectV2Item {
        fieldValueByName(name:"Status"){
          ... on ProjectV2ItemFieldSingleSelectValue { name }
        }
      }
    }
  }' -F item="$item_id" --jq '.data.node.fieldValueByName.name'
}

# ---------- Process issues ----------
echo "→ Fetching issues from $REPO..."
ISSUES=$(gh issue list --repo "$REPO" --state all --limit 500 --json id,number,title,labels,state)
total=$(echo "$ISSUES" | jq 'length')
echo "✓ Found $total issues"

idx=0
echo "$ISSUES" | jq -c '.[]' | while read -r row; do
  idx=$((idx+1))
  node_id=$(echo "$row" | jq -r '.id')
  number=$(echo "$row" | jq -r '.number')
  title=$(echo "$row" | jq -r '.title')
  state=$(echo "$row" | jq -r '.state')
  epic_label=$(echo "$row" | jq -r '.labels[]?.name | select(startswith("epic:"))' | head -n 1 | sed 's/^epic://')

  printf "  [%3d/%3d] #%s %s ...\n" "$idx" "$total" "$number" "$title"

  item_id=$(add_or_find_item "$node_id")
  if [ -z "$item_id" ] || [ "$item_id" = "null" ]; then
    echo "     ⚠️  could not add/find project item"; continue
  fi

  # decide desired status
  desired="$STATUS_OPEN_NAME"
  case "$state" in
    OPEN|open) desired="$STATUS_OPEN_NAME" ;;
    CLOSED|closed) desired="$STATUS_DONE_NAME" ;;
  esac
  echo "     → Setting Status to '$desired'"
  set_single_select "$item_id" "$STATUS_FIELD_ID" "$desired"

  # verify
  actual=$(get_status_name "$item_id" || true)
  echo "     ✓ Status now: '${actual:-<none>}'"
  if [ "${actual:-}" != "$desired" ]; then
    echo "     ⚠️  Mismatch (wanted '$desired'); check field options/permissions."
  fi

  if [ -n "${EPIC_FIELD_ID:-}" ] && [ "$EPIC_FIELD_ID" != "null" ] && [ -n "$epic_label" ]; then
    echo "     → Setting Epic to '$epic_label'"
    set_single_select "$item_id" "$EPIC_FIELD_ID" "$epic_label"
  fi
done

echo "✅ Done."
