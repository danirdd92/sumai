---
title: "Kubernetes v1.36: Fine-Grained Kubelet API Authorization Graduates to GA"
originalUrl: "https://kubernetes.io/blog/2026/04/24/kubernetes-v1-36-fine-grained-kubelet-authorization-ga/"
publishDate: 2026-04-24T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "security", "rbac", "kubelet"]
---

### Overview
In Kubernetes v1.36, the `KubeletFineGrainedAuthz` feature gate is generally available (GA) and locked to enabled. This release deprecates the reliance on the coarse-grained `nodes/proxy` RBAC permission, introducing specific subresources for the Kubelet HTTPS API. This enables strict least-privilege access controls for node-level observability and monitoring agents.

### The Architectural Flaw: `nodes/proxy GET` WebSocket RCE
Historically, granting read-only `nodes/proxy GET` to monitoring tools introduced a critical Remote Code Execution (RCE) vulnerability stemming from how the Kubelet handles WebSocket connections.

The WebSocket protocol (RFC 6455) requires an HTTP `GET` request for the initial connection handshake. Previously, the Kubelet mapped this handshake to the RBAC `get` verb and authorized the request without verifying if the client also possessed `CREATE` permissions for subsequent write operations. This mismatch allowed attackers with basic read access to bypass intended restrictions and execute arbitrary commands in any pod on the node via the `/exec` endpoint.

```bash
# Exploiting the WebSocket mismatch using websocat against the /exec endpoint
websocat --insecure \
  --header "Authorization: Bearer $TOKEN" \
  --protocol v4.channel.k8s.io \
  "wss://$NODE_IP:10250/exec/default/nginx/nginx?output=1&error=1&command=id"

# Output: uid=0(root) gid=0(root) groups=0(root)
```

### Implementation: Fine-Grained Subresources
The Kubelet now maps discrete API paths to dedicated subresources rather than grouping them under a single proxy capability:

*   `/stats/*` → `nodes/stats`
*   `/metrics/*` → `nodes/metrics`
*   `/logs/*` → `nodes/log`
*   `/spec/*` → `nodes/spec`
*   `/checkpoint/*` → `nodes/checkpoint`

To ensure backward compatibility without breaking existing clusters, endpoints such as `/pods`, `/runningPods/`, `/healthz`, and `/configz` implement a **dual-check authorization model**. The Kubelet first evaluates a `SubjectAccessReview` for the specific subresource (e.g., `nodes/pods`). If that check is denied, it gracefully falls back to checking for the legacy `nodes/proxy` permission. Any unmapped paths default to `nodes/proxy`.

### Configuration Example: Least-Privilege Monitoring
Monitoring agents scraping metrics no longer require node-level superuser capabilities. RBAC policies should be updated to target only the required data streams.

**Legacy Anti-Pattern (Overly Broad)**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: monitoring-agent
rules:
- apiGroups: [""]
  resources: ["nodes/proxy"] # Grants potential RCE capabilities
  verbs: ["get"]
```

**Modern Implementation (Least Privilege)**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: monitoring-agent
rules:
- apiGroups: [""]
  resources: ["nodes/metrics", "nodes/stats"] # Scoped strictly to observability
  verbs: ["get"]
```

### Operational & Upgrade Considerations
*   **Zero-Downtime Upgrades:** The dual-check fallback mechanism ensures that legacy workloads relying on `nodes/proxy` continue to function without immediate modification.
*   **System Roles:** The built-in `system:kubelet-api-admin` ClusterRole is automatically updated by the control plane to include all new fine-grained subresources. `kube-apiserver` to `kubelet` communication remains uninterrupted.
*   **Mixed-Version Clusters:** In environments with mismatched API server and Kubelet versions, authorization safely degrades to the `nodes/proxy` fallback logic.

### Verification
You can verify the feature state by querying the Kubelet metrics endpoint. The client making the request must have an RBAC binding granting `get` on `nodes/metrics`.

```bash
# Assuming $TOKEN belongs to a ServiceAccount with nodes/metrics access
curl -sk \
  --header "Authorization: Bearer $TOKEN" \
  https://$NODE_IP:10250/metrics | grep KubeletFineGrainedAuthz

# Expected Output:
# kubernetes_feature_enabled{name="KubeletFineGrainedAuthz",stage="GA"} 1