---
title: "Spotlight on WG Device Management"
originalUrl: "https://kubernetes.io/blog/2026/06/24/wg-device-management-spotlight-2026/"
publishDate: 2026-06-24T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scheduling", "hardware", "dra"]
---

# Dynamic Resource Allocation (DRA) Architecture

The legacy Kubernetes Device Plugin API models hardware as opaque integers (e.g., `nvidia.com/gpu: 2`), a pattern that fails for workloads requiring specific interconnect topologies, memory capacities, or dynamic partitioning. To solve this, the Device Management Working Group introduced Dynamic Resource Allocation (DRA) (GA in Kubernetes 1.34).

DRA shifts Kubernetes from primitive device counting to a structured, requirements-driven scheduling framework, splitting device management into four distinct phases:

```text
+-------------------+       +-------------------+       +-------------------+
|  Hardware Vendor  |       |   User/Workload   |       |   K8s Scheduler   |
+-------------------+       +-------------------+       +-------------------+
          |                           |                           |
          v                           v                           |
  1. Modeling                 2. Requesting                       |
[ ResourceSlice ]           [ ResourceClaim ]                     |
(Exposes hardware)          (Defines hardware)                    |
(capacity/topology)         (requirements)                        |
          |                           |                           |
          +----------+----------------+                           |
                     |                                            v
                     |                                     3. Scheduling
                     +-----------------------------------> [ Match & Bind ]
                                                                  |
                                                                  v
                                                           4. Actuation
                                                           [ DRA Driver ]
                                                         (Configures device)
```

## Advanced Device Sharing Semantics

To improve hardware utilization, DRA introduces specialized paradigms for device sharing:

1. **User-Mediated Sharing (Explicit Sharing)**
Multiple containers—either within the same Pod or across different Pods—reference a single `ResourceClaim`. The scheduler maps these containers to the same physical hardware, relying on the device's native multiplexing capabilities to handle concurrency.

2. **Platform-Mediated Sharing (Consumable Capacity)**
Pods define independent `ResourceClaim`s requesting fractional units of a device (e.g., requesting 2 Gbps of network bandwidth). The scheduler deducts these fractional requests from a unified device capacity (e.g., a 40 Gbps NIC). The node-level DRA driver then dynamically partitions the hardware, such as creating isolated SR-IOV sub-interfaces for each Pod.

3. **Overlapping Partitions**
Vendors can model hardware with dynamic segmentation (e.g., NVIDIA MIG). The scheduler selects a specific hardware partition to satisfy a workload, automatically marking any physically overlapping partitions as unavailable to prevent resource contention.

## Implementation Example: Flexible Resource Claims

To decouple workload requirements from cluster topology, `ResourceClaim` leverages CEL (Common Expression Language) for dynamic constraints. This allows workloads to define explicit requirements and prioritized fallback configurations.

```yaml
apiVersion: resource.k8s.io/v1
kind: ResourceClaimTemplate
metadata:
  name: flexible-gpu-claim
spec:
  spec:
    devices:
      requests:
        - name: primary-preference
          deviceClassName: gpu.nvidia.com
          selectors:
            - cel:
                expression: 'device.model == "A100" && device.capacity.memory >= 80Gi'
        - name: fallback-preference
          deviceClassName: gpu.nvidia.com
          selectors:
            - cel:
                expression: 'device.model == "A100" && device.capacity.memory >= 40Gi'
          count: 2
```
*Implementation Detail: The scheduler evaluates this manifest by first attempting to secure a single 80GB A100 GPU. If cluster capacity is insufficient, it dynamically falls back to allocating two 40GB A100 GPUs.*

## Architectural Trade-Offs and Limitations

While DRA enables granular hardware orchestration, it introduces significant complexity to the control plane:

* **NP-Hard Scheduling Expansion**: Adding fine-grained hardware parameters and fallback alternatives exponentially expands the scheduler's search space. While flexible `ResourceClaim`s improve workload obtainability, they severely penalize scheduler throughput in dense, highly-contended clusters.
* **Optimality vs. Solvability**: The current DRA scheduling implementation prioritizes finding *a* valid hardware match rather than computing the globally optimal placement. Workloads requiring strict multi-node gang scheduling or perfect topology alignment within a node may suffer sub-optimal placements.
* **Opaque Node Resources**: Aligning standard node allocatable resources (CPU/RAM) with specialized hardware on a unified topology map remains unresolved. This disjointed metadata risks placing a workload's CPU threads on a different NUMA node than its allocated GPU, bottlenecking interconnect performance.