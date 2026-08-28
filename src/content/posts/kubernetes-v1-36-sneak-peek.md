---
title: "Kubernetes v1.36 Sneak Peek"
originalUrl: "https://kubernetes.io/blog/2026/03/30/kubernetes-v1-36-sneak-peek/"
publishDate: 2026-03-30T00:00:00+00:00
source: "kubernetes"
tags: ["kubernetes", "networking", "storage", "security", "scheduling"]
---

# Kubernetes v1.36 Architecture & Implementation Guide
**Target Release Date:** April 22, 2026

## Critical Deprecations & Removals

### 1. `service.spec.externalIPs` Deprecation (KEP-5707)
The `externalIPs` field in `Service` resources is officially deprecated. Usage will generate warnings in v1.36, with full removal slated for v1.43.

**Why it matters:** This field represents a fundamental security flaw that enables Man-in-the-Middle (MITM) attacks against cluster traffic (CVE-2020-8554). By claiming an arbitrary IP, malicious tenants can hijack traffic destined for external endpoints.

**Implementation / Migration:** 
Shift to Gateway API for advanced routing, or standard LoadBalancer/NodePort configurations.

```yaml
# ❌ VULNERABLE PATTERN (DEPRECATED)
apiVersion: v1
kind: Service
spec:
  externalIPs:
    - 198.51.100.32 # Susceptible to MITM interception

# ✅ PREFERRED PATTERN (Gateway API)
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
spec:
  parentRefs:
  - name: cluster-edge-gateway
  rules:
  - backendRefs:
    - name: secure-backend-service
      port: 8080
```

### 2. `gitRepo` Volume Plugin Permanent Removal (KEP-5040)
The `gitRepo` volume driver is permanently disabled and cannot be re-enabled.

**Why it matters:** The plugin design permitted an attacker to execute arbitrary code as `root` on the underlying Kubernetes node.

**Implementation / Migration:**
Replace `gitRepo` volumes with an `initContainer` that clones the repository into an `emptyDir` before the main application starts.

```yaml
# ✅ PREFERRED PATTERN (Init Container Git Sync)
apiVersion: v1
kind: Pod
spec:
  initContainers:
  - name: git-sync
    image: alpine/git
    command: ["git", "clone", "https://github.com/org/repo.git", "/workspace"]
    volumeMounts:
    - name: shared-data
      mountPath: /workspace
  containers:
  - name: application
    image: my-app:latest
    volumeMounts:
    - name: shared-data
      mountPath: /workspace
  volumes:
  - name: shared-data
    emptyDir: {}
```

### 3. Ingress NGINX Retirement
The `ingress-nginx` controller was formally retired on March 24, 2026. 
* **Impact:** Zero future releases, bug fixes, or CVE patches. Artifacts remain available but running them constitutes a growing security liability.
* **Action:** Audit clusters and migrate to actively maintained Gateway API controllers or alternative Ingress implementations.

---

## Core Enhancements

### 1. Faster SELinux Volume Labeling (GA) (KEP-1710)
Replaces expensive recursive file relabeling with the `mount -o context=XYZ` option, applying SELinux labels to the entire volume instantaneously at mount time.

**Why it matters:** Eliminates catastrophic Pod startup latency on SELinux-enforcing nodes when mounting volumes containing large numbers of files.

**Failure Modes & Trade-offs:** 
Applying a single SELinux context at the mount level introduces breaking changes if you mix privileged and unprivileged Pods sharing the same volume. Pod authors are strictly responsible for managing these overlaps. If conflicts occur, you must explicitly opt-out and revert to recursive relabeling.

```yaml
apiVersion: v1
kind: Pod
spec:
  securityContext:
    # Explicitly fall back to legacy recursive relabeling if 
    # mount-time labeling breaks shared volume access across varied Pod privilege levels
    seLinuxChangePolicy: "Recursive" 
```

### 2. External Signing of ServiceAccount Tokens (GA expected) (KEP-740)
Delegates ServiceAccount token signing from the internal `kube-apiserver` to external Key Management Systems (KMS) or Hardware Security Modules (HSM).

**Why it matters:** Removes the operational burden of managing and rotating internal signing keys, satisfying strict compliance mandates that require cryptographic materials to never leave a hardware boundary.

```text
+-------------------+ (Token Request) +-------------------------+
|                   |---------------->|                         |
|  kube-apiserver   |                 |    External KMS / HSM   |
|                   |<----------------|                         |
+-------------------+ (Signed JWT)    +-------------------------+
```

### 3. DRA: Device Taints and Tolerations (Beta) (KEP-5055)
Dynamic Resource Allocation (DRA) drivers can now taint specialized physical devices, operating identically to Node taints but scoped to hardware. Administrators can also define `DeviceTaintRule` policies to taint devices in bulk by driver or criteria.

**Why it matters:** Prevents generic workloads from accidentally consuming scarce, high-value accelerators (like top-tier GPUs) during scheduling.

```yaml
# Pod must explicitly tolerate the DRA device taint to be scheduled onto it
apiVersion: v1
kind: Pod
spec:
  tolerations:
  - key: "dra.example.com/h100-gpu"
    operator: "Exists"
    effect: "NoSchedule"
```

### 4. DRA: Partitionable Devices (KEP-4815)
Introduces the ability to split a single physical hardware accelerator into multiple logical units managed by DRA.

**Why it matters:** Radically improves infrastructure ROI. Instead of dedicating an entire GPU to a single Pod (often leading to massive underutilization), platform teams can slice the device, preserving strict isolation while multiplexing workloads.

```text
+-------------------------------------------------------------+
| Physical DRA Device (e.g., GPU 80GB)                        |
|                                                             |
| +-----------------------+         +-----------------------+ |
| | Logical Partition A   |         | Logical Partition B   | |
| | (20GB VRAM Allocated) |         | (60GB VRAM Allocated) | |
| | Bound to Pod: Web-LLM |         | Bound to Pod: Train-Job |
| +-----------------------+         +-----------------------+ |
+-------------------------------------------------------------+