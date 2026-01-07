#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID (e.g., PVT_xxx)}"

# fetch Status field + option ids
FIELDS=$(gh api graphql -f query='
query($project:ID!){
  node(id:$project){
    ... on ProjectV2 {
      fields(first:50){
        nodes{
          ... on ProjectV2SingleSelectField { id name options { id name } }
        }
      }
      items(first:100){
        nodes { id fieldValueByName(name:"Status"){ ... on ProjectV2ItemFieldSingleSelectValue { name } } }
      }
    }
  }
}' -F project="$PROJECT_ID")

STATUS_FIELD_ID=$(echo "$FIELDS" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .id')
TODO_OPT_ID=$(echo "$FIELDS" | jq -r '.data.node.fields.nodes[] | select(.name=="Status") | .options[] | select(.name=="Todo") | .id')

if [ -z "$TODO_OPT_ID" ] || [ "$TODO_OPT_ID" = "null" ]; then
  echo "Could not find 'Todo' option on Status field"; exit 1
fi

# iterate items with No Status
echo "$FIELDS" | jq -r '.data.node.items.nodes[] | select(.fieldValueByName == null) | .id' | while read -r ITEM_ID; do
  echo "Setting item $ITEM_ID -> Todo"
  gh api graphql -f query='
  mutation($project:ID!,$item:ID!,$field:ID!,$opt:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project,itemId:$item,fieldId:$field,
      value:{ singleSelectOptionId:$opt }
    }){ projectV2Item { id } }
  }' -F project="$PROJECT_ID" -F item="$ITEM_ID" -F field="$STATUS_FIELD_ID" -F opt="$TODO_OPT_ID" > /dev/null
done

echo "Done."
