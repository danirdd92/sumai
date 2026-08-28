---
title: "Kubernetes v1.36: ハル (Haru)"
originalUrl: "https://kubernetes.io/blog/2026/04/22/kubernetes-v1-36-release/"
publishDate: 2026-04-22T00:00:00+00:00
source: "kubernetes"
tags: ["kubernetes", "architecture", "security", "scheduling", "storage"]
---

Kubernetes v1.36 introduces 70 enhancements (18 Stable, 25 Beta, 25 Alpha), focusing heavily on API extensibility without webhooks, granular hardware resource scheduling, and hardened identity isolation. 

## API & Control Plane Architecture

### Mutating Admission Policies (Stable)
`MutatingAdmissionPolicies` native to the API server via Common Expression Language (CEL) is now GA. This eliminates the network latency, operational overhead, and failure domains associated with external mutating webhooks. 

**Trade-offs:** CEL execution is strictly time-bounded. Highly complex mutations requiring external lookups or heavy computation still require traditional external webhooks.

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: MutatingAdmissionPolicy
metadata:
  name: force-pull-policy
spec:
  matchConstraints:
    resourceRules:
    - apiGroups: [""]
      resources: ["pods"]
      operations: ["CREATE"]
  mutations:
  - patchType: ApplyConfiguration
    applyConfiguration:
      expression: |
        Object{ spec: Object{ containers: [Object{ name: object.spec.containers[0].name, imagePullPolicy: "Always" }] } }
```

### Declarative Validation via `validation-gen` (Stable)
API development moves away from manual OpenAPI schemas. Complex validation logic can now be declared directly in Go struct tags using CEL, allowing the `validation-gen` tool to automatically generate robust API validation code at compile-time.

```go
// +k8s:minimum=1
// +k8s:maximum=100
// +k8s:enum=Fast,Standard,Slow
Priority string `json:"priority"`
```

### Component Observability: `/statusz` & `/flagz` (Beta)
Control-plane components and node agents now expose standard `/statusz` (uptime, Go/binary versions) and `/flagz` (effective CLI flags). They support content negotiation for programmatic access.

```bash
# Query API server effective flags programmatically
curl -sk -H "Accept: application/json" https://localhost:6443/flagz | jq '.flags'
```

---

## Security & Identity

### External ServiceAccount Token Signer (Stable)
Control planes can now offload SA token signing to external identity or Key Management Systems (KMS). The API server caches public keys from the external signer and validates JWTs it did not sign itself. 

**Why it matters:** Centralizes identity management and prevents key-sprawl directly inside the control plane.
**Failure mode:** If the external signer suffers an outage, new pods cannot obtain valid tokens. Strict key rotation synchronization is required to avoid degrading cluster authentication.

```yaml
# kube-apiserver configuration
--service-account-issuer=https://oidc.example.com
--service-account-jwks-uri=https://oidc.example.com/.well-known/jwks.json
```

### User Namespaces (Stable)
Container root users can now be mapped to non-privileged host users, providing kernel-level defense-in-depth against container breakout exploits.

**Trade-offs:** Requires support from the underlying container runtime (e.g., containerd/CRI-O) and host OS kernel. Volume ownership and file permissions must be strictly aligned with the UID/GID mapping logic.

```yaml
apiVersion: v1
kind: Pod
spec:
  hostUsers: false # Enables User Namespace isolation
  containers:
  - name: app
    image: my-app
```

### Fine-Grained Kubelet API Authorization (Stable)
The overly broad `nodes/proxy` RBAC permission is replaced with precise, least-privilege resource scoping for the kubelet HTTPS API. This is ideal for restricting observability tools solely to required endpoints.

```yaml
rules:
- apiGroups: [""]
  resources: ["nodes/metrics", "nodes/stats"] # Scoped access instead of full proxy
  verbs: ["get"]
```

### Constrained Impersonation (Beta)
Impersonation now follows least-privilege. An impersonator requires both the permission to impersonate an identity *and* the RBAC permissions for the underlying action being performed on that identity's behalf.

---

## Scheduling & Workload Management

### Workload Aware Scheduling (Alpha)
Addresses resource fragmentation in batch/HPC workloads by evaluating grouped Pods atomically. This integrates a native, decoupled `PodGroup` API where all pods bind together simultaneously, or none do.

```yaml
apiVersion: scheduling.x-k8s.io/v1alpha1
kind: PodGroup
metadata:
  name: distributed-training
spec:
  minMember: 16
  scheduleTimeoutSeconds: 300
```

### Dynamic Resource Allocation (DRA) Advancements (Stable/Beta)
DRA admin access and prioritized lists are now Stable. Features for partitionable devices, consumable capacity, and device taints/tolerations reach Beta. This formalizes a scalable, production-ready replacement for legacy device plugins, essential for multi-tenant GPU sharing.

### Mutable Container Resources for Suspended Jobs (Beta)
Queue controllers can now dynamically adjust CPU/Memory/GPU requests of a `Job` while it is suspended, adapting workloads to real-time cluster availability or quota limits before unsuspending them.

---

## Storage & Node Operations

### OCI Artifact Volume Source (Stable)
The kubelet can now pull and mount content directly from OCI-compliant registries without requiring ConfigMaps, init containers, or specialized storage backends.

**Trade-offs:** Volumes are strictly read-only. Pulling large models or datasets will heavily consume the node's local disk/image cache and may significantly delay pod startup if not pre-fetched.

```yaml
volumes:
- name: static-assets
  oci:
    repository: registry.example.com/assets/frontend
    tag: v1.4.2
```

### Volume Group Snapshots (Stable)
Enables crash-consistent snapshots across multiple `PersistentVolumeClaims` simultaneously. This is critical for distributed databases or stateful applications requiring synchronized state capture across multiple disks.

### PSI based on cgroupv2 (Stable)
Kubelet now exports Pressure Stall Information (PSI) metrics for CPU, memory, and I/O. 

**Why it matters:** Traditional utilization metrics only indicate a system is busy. PSI differentiates between high utilization and actual resource stalling (thrashing), driving much more accurate horizontal/vertical autoscaling decisions and noisy-neighbor detection.