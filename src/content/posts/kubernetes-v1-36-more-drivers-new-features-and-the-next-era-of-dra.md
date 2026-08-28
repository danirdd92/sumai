---
title: "Kubernetes v1.36: More Drivers, New Features, and the Next Era of DRA"
originalUrl: "https://kubernetes.io/blog/2026/05/07/kubernetes-v1-36-dra-136-updates/"
publishDate: 2026-05-07T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scheduling", "dra", "hardware-accelerators", "numa"]
---

# Dynamic Resource Allocation (DRA) in v1.36

Kubernetes v1.36 matures Dynamic Resource Allocation (DRA) by stabilizing core primitives, bridging legacy APIs, and expanding the framework's scope to native infrastructure resources and large-scale workload orchestration.

## Stable & Beta Graduations

### Prioritized Lists (Stable)
**How it works**: Enables defining ordered fallback preferences when requesting devices via DRA. The scheduler evaluates these requests sequentially.
**Why it matters**: Prevents hard-coding specific device models, significantly improving scheduling flexibility and cluster utilization in heterogeneous hardware environments.

```yaml
# Conceptual implementation of a prioritized device request
apiVersion: resource.k8s.io/v1alpha3
kind: ResourceClaim
metadata:
  name: gpu-claim
spec:
  devices:
    requests:
      - name: preferred-gpu
        deviceClassName: gpu.example.com
        selectors:
          - cel:
              expression: 'device.attributes["model"] == "H100"'
      - name: fallback-gpu
        deviceClassName: gpu.example.com
        selectors:
          - cel:
              expression: 'device.attributes["model"] == "A100"'
```

### Partitionable Devices (Beta)
**How it works**: Provides native DRA support for dynamically carving physical hardware into smaller, logical instances (e.g., NVIDIA MIG) based on workload demands.
**Trade-offs**: Efficiently shares expensive accelerators across multiple Pods, but relies heavily on the underlying hardware's physical isolation capabilities to prevent noisy-neighbor performance degradation.

### Device Taints and Tolerations (Beta)
**How it works**: Applies Kubernetes taint semantics directly to specific DRA devices rather than the entire Node. 
**Why it matters**: Allows administrators to cordon faulty devices or reserve specific hardware configurations for dedicated teams without impacting the scheduling of standard compute on the same node.

```yaml
# Pod tolerating a tainted device
apiVersion: v1
kind: Pod
metadata:
  name: experimental-workload
spec:
  tolerations:
    - key: "hardware.example.com/reserved"
      operator: "Equal"
      value: "team-a"
      effect: "NoSchedule"
```

### Extended Resource Support (Beta)
**How it works**: Allows workloads to request resources via traditional pod-level extended resources, which are then fulfilled by the DRA backend.
**Why it matters**: Decouples operator infrastructure migrations from application-level API migrations. Cluster admins can migrate to DRA drivers while developers continue using legacy resource requests.

### Binding Conditions (Beta)
**How it works**: Delays the scheduler from fully committing a Pod to a Node until external resources (e.g., attachable FPGAs) are fully prepared.
**Failure mode**: If the external driver fails to signal readiness due to a bug or hardware failure, the Pod will remain indefinitely stuck in a binding state rather than failing fast.

### Resource Health Status (Beta)
**How it works**: Surfaces device health telemetry and human-readable error messages directly in the Pod status.
**Why it matters**: Eliminates the need to scrape individual driver logs to diagnose hardware allocation failures.

## Alpha Features & Architectural Expansions

### Node Allocatable Resources via DRA
**How it works**: Begins managing native infrastructure resources (CPU, Memory) through the DRA API instead of the traditional kubelet allocation model.
**Why it matters**: Unlocks DRA's advanced placement, NUMA-awareness, and prioritization semantics for standard compute workloads.
**Trade-offs**: Introduces scheduling overhead and complexity to core compute paths. Managing standard CPU/memory via DRA is a massive architectural shift requiring careful evaluation for latency-sensitive scheduling.

### ResourceClaim Support for Workloads
**How it works**: Associates `ResourceClaims` or `ResourceClaimTemplates` directly with `PodGroups`.
**Why it matters**: Resolves critical scaling bottlenecks for strict topological scheduling in large AI/ML workloads by allowing massive sets of Pods to share claims without manual orchestrator intervention.

### DRA Resource Availability Visibility
**How it works**: Introduces the `ResourcePoolStatusRequest` object to query point-in-time capacity snapshots (total, allocated, available, unavailable) per device pool.
**Why it matters**: Provides a standard API for capacity planning tools and dashboards to monitor hardware utilization without reverse-engineering allocations.

### Discoverable Device Metadata in Containers
**How it works**: Defines a standard protocol for DRA drivers to expose hardware metadata to containers as versioned JSON files at well-known paths via CDI (Container Device Interface) bind-mounts.
**Why it matters**: Workloads can parse hardware topology locally without needing RBAC permissions to query the Kubernetes API or `ResourceSlice` objects.

```json
// Example: /etc/cdi/device-metadata.json exposed to the container
{
  "version": "1.0.0",
  "device": {
    "pciBus": "0000:41:00.0",
    "numaNode": 1,
    "vramAllocatedGB": 40
  }
}
```

### Evaluation & Deterministic Selection
- **List Types & CEL**: `matchAttribute` now supports non-empty intersection checks, and `distinctAttribute` supports pairwise disjoint values. A new CEL `includes()` function simplifies evaluating attributes that toggle between scalars and lists.
- **Deterministic Selection**: The scheduler now evaluates devices using lexicographical ordering based on resource pool and `ResourceSlice` names. 
**Why it matters**: Allows driver authors to proactively dictate exact device allocation ordering (e.g., filling a specific PCIe switch topology first) simply by formatting their generated names correctly.