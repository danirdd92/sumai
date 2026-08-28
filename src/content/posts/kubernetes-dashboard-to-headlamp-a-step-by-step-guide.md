---
title: "Kubernetes Dashboard to Headlamp: A Step-by-Step Guide"
originalUrl: "https://kubernetes.io/blog/2026/07/13/kubernetes-dashboard-to-headlamp/"
publishDate: 2026-07-13T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "headlamp", "ui", "rbac", "migration"]
---

# Architectural Differences

**Kubernetes Dashboard**
* Runs strictly in-cluster.
* Authentication relies on long-lived ServiceAccount Bearer tokens.
* Scoped to a single cluster per deployment.
* UI-driven resource creation via forms.

**Headlamp**
* Runs locally (Desktop) or in-cluster.
* Adopts user identity via `kubeconfig` or OIDC, strictly enforcing existing Kubernetes RBAC.
* Natively aggregates and switches between multiple clusters.
* YAML-driven resource management, aligning with GitOps and CI/CD pipelines.

# Deployment Topologies

## Desktop Mode (Client-Side)
Executes entirely on the user's machine, consuming zero cluster compute or memory. It inherits the user's existing `kubeconfig` contexts.

```bash
# macOS
brew install --cask headlamp

# Linux
flatpak install flathub io.kinvolk.Headlamp

# Windows
winget install headlamp
```

## In-Cluster Mode (Shared Platform)
Deployed as a standard Kubernetes workload. Optimal for platform teams providing a shared URL. Requires an Ingress controller and an Identity Provider (IdP) for secure access.

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/
kubectl create namespace headlamp
helm install headlamp headlamp/headlamp --namespace headlamp
```

# Authentication & Access Control

Headlamp operates strictly as a Kubernetes client. It does not bypass API server authorization and will only render UI elements for actions the user is explicitly permitted to perform.

## Desktop Auth
Relies on the local `kubeconfig`. Validate baseline API access before launching:
```bash
kubectl config current-context
kubectl get nodes || kubectl get pods -n <target-namespace>
```

## In-Cluster Auth (OIDC)
Requires standard OIDC configuration (Issuer URL, Client ID, Secret). 
* **Callback URI:** `https://<headlamp-domain>/oidc-callback`
* **Failure Mode (Ingress):** Your Ingress controller *must* forward the `X-Forwarded-Proto` header. Without it, Headlamp will generate an `http://` callback URL, permanently breaking the OAuth2 redirect flow.

# Multi-Cluster Configuration

Headlamp aggregates multiple clusters by parsing composite `KUBECONFIG` paths.

```bash
# Unix/macOS/Linux
KUBECONFIG=~/.kube/dev-cluster:~/.kube/prod-cluster headlamp

# Windows
$env:KUBECONFIG="$HOME\.kube\dev-cluster;$HOME\.kube\prod-cluster"
```

# Workload Operations

Headlamp intentionally removes UI wizards for resource creation, favoring direct YAML application to match modern deployment standards. 

Generate scaffold YAML locally if necessary:
```bash
kubectl create deployment nginx --image=nginx --dry-run=client -o yaml > target.yaml
```

**Debugging Features**
* **Container Exec:** Provides embedded interactive terminal sessions (strictly bounded by `kubectl exec` RBAC policies).
* **Resource Metrics:** CPU and memory utilization graphs require `metrics-server` to be installed on the target cluster.
* **Map View:** Replaces standard lists with a visual dependency graph (Deployment → ReplicaSet → Pod → Service), reducing MTTR by exposing broken resource bindings at a glance.

# Legacy Dashboard Cleanup

After migrating, completely remove the legacy Dashboard to minimize attack surface.

```bash
helm uninstall kubernetes-dashboard -n kubernetes-dashboard
```

**Security Audit:** You must manually track down and delete any `ServiceAccount`, `RoleBinding`, or `ClusterRoleBinding` created exclusively for the old Dashboard. Leaving high-privilege, long-lived tokens in the cluster is a critical security risk.