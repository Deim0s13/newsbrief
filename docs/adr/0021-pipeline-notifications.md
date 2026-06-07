# ADR-0021: Pipeline Failure Notifications

## Status
**Accepted** - January 2026

> Note (June 2026): The ntfy.sh notification decision remains valid and is still in use. The implementation mechanism changed from Tekton finally blocks to GitHub Actions job steps and a `compose-watch.sh` deploy step (see ADR-0032). The notification channel and strategy are unchanged.

## Context

NewsBrief uses Tekton pipelines for CI/CD running in a local kind cluster. When pipelines fail, developers currently need to manually check pipeline status via `kubectl` or the Tekton Dashboard. This creates a poor developer experience and delays response to failures.

Requirements:
1. **Immediate awareness** - Know within seconds when a pipeline fails
2. **Local-first** - Work with the local development setup
3. **Low overhead** - No complex infrastructure to maintain
4. **Future flexibility** - Support team notifications (Slack) when needed

## Decision

Implement a **dual notification strategy**:

### Primary: ntfy.sh for macOS Notifications
- Use [ntfy.sh](https://ntfy.sh) pub-sub notification service
- Native macOS app delivers system notifications
- Works when laptop sleeps/wakes (push-based)
- Free tier is sufficient for development use

### Secondary: Slack Webhook (Groundwork Only)
- Create Tekton task for Slack notifications
- Disabled by default (no webhook URL configured)
- Can be activated for team environments
- Follows same pattern as ntfy.sh task

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tekton Pipeline                              │
│                                                                 │
│  ┌──────┐  ┌──────┐  ┌───────┐  ┌──────┐  ┌────────┐           │
│  │ lint │──│ test │──│ build │──│ scan │──│  sign  │           │
│  └──────┘  └──────┘  └───────┘  └──────┘  └────────┘           │
│                                                                 │
│  finally:                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              notify-failure (when: failed)              │   │
│  │  ┌───────────────┐      ┌───────────────────────────┐   │   │
│  │  │   ntfy.sh     │      │   Slack (disabled)        │   │   │
│  │  │ POST /topic   │      │   POST webhook URL        │   │   │
│  │  └───────┬───────┘      └───────────────────────────┘   │   │
│  └──────────│──────────────────────────────────────────────┘   │
└─────────────│──────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ntfy.sh Service                             │
│                                                                 │
│  ┌─────────────────┐                                            │
│  │  Topic: newsbrief│ ──────────────────┐                       │
│  └─────────────────┘                    │                       │
│                                         ▼                       │
│                              ┌──────────────────┐               │
│                              │  macOS ntfy app  │               │
│                              │  System Notif.   │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation

### 1. ntfy.sh Notification Task

```yaml
# tekton/tasks/notify-ntfy.yaml
apiVersion: tekton.dev/v1beta1
kind: Task
metadata:
  name: notify-ntfy
spec:
  params:
    - name: topic
      description: ntfy.sh topic name
      default: "newsbrief-ci"
    - name: title
      description: Notification title
    - name: message
      description: Notification message
    - name: priority
      description: Priority (min, low, default, high, urgent)
      default: "high"
    - name: tags
      description: Emoji tags (comma-separated)
      default: "x,pipeline"
  steps:
    - name: send-notification
      image: curlimages/curl:latest
      script: |
        #!/bin/sh
        curl -s \
          -H "Title: $(params.title)" \
          -H "Priority: $(params.priority)" \
          -H "Tags: $(params.tags)" \
          -d "$(params.message)" \
          "https://ntfy.sh/$(params.topic)"
        echo "✅ Notification sent to ntfy.sh/$(params.topic)"
```

### 2. Pipeline Integration (ntfy only)

```yaml
# In ci-dev.yaml and ci-prod.yaml
finally:
  - name: notify-failure
    when:
      - input: $(tasks.status)
        operator: in
        values: ["Failed"]
    taskRef:
      name: notify-ntfy
    params:
      - name: topic
        value: "newsbrief-ci"
      - name: title
        value: "❌ Pipeline Failed"
      - name: message
        value: "Pipeline $(context.pipelineRun.name) failed on $(params.git-revision)"
      - name: priority
        value: "high"
      - name: tags
        value: "x,pipeline,$(params.environment)"

  - name: notify-success
    when:
      - input: $(tasks.status)
        operator: in
        values: ["Succeeded"]
    taskRef:
      name: notify-ntfy
    params:
      - name: topic
        value: "newsbrief-ci"
      - name: title
        value: "✅ Pipeline Succeeded"
      - name: message
        value: "Pipeline $(context.pipelineRun.name) completed successfully"
      - name: priority
        value: "default"
      - name: tags
        value: "white_check_mark,pipeline"
```

### 3. macOS Setup

```bash
# Install ntfy macOS app
brew install --cask ntfy

# Or download from: https://ntfy.sh/docs/subscribe/macos/

# Subscribe to your topic in the app:
# Topic: newsbrief-ci
```

## Configuration

### Environment Variables / Secrets

| Variable | Purpose | Required |
|----------|---------|----------|
| `NTFY_TOPIC` | ntfy.sh topic name | Yes (default: newsbrief-ci) |

## Consequences

### Positive
- ✅ Immediate notification of pipeline failures
- ✅ Native macOS system notifications
- ✅ No local infrastructure to maintain
- ✅ Works when laptop sleeps/wakes
- ✅ Zero cost (ntfy.sh free tier)

### Negative
- ⚠️ Depends on external service (ntfy.sh)
- ⚠️ Topic is public by default (use unique topic name)
- ⚠️ Requires internet connectivity for notifications

### Mitigations
- Use unique, hard-to-guess topic names (e.g., `newsbrief-ci-a8x9k2`)
- For sensitive environments, self-host ntfy server

## Alternatives Considered

### 1. Local Webhook Receiver
- Run small service on macOS receiving webhooks
- Rejected: Requires maintaining local service, doesn't work when Mac sleeps

### 2. Email Notifications
- Send emails via SMTP
- Rejected: Higher latency, requires email server setup

### 3. Pushover
- Commercial push notification service
- Rejected: Requires paid subscription, ntfy.sh is free

### 4. GitHub Actions Notifications
- Retired GitHub Actions workflow
- Rejected: We migrated to Tekton

## References

- [ntfy.sh Documentation](https://ntfy.sh/docs/)
- [ntfy macOS App](https://ntfy.sh/docs/subscribe/macos/)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [Tekton Finally Tasks](https://tekton.dev/docs/pipelines/pipelines/#adding-finally-to-the-pipeline)
- [ADR-0019: CI/CD Pipeline Design](0019-cicd-pipeline-design.md)
