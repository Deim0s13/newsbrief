# NewsBrief infrastructure startup script for Windows (Podman Desktop)
# Equivalent to scripts/infra-start.sh for macOS.
# Registered as a Task Scheduler task via scripts/infra-task-install.ps1.
# Run manually: powershell -ExecutionPolicy Bypass -File scripts\infra-start.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ClusterName = "newsbrief-dev"
$ClusterConfig = Join-Path $ProjectRoot "kind\cluster-config.yaml"
$LogDir = Join-Path $ProjectRoot "logs"

function Log { param($msg); Write-Host "[newsbrief-infra] $msg" }

# Ensure log directory exists
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# 1. Ensure Podman machine is running (Podman Desktop manages this, but be safe)
try {
    $machineStatus = podman machine info --format "{{.Host.MachineState}}" 2>$null
    if ($machineStatus -ne "Running") {
        Log "Starting Podman machine..."
        podman machine start
    } else {
        Log "Podman machine already running"
    }
} catch {
    Log "Warning: could not check Podman machine status: $_"
}

# 2. Ensure kind cluster exists
$clusters = kind get clusters 2>$null
if ($clusters -match "^$ClusterName$") {
    Log "Kind cluster '$ClusterName' already exists"
} else {
    Log "Creating kind cluster '$ClusterName'..."
    kind create cluster --name $ClusterName --config $ClusterConfig
}

# 3. Export kubeconfig
kind export kubeconfig --name $ClusterName
Log "Kubeconfig set to cluster '$ClusterName'"

# 4. Wait for ArgoCD
Log "Waiting for ArgoCD server..."
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=180s
Log "ArgoCD is ready"

# 5. Trigger ArgoCD sync
try {
    argocd app sync newsbrief-dev --async 2>$null
    Log "Triggered sync: newsbrief-dev"
} catch {
    Log "Warning: could not sync newsbrief-dev"
}
try {
    argocd app sync newsbrief-prod --async 2>$null
    Log "Triggered sync: newsbrief-prod"
} catch {
    Log "Warning: could not sync newsbrief-prod"
}

# 6. Re-establish port-forwards
Get-Process -Name "kubectl" -ErrorAction SilentlyContinue | Stop-Process -Force

$portForwardLog = Join-Path $LogDir "port-forward.log"

Start-Process kubectl `
    -ArgumentList "port-forward svc/newsbrief -n newsbrief-prod --address 0.0.0.0 8788:8787" `
    -RedirectStandardOutput $portForwardLog -WindowStyle Hidden
Start-Process kubectl `
    -ArgumentList "port-forward svc/newsbrief -n newsbrief-dev --address 0.0.0.0 8789:8787" `
    -RedirectStandardOutput $portForwardLog -WindowStyle Hidden
Start-Process kubectl `
    -ArgumentList "port-forward svc/argocd-server -n argocd 8443:443" `
    -RedirectStandardOutput $portForwardLog -WindowStyle Hidden
Start-Process kubectl `
    -ArgumentList "port-forward svc/tekton-dashboard -n tekton-pipelines 9097:9097" `
    -RedirectStandardOutput $portForwardLog -WindowStyle Hidden

Log "Port-forwards started:"
Log "  Prod app:   http://localhost:8788"
Log "  Dev app:    http://localhost:8789"
Log "  ArgoCD UI:  https://localhost:8443"
Log "  Tekton UI:  http://localhost:9097"
Log "NewsBrief infrastructure ready."
