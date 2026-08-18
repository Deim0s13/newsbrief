#!/usr/bin/env bash
set -euo pipefail

: "${OWNER:?Set OWNER to org or @user}"
: "${PROJECT_NAME:?Set PROJECT_NAME (e.g., 'NewsBrief Roadmap')}"

OWNER_LOGIN="${OWNER#@}"

# 🔹 1) Resolve owner node ID (org first, then user)
# Expect OWNER to be a user login (e.g., Deim0s13) or @user; orgs also work.
OWNER_LOGIN="${OWNER#@}"

echo "Resolving owner id for '$OWNER_LOGIN'..."

# Try user first
set +e
OWNER_ID=$(gh api graphql -f query='query($login:String!){ user(login:$login){ id } }' -F login="$OWNER_LOGIN" --jq '.data.user.id' 2>/dev/null)
set -e

# If not a user, try organization
if [ -z "${OWNER_ID}" ] || [ "${OWNER_ID}" = "null" ]; then
  OWNER_ID=$(gh api graphql -f query='query($login:String!){ organization(login:$login){ id } }' -F login="$OWNER_LOGIN" --jq '.data.organization.id')
fi

if [ -z "${OWNER_ID}" ] || [ "${OWNER_ID}" = "null" ]; then
  echo "❌ Could not resolve an owner id for '$OWNER_LOGIN'. Is this a valid GitHub user/org? Do you have access?"
  exit 1
fi

echo "OWNER_ID=$OWNER_ID"

# 🔹 2) Create project
PROJECT_ID=$(gh api graphql -f query='
mutation($ownerId:ID!,$title:String!){
  createProjectV2(input:{ownerId:$ownerId,title:$title}){projectV2{id title}}
}' -F ownerId="$OWNER_ID" -F title="$PROJECT_NAME" --jq '.data.createProjectV2.projectV2.id')
echo "✅ Created project: $PROJECT_ID"

# 🔹 3) Add fields (Epic, Priority, Target Date)
add_single_select () {
  local name="$1"; shift
  local opts_json="$1"; shift
  local fid
  fid=$(gh api graphql -f query='
  mutation($project:ID!,$name:String!){
    addProjectV2Field(input:{projectId:$project,name:$name,dataType:SINGLE_SELECT}){projectV2Field{id}}
  }' -F project="$PROJECT_ID" -F name="$name" --jq '.data.addProjectV2Field.projectV2Field.id')
  echo "Field '$name' id: $fid"

  # add options
  echo "$opts_json" | jq -c '.[]' | while read -r row; do
    opt_name=$(echo "$row" | jq -r '.name')
    opt_color=$(echo "$row" | jq -r '.color')
    gh api graphql -f query='
    mutation($project:ID!,$field:ID!,$name:String!,$color:String!){
      updateProjectV2SingleSelectField(input:{projectId:$project,fieldId:$field,options:[{name:$name,color:$color}]}){projectV2{title}}
    }' -F project="$PROJECT_ID" -F field="$fid" -F name="$opt_name" -F color="$opt_color" >/dev/null
  done
  echo "$fid"
}

EPIC_OPTS='[
  {"name":"ingestion","color":"BLUE"},
  {"name":"summaries","color":"ORANGE"},
  {"name":"ranking","color":"GREEN"},
  {"name":"ui","color":"RED"},
  {"name":"embeddings","color":"PURPLE"},
  {"name":"search","color":"BROWN"},
  {"name":"ops","color":"PINK"},
  {"name":"apple-containers","color":"GRAY"}
]'
EPIC_FIELD_ID=$(add_single_select "Epic" "$EPIC_OPTS")

PRIORITY_OPTS='[
  {"name":"P0","color":"RED"},
  {"name":"P1","color":"ORANGE"},
  {"name":"P2","color":"YELLOW"},
  {"name":"P3","color":"BLUE"}
]'
PRIORITY_FIELD_ID=$(add_single_select "Priority" "$PRIORITY_OPTS")

TARGET_DATE_FIELD_ID=$(gh api graphql -f query='
mutation($project:ID!){
  addProjectV2Field(input:{projectId:$project,name:"Target Date",dataType:DATE}){projectV2Field{id}}
}' -F project="$PROJECT_ID" --jq '.data.addProjectV2Field.projectV2Field.id')
echo "Field 'Target Date' id: $TARGET_DATE_FIELD_ID"

# 🔹 4) Create views
STATUS_FIELD_ID=$(gh api graphql -f query='
query($project:ID!){
  node(id:$project){
    ... on ProjectV2{
      fields(first:50){nodes{... on ProjectV2FieldCommon{id,name,dataType}}}
    }
  }
}' -F project="$PROJECT_ID" --jq '.data.node.fields.nodes[] | select(.name=="Status") | .id')

create_view () {
  local name="$1"; shift
  local layout="$1"; shift # BOARD or TABLE
  gh api graphql -f query='
  mutation($project:ID!,$name:String!,$layout:ProjectV2ViewLayout!){
    addProjectV2View(input:{projectId:$project,name:$name,layout:$layout}){projectV2View{id}}
  }' -F project="$PROJECT_ID" -F name="$name" -F layout="$layout" --jq '.data.addProjectV2View.projectV2View.id'
}

BOARD_STATUS_VIEW_ID=$(create_view "Board (by Status)" "BOARD")
TABLE_OPEN_VIEW_ID=$(create_view "Table (Open)" "TABLE")
BOARD_EPIC_VIEW_ID=$(create_view "Board (by Epic)" "BOARD")

# group Board (by Status) by Status
gh api graphql -f query='
mutation($view:ID!,$field:ID!){
  updateProjectV2View(input:{viewId:$view,groupBy:"FIELD",groupByFieldId:$field}){projectV2View{id}}
}' -F view="$BOARD_STATUS_VIEW_ID" -F field="$STATUS_FIELD_ID" >/dev/null

# filter Table (Open) to open issues
gh api graphql -f query='
mutation($view:ID!){
  updateProjectV2View(input:{viewId:$view,filter:"is:issue is:open"}){projectV2View{id}}
}' -F view="$TABLE_OPEN_VIEW_ID" >/dev/null

# group Board (by Epic) by Epic field
gh api graphql -f query='
mutation($view:ID!,$field:ID!){
  updateProjectV2View(input:{viewId:$view,groupBy:"FIELD",groupByFieldId:$field}){projectV2View{id}}
}' -F view="$BOARD_EPIC_VIEW_ID" -F field="$EPIC_FIELD_ID" >/dev/null

echo "✅ Done."
echo "Project ID: $PROJECT_ID"
echo "Views:"
echo " - Board (by Status): $BOARD_STATUS_VIEW_ID"
echo " - Table (Open): $TABLE_OPEN_VIEW_ID"
echo " - Board (by Epic): $BOARD_EPIC_VIEW_ID"
