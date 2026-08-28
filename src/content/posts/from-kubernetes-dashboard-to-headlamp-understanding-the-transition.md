---
title: "From Kubernetes Dashboard to Headlamp: Understanding the Transition"
originalUrl: "https://kubernetes.io/blog/2026/06/01/dashboard-to-headlamp/"
publishDate: 2026-06-01T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "headlamp", "architecture", "rbac", "gitops"]
---

# Archiving Kubernetes Dashboard: The Transition to Headlamp

With the deprecation and archiving of Kubernetes Dashboard, Headlamp has emerged as the de facto replacement. While Dashboard provided a functional 1:1 graphical interface for cluster resources, Headlamp addresses modern operational requirements: multi-cluster fleet management, GitOps integration, and logical application grouping.

## Architectural Enhancements

### 1. Multi-Cluster Fleet Visibility
Dashboard’s architecture limited it to single-cluster introspection. Headlamp abstracts the cluster context, aggregating multiple environments (e.g., dev, staging, prod) into a unified control plane UI. This eliminates context-switching friction for operators managing fleet-wide workloads.

### 2. Application-Centric "Projects"
Raw resource lists (Pods, Deployments, Services) lack application context. Headlamp’s **Projects** feature provides a logical grouping mechanism built on native primitives (namespaces and labels) to map disparate resources to cohesive applications. 

### 3. Extensible Plugin Architecture
Headlamp supports a modular plugin ecosystem for injecting third-party or proprietary workflows directly into the UI.
*   **GitOps Parity:** Plugins for tools like Flux visualize application state alongside the underlying Kubernetes resources, bridging the gap between Git commits and cluster state.
*   **Platform Engineering:** Platform teams can build custom plugins to expose Internal Developer Platform (IDP) tooling, centralizing the developer experience.

## Deployment Topologies & Trade-offs

Headlamp supports two distinct deployment models, which can be utilized independently or in tandem.

### Model A: In-Cluster (Centrally Managed)
Deployed via Helm, operating as a standard cluster workload behind an Ingress controller.

*   **Optimal for:** Shared team environments, production debugging, and enforcing centralized authentication (OIDC).
*   **Drawbacks & Failure Modes:** Requires maintaining Ingress, TLS, and OIDC integrations. If the cluster control plane or Ingress controller degrades, UI access is severed, requiring CLI break-glass procedures. Poorly configured OIDC session timeouts can lead to dropped UI states during active troubleshooting.

**Production-Ready Helm Configuration (OIDC Enabled):**
```yaml
# headlamp-values.yaml
ingress:
  enabled: true
  ingressClassName: nginx
  hosts:
    - host: headlamp.ops.internal
      paths:
        - path: /
          type: ImplementationSpecific
  tls:
    - secretName: headlamp-tls
      hosts:
        - headlamp.ops.internal
config:
  oidc:
    clientID: "headlamp-client"
    clientSecret: "${OIDC_CLIENT_SECRET}" # Should be injected via External Secrets Operator
    issuerURL: "https://dex.ops.internal"
    scopes: "openid,profile,email,groups"
```

### Model B: Desktop Application (Client-Side)
An Electron-based local client that relies on the operator's local `~/.kube/config`.

*   **Optimal for:** Local development (minikube, kind), rapid onboarding, or break-glass operations when cluster Ingress is unreachable.
*   **Drawbacks & Failure Modes:** Susceptible to `kubeconfig` sprawl. Without strict RBAC or visual environment indicators, operators risk executing destructive commands against the wrong cluster context. Furthermore, client-side execution bypasses centralized UI auditing mechanisms.

## Migration and Access Control (RBAC)

Headlamp does not reinvent Kubernetes access control; it strictly enforces existing RBAC policies. If an operator possesses permissions to scale a Deployment via `kubectl` or Dashboard, that identical matrix applies in Headlamp.

**Migration Checklist:**
1.  **RBAC Audit:** Verify existing `ClusterRoleBindings` and `RoleBindings`. Headlamp relies on standard Kubernetes authentication, meaning existing ServiceAccount tokens or OIDC identities map directly without modification.
2.  **Topology Selection:** Standardize on In-Cluster deployments for production visibility and Desktop clients for local development.
3.  **Plugin Toolchain Evaluation:** Identify required plugins (e.g., Flux) to ensure feature parity with any existing internal dashboards before fully decommissioning Dashboard instances.