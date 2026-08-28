---
title: "Securing Production Debugging in Kubernetes"
originalUrl: "https://kubernetes.io/blog/2026/03/18/securing-production-debugging-in-kubernetes/"
publishDate: 2026-03-18T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "security", "rbac", "authentication", "operations"]
---

# Architecture Overview

Relying on broad access methods (`cluster-admin`, shared bastions, long-lived SSH keys) for production debugging compromises audit trails and permanently violates least-privilege principles. A production-ready architecture replaces static access with a **Just-In-Time (JIT) Access Gateway**. 

The implementation requires three components:
1. **Kubernetes RBAC** to define API-level access scopes.
2. **Short-lived, identity-bound credentials** tied to hardware-backed keys.
3. **An Access Broker/Gateway** to enforce granular constraints that RBAC cannot natively handle (e.g., restricting specific commands executed inside a container).

## 1. Access Broker & RBAC Design

Kubernetes RBAC is the authorization source of truth, but it cannot restrict specific commands run inside an `exec` session. An access broker sits in front of the cluster to enforce command-level policies, manage approval workflows, and restrict actions to specific pods or nodes. 

*(Note: Kubernetes also supports `ValidatingAdmissionPolicy` for write restrictions and webhook authorization for custom verb handling to supplement RBAC).*

**Implementation Rules:**
- **Group-based binding:** Never grant RBAC roles to individual users. Bind exclusively to groups managed by an identity provider.
- **Policy-as-Code:** Maintain broker policies (e.g., auto-approval logic, allowed interactive commands) in version control and apply them via standard CI/CD pipelines.

### Example: Namespace-Scoped On-Call Role
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: oncall-debug
  namespace: <namespace>
rules:
  # Discover what’s running
  - apiGroups: [""]
    resources: ["pods", "events"]
    verbs: ["get", "list", "watch"]
  # Read logs
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  # Interactive debugging actions
  - apiGroups: [""]
    resources: ["pods/exec", "pods/portforward"]
    verbs: ["create"]
  # Understand rollout/controller state
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
  # Optional: allow kubectl debug ephemeral containers
  - apiGroups: [""]
    resources: ["pods/ephemeralcontainers"]
    verbs: ["update"] 
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: oncall-debug
  namespace: <namespace>
subjects:
  - kind: Group
    name: oncall-<team-name>
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: oncall-debug
  apiGroup: rbac.authorization.k8s.io
```

## 2. Short-Lived, Identity-Bound Credentials

Credentials must cryptographically tie a session to a specific human and expire automatically. Private keys should be generated and stored in non-exportable hardware (e.g., YubiKey/PIV tokens).

### Option A: OIDC Tokens via Credential Helper
Use `kubeconfig` credential helpers to enforce a strict Time-To-Live (TTL) on authentication tokens.

```yaml
users:
- name: oncall
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1
      command: cred-helper
      args: ["--cluster=prod", "--ttl=30m"]
```

### Option B: Short-Lived X.509 Client Certificates
Leverage the Kubernetes `CertificateSigningRequest` (CSR) API to issue scoped, temporary certificates.

1. **Generate Key and CSR (ideally within the hardware token):**
```bash
openssl genpkey -algorithm Ed25519 -out oncall.key
openssl req -new -key oncall.key -out oncall.csr \
    -subj "/CN=user/O=oncall-payments"
```

2. **Submit CSR with strict expiration:**
```yaml
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata:
  name: oncall-<user>-20260218
spec:
  request: <base64-encoded oncall.csr>
  signerName: kubernetes.io/kube-apiserver-client
  expirationSeconds: 1800  # 30 minutes
  usages:
    - client auth
```
*Security Requirement:* The Certificate Authority (CA) signing these requests must be rotated regularly (e.g., quarterly) to mitigate long-term compromise risk.

## 3. Just-In-Time (JIT) Access Gateway Execution

The JIT gateway (typically an on-demand pod) acts as an execution proxy. It requires engineers to authenticate using a short-lived OpenSSH user certificate (distinct from Kubernetes X.509 client certificates). It enforces session scope (restricting access to specific clusters, namespaces, or nodes) before proxying API calls, ensuring the session cannot be hijacked or reused outside the approved scope.

### Example: Cluster-Scoped Read Binding
Cluster-level bindings bypass namespace boundaries and should be used strictly for workflows requiring global visibility (e.g., reading nodes).

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: jit-cluster-read
rules:
  - apiGroups: [""]
    resources: ["nodes", "namespaces"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: jit-cluster-read
subjects:
  - kind: Group
    name: jit:oncall:cluster
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: jit-cluster-read
  apiGroup: rbac.authorization.k8s.io
```

## Architectural Trade-Offs & Failure Modes

- **RBAC Command Blindness:** Kubernetes RBAC natively permits `pods/exec` but cannot inspect or constrain the command executed inside the container. An external broker/gateway is strictly required if granular execution control is necessary.
- **Operational Complexity:** Implementing hardware-backed keys, dynamic gateway pods, short-lived certificate issuance, and routine CA rotation introduces significant infrastructure overhead and potential points of failure during active incidents.
- **Mediation Layer Latency:** Highly secure environments may deploy an additional ephemeral session mediation layer to separate session setup from privileged action execution. Both layers produce independent audit trails, but this architecture significantly increases connection latency and configuration complexity.