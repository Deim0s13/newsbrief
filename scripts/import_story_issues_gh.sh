#!/bin/bash
# Bulk import story architecture issues using GitHub CLI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISSUES_FILE="$SCRIPT_DIR/../data/story-architecture-issues.json"

echo "🚀 Importing story architecture issues to GitHub"
echo

# Check if gh CLI is authenticated
if ! gh auth status >/dev/null 2>&1; then
    echo "❌ GitHub CLI not authenticated"
    echo "Please run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI authenticated"
echo

# Create labels first
echo "🏷️  Creating labels..."

declare -A LABELS=(
    # Epic labels
    ["epic:stories"]="7B68EE:Story-based architecture epic"
    ["epic:ui"]="1D76DB:User interface improvements"
    ["epic:ops"]="0E8A16:Operations and DevOps"
    
    # Priority labels
    ["priority:p0"]="D73A4A:Critical - Blocking priority"
    ["priority:p1"]="FBCA04:High priority"
    ["priority:p2"]="0E8A16:Medium priority"
    
    # Phase labels
    ["phase:planning"]="BFD4F2:Planning and design phase"
    ["phase:infrastructure"]="D4C5F9:Infrastructure and foundation"
    ["phase:clustering"]="C2E0C6:Clustering and intelligence"
    ["phase:synthesis"]="FEF2C0:AI synthesis and generation"
    ["phase:scheduling"]="F9D0C4:Scheduling and automation"
    ["phase:ui"]="D4E5FF:User interface implementation"
    ["phase:api"]="FAD8C7:API development"
    ["phase:interests"]="FDD7E4:Interest-based filtering"
    ["phase:testing"]="EDEDED:Testing and quality assurance"
    ["phase:documentation"]="D4F4DD:Documentation"
)

for label_name in "${!LABELS[@]}"; do
    IFS=':' read -r color description <<< "${LABELS[$label_name]}"
    
    if gh label list --json name --jq ".[].name" | grep -q "^${label_name}$"; then
        echo "  ℹ️  Label '$label_name' already exists"
    else
        gh label create "$label_name" --color "$color" --description "$description" 2>/dev/null && \
            echo "  ✅ Created label '$label_name'" || \
            echo "  ⚠️  Failed to create label '$label_name'"
    fi
done

echo
echo "📝 Creating issues from $ISSUES_FILE..."
echo

# Read and create issues
created=0
failed=0

while IFS= read -r line; do
    # Skip if not a valid issue object (array brackets, etc)
    if [[ ! "$line" =~ \"title\" ]]; then
        continue
    fi
    
    # Parse JSON (simple extraction)
    title=$(echo "$line" | grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"title"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/')
    body=$(echo "$line" | grep -o '"body"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"body"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/' | sed 's/\\n/\n/g')
    labels=$(echo "$line" | grep -o '"labels"[[:space:]]*:[[:space:]]*\[[^]]*\]' | grep -o '"[^"]*"' | tr -d '"' | tr '\n' ',' | sed 's/,$//')
    
    if [ -n "$title" ]; then
        echo "Creating: $title"
        
        if gh issue create --title "$title" --body "$body" --label "$labels" >/dev/null 2>&1; then
            echo "  ✅ Created"
            ((created++))
        else
            echo "  ❌ Failed"
            ((failed++))
        fi
    fi
done < <(cat "$ISSUES_FILE" | jq -c '.[]')

echo
echo "=================================================================="
echo "✅ Successfully created: $created issues"
if [ $failed -gt 0 ]; then
    echo "❌ Failed: $failed issues"
fi
echo "=================================================================="
echo
echo "🎯 Next steps:"
echo "1. Visit https://github.com/Deim0s13/newsbrief/issues"
echo "2. Issues will auto-sync to Project #7 via project-automation workflow"
echo "3. Review and adjust priorities/assignments as needed"

