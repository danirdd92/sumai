---
title: "Kubernetes v1.36: User Namespaces in Kubernetes are finally GA"
originalUrl: "https://kubernetes.io/blog/2026/04/23/kubernetes-v1-36-userns-ga/"
publishDate: 2026-04-23T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "security", "linux-kernel", "containers"]
---

# Kubernetes v1.36: User Namespaces (GA)

User namespaces (userns) provide Linux kernel-level isolation by mapping user and group IDs inside a container to a different, unprivileged range of IDs on the host. This mitigates container breakout vulnerabilities: a process running as `root` (UID 0) inside the container operates as an unprivileged user on the host node, preventing administrative access if the container boundary is breached.

With Kubernetes v1.36, user namespaces are Generally Available (GA).

## Architectural Mechanics

### ID-Mapped Mounts

Historically, mapping containers to an unprivileged UID range on the host required the Kubelet to recursively `chown` attached volumes so the container process could read or write to them. This `O(N)` disk operation caused severe startup latency for large data volumes.

Kubernetes user namespaces bypass this using **ID-mapped mounts** (introduced in Linux 5.12). The kernel transparently translates UIDs and GIDs at mount time rather than rewriting file ownership on the underlying disk. 

- **Container view:** Files appear owned by the container's UID (e.g., UID 0).
- **Host disk view:** File ownership remains entirely unchanged.
- **Performance:** `O(1)` mount-time operation; zero startup penalty.

### Confined Capabilities

When user namespaces are active, Linux capabilities are also namespaced. For example, granting `CAP_NET_ADMIN` to a pod grants administrative control over the container's isolated network stack, without exposing or affecting the host's network interfaces. This enables patterns previously requiring fully privileged containers (such as running VPN clients, routing daemons, or traffic shaping) to operate safely in a confined boundary.

## Implementation

To enable user namespaces, explicitly opt out of the host user namespace by setting `hostUsers: false` in the Pod or PodTemplate spec. Existing container images do not require modification.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: isolated-workload
spec:
  # Instructs the Kubelet to map this pod to an unprivileged user namespace
  hostUsers: false
  containers:
    - name: app
      image: fedora:42
      securityContext:
        # The process acts as root inside the container, 
        # but is mapped to an unprivileged UID on the host node.
        runAsUser: 0
```

## Trade-offs and Constraints

- **Filesystem Support:** ID-mapped mounts require underlying filesystem support in the kernel. While modern filesystems (ext4, xfs, btrfs, overlayfs) support this, unsupported or legacy filesystems will fail to mount correctly.
- **Linux Dependency:** This feature is strictly bound to Linux nodes and requires kernel 5.12 or newer.
- **Runtime Configuration:** The underlying container runtime (containerd or CRI-O) must be properly configured by the cluster administrator to handle UID/GID pool allocations for user namespace remapping.