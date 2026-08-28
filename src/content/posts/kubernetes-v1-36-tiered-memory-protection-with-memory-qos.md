---
title: "Kubernetes v1.36: Tiered Memory Protection with Memory QoS"
originalUrl: "https://kubernetes.io/blog/2026/04/29/kubernetes-v1-36-memory-qos-tiered-protection/"
publishDate: 2026-04-29T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "cgroups", "memory-management", "reliability"]
---

Kubernetes v1.36 updates Memory QoS with opt-in memory reservation, tiered protection by QoS class, and observability metrics. Memory QoS leverages the Linux cgroup v2 memory controller to manage container memory behavior under node pressure.

## Architectural Trade-offs: Hard vs. Soft Memory Protection

In earlier Kubernetes versions, enabling Memory QoS mapped all container memory requests to `memory.min`, enforcing a hard kernel reservation. This architecture proved risky: if a node with 8 GiB of RAM had 7 GiB requested by Burstable Pods, 7 GiB became un-reclaimable. Under severe memory pressure, this left insufficient headroom for the kernel or system daemons, increasing the likelihood of system-wide Out-Of-Memory (OOM) crashes.

v1.36 resolves this by separating throttling from reservation via the `memoryReservationPolicy` configuration. When configured with `TieredReservation`, Kubernetes maps protection levels based on the Pod's Quality of Service (QoS) class:

- **Guaranteed Pods (`memory.min`)**: Receive hard protection. The kernel will not reclaim this memory. If the guarantee cannot be honored, the kernel invokes the OOM killer on other processes to free pages.
- **Burstable Pods (`memory.low`)**: Receive soft protection. The kernel protects this memory under normal conditions but will reclaim it to prevent a system-wide OOM.
- **BestEffort Pods**: Receive no protection. Memory remains fully reclaimable.

### Cgroup v2 Interface Mapping

With `memoryReservationPolicy: TieredReservation`, Kubernetes resources map to cgroup v2 interfaces as follows:

| QoS Class | `memory.min` (Hard) | `memory.low` (Soft) | `memory.high` (Throttling) | `memory.max` (Limit) |
| :--- | :--- | :--- | :--- | :--- |
| **Guaranteed** | `requests.memory` | Not set | Not set | `limits.memory` |
| **Burstable** | Not set | `requests.memory` | Calculated via throttling factor | `limits.memory` (if set) |
| **BestEffort** | Not set | Not set | Calculated via node allocatable | Not set |

*Note on Hierarchy: cgroup v2 dictates that a parent cgroup's memory protection must equal or exceed the sum of its children's. The kubelet maintains this by setting `memory.min` on the root `kubepods` cgroup to the sum of all Guaranteed and Burstable requests, and `memory.low` on the Burstable cgroup to the sum of all Burstable requests.*

## Implementation and Configuration

### Prerequisites
- Kubernetes v1.36+
- Linux with cgroup v2 (`mount | grep cgroup2`)
- Container runtime supporting cgroup v2 (containerd 1.6+, CRI-O 1.22+)
- **Kernel Requirement**: Linux kernel 5.9+ is strongly recommended. Older kernels suffer from a known livelock bug triggered by `memory.high` throttling. The kubelet logs a warning on older kernels but does not block execution.

### Kubelet Configuration

Enable Memory QoS and opt into tiered protection via the `KubeletConfiguration`. By default, `memoryReservationPolicy` is `None`, which enables `memory.high` throttling (based on `memoryThrottlingFactor`) but writes no reservation values to `memory.min` or `memory.low`.

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
featureGates:
  MemoryQoS: true
memoryReservationPolicy: TieredReservation # Defaults to None
memoryThrottlingFactor: 0.9 # Default is 0.9
```

### Verification

You can inspect the cgroup v2 filesystem directly to verify protections are applied. 

For a Guaranteed Pod requesting 512 MiB:
```bash
$ cat /sys/fs/cgroup/kubepods.slice/kubepods-pod6a4f2e3b_1c9d_4a5e_8f7b_2d3e4f5a6b7c.slice/memory.min
536870912
```

For a Burstable Pod requesting 512 MiB:
```bash
$ cat /sys/fs/cgroup/kubepods.slice/kubepods-burstable.slice/kubepods-burstable-pod8b3c7d2e_4f5a_6b7c_9d1e_3f4a5b6c7d8e.slice/memory.low
536870912
```

## Observability

v1.36 introduces two alpha metrics on the kubelet `/metrics` endpoint to monitor hard and soft reservations. Tracking `kubelet_memory_qos_node_memory_min_bytes` against physical node memory is critical for capacity planning and identifying hard reservation limits that threaten node stability.

```bash
$ curl -sk https://localhost:10250/metrics | grep memory_qos
# HELP kubelet_memory_qos_node_memory_min_bytes [ALPHA] Total memory.min in bytes for Guaranteed pods
kubelet_memory_qos_node_memory_min_bytes 5.36870912e+08
# HELP kubelet_memory_qos_node_memory_low_bytes [ALPHA] Total memory.low in bytes for Burstable pods
kubelet_memory_qos_node_memory_low_bytes 2.147483648e+09