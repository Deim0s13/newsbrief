#!/bin/bash
# Smee.io webhook relay client
# This script forwards GitHub webhooks to the local Tekton EventListener

set -e

# Configuration
SMEE_URL="${SMEE_URL:-https://smee.io/cddqBCYHwHG3ZcUY}"
TARGET_URL="${TARGET_URL:-http://localhost:8080}"

echo "🔗 Smee.io Webhook Relay"
echo "========================"
echo ""
echo "📡 Smee URL: $SMEE_URL"
echo "🎯 Target:   $TARGET_URL"
echo ""
echo "📋 GitHub Webhook Setup:"
echo "   1. Go to: https://github.com/Deim0s13/newsbrief/settings/hooks"
echo "   2. Add webhook with:"
echo "      - Payload URL: $SMEE_URL"
echo "      - Content type: application/json"
echo "      - Secret: (use the webhook secret from kubectl get secret github-webhook-secret)"
echo "      - Events: Just the push event"
echo ""
echo "⚠️  Make sure port-forward is running in another terminal:"
echo "   kubectl port-forward svc/el-newsbrief-listener 8080:8080"
echo ""
echo "Starting smee client..."
echo ""

# Run smee client
npx smee-client --url "$SMEE_URL" --target "$TARGET_URL"
