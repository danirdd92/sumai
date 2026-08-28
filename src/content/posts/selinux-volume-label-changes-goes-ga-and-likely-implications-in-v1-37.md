---
title: "SELinux Volume Label Changes goes GA (and likely implications in v1.37)"
originalUrl: "https://kubernetes.io/blog/2026/04/22/breaking-changes-in-selinux-volume-labeling/"
publishDate: 2026-04-22T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "selinux", "storage", "security"]
---

## Overview

Kubernetes is changing how SELinux labels are applied to volumes. In Kubernetes v1.37, the `SELinuxMount` feature gate will default to true. This shifts the responsibility of labeling from the Container Runtime Interface (CRI) recursive relabeling (O(N) time complexity) to the Kubelet using kernel-level mount options (O(1) time complexity). 

While this drastically reduces volume setup time for large filesystems, it introduces breaking changes for workloads sharing volumes across different security contexts.

## Architectural Shift

Historically, Kubernetes passed the SELinux label to the CRI, which executed a recursive `chcon`-equivalent operation across all files in the volume. 

With `SELinuxMount`, Kubelet directly mounts the volume using `-o context=<label>`. The kernel instantly applies the context to all inodes on the mount.

```text
Legacy Behavior (O(N))                   Target Behavior (O(1))
+---------------+                        +---------------+
| Kubelet       |                        | Kubelet       |
+-------+-------+                        +-------+-------+
        | (passes label)                         | mount -o context=... 
+-------v-------+                        +-------v-------+
| CRI           |                        | Linux Kernel  |
+-------+-------+                        +-------+-------+
        | chcon -R /vol                          | (Instant inode labeling)
        v                                        v
[File 1, File 2, ... File N]             [Volume Mountpoint]
```

### Requirements for Mount-Time Labeling

For Kubernetes to utilize the O(1) mount option, **all** following conditions must be met:

1. **OS Support:** SELinux must be enabled.
2. **Explicit SELinux Level:** The Pod (or all containers) must define `seLinuxOptions.level`. Without this, the CRI assigns a random level post-mount and falls back to recursive relabeling to prevent container boundary escapes.
3. **CSI Driver Support:** The volume plugin or CSI driver must declare support via the `seLinuxMount: true` field in its `CSIDriver` object. (In-tree `fc` and `iscsi` are supported).
4. **Compatible Access Modes / Policies:** The PVC must use `ReadWriteOncePod`, or `seLinuxChangePolicy` must not be explicitly set to `Recursive`.

```yaml
# Example: Pod properly configured for O(1) mount labeling
apiVersion: v1
kind: Pod
metadata:
  name: fast-mount-pod
spec:
  securityContext:
    seLinuxOptions:
      level: "s0:c123,c456" # Required: Prevents CRI random generation/fallback
    seLinuxChangePolicy: MountOption # Available when SELinuxMount is enabled
  containers:
  - name: app
    image: my-app:latest
```

## Breaking Changes & Failure Modes

The `SELinuxMount` implementation enforces strict mount-level context. This breaks workloads relying on inode-level contextual variations within a single volume.

**Unsupported Architectures:**
1. Two Pods with different SELinux labels sharing the same volume via different `subPath` mounts.
2. A privileged Pod and an unprivileged Pod sharing the same volume.

**Failure Mode:** If two incompatible Pods attempt to mount the same volume, one Pod will successfully mount, and the subsequent Pod will deadlock in the `ContainerCreating` state until the first Pod terminates.

## Remediation & Opt-Out

You can selectively opt out of the O(1) mount behavior and force legacy CRI recursive relabeling using the new `seLinuxChangePolicy` field in the Pod API.

```yaml
# Example: Opting out to allow privileged/unprivileged sharing
apiVersion: v1
kind: Pod
metadata:
  name: legacy-shared-volume-pod
spec:
  securityContext:
    # Forces legacy O(N) recursive labeling, bypassing SELinuxMount logic
    seLinuxChangePolicy: Recursive 
  containers:
  - name: app
    image: my-app:latest
```

*Note: You can enforce this opt-out globally for legacy namespaces using a `MutatingAdmissionPolicy`, Kyverno, or Gatekeeper.*

## Migration Path & Observability

Kubernetes v1.36 ships with observability primitives to identify architectural conflicts before the v1.37 default change.

### 1. Enable the Warning Controller
Enable the `selinux-warning-controller` on the control plane. This controller continuously evaluates the scheduler state for potential volume/label conflicts, even if the Pods are not currently scheduled to the same node.

```bash
kube-controller-manager --controllers=*,selinux-warning-controller
```

### 2. Audit Metrics
Audit the following Prometheus metrics to identify required architectural changes or necessary opt-outs.

```promql
# Metric 1: Emitted by selinux-warning-controller (Control Plane)
# Identifies potential conflicts cluster-wide.
# WARNING: This metric exposes Pod and Namespace names, creating a potential 
# data leakage vector across namespace boundaries. Restrict access.
selinux_warning_controller_selinux_volume_conflict

# Metric 2: Emitted by Kubelet (Node)
# Identifies Pods that are currently running but will fail to start in v1.37.
# Drawback: Does not expose Pod names as labels (correlate with Metric 1).
volume_manager_selinux_volume_context_mismatch_warnings_total
```

Once `SELinuxMount` is enabled in v1.37, actual runtime deadlocks will be surfaced via the `volume_manager_selinux_volume_context_mismatch_errors_total` metric on the Kubelet.