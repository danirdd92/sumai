---
title: "Kubernetes v1.36: Pod-Level Resource Managers (Alpha)"
originalUrl: "https://kubernetes.io/blog/2026/05/01/kubernetes-v1-36-feature-pod-level-resource-managers-alpha/"
publishDate: 2026-05-01T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "resource-management", "numa", "scheduling", "performance"]
---
Kubernetes v1.36 introduces Pod-Level Resource Managers (alpha), shifting the kubelet's Topology, CPU, and Memory Managers from a strictly per-container allocation model to a pod-centric one via the `.spec.resources` API.

### The Problem
Historically, achieving predictable performance (NUMA-aligned, exclusive resources) for latency-sensitive or compute-heavy workloads required assigning exclusive, integer-based CPU resources to *every* container in a pod to maintain a Guaranteed QoS class. This forced engineers to wastefully over-allocate dedicated cores to lightweight auxiliary containers (e.g., sidecars, loggers, meshes) just to ensure the primary workload remained NUMA-aligned.

### Architectural Solution
By enabling the `PodLevelResources` and `PodLevelResourceManagers` feature gates, the kubelet can now execute hybrid resource allocations within a single pod. This allows exclusive, NUMA-aligned resources to be carved out for primary application containers, while sidecars are relegated to a shared pool without forfeiting the pod's overall Guaranteed QoS status.

### Implementation Patterns

#### 1. Topology Manager Scope: `pod`
In `pod` scope, the kubelet performs a single NUMA alignment based on the **entire pod's budget**. The primary container receives its exclusive CPU and memory slices from that specific NUMA node. The remaining resources form a new **pod shared pool**. Sidecars run in this pool, sharing resources with each other while remaining strictly isolated from both the primary container's exclusive slices and the broader node pool.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: tightly-coupled-database
spec:
  # Pod-level resources establish the overall budget and NUMA alignment size.
  resources:
    requests:
      cpu: "8"
      memory: "16Gi"
    limits:
      cpu: "8"
      memory: "16Gi"
  initContainers:
  - name: metrics-exporter
    image: metrics-exporter:v1
  - name: backup-agent
    image: backup-agent:v1
  containers:
  - name: database
    image: database:v1
    # Receives an exclusive 6 CPU slice from the pod budget.
    # The remaining 2 CPUs and 4Gi memory form the pod shared pool for sidecars.
    resources:
      requests:
        cpu: "6"
        memory: "12Gi"
      limits:
        cpu: "6"
        memory: "12Gi"
```

#### 2. Topology Manager Scope: `container`
In `container` scope, the kubelet evaluates containers individually. The primary container receives exclusive, NUMA-aligned CPUs and memory. Sidecars—which typically do not require NUMA alignment—are placed in the general **node-wide shared pool**. The collective resource consumption is bounded by overall pod limits, but NUMA-aligned exclusive resources are strictly reserved only for the containers that request them.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ml-workload
spec:
  # Pod-level resources establish the overall budget constraint.
  resources:
    requests:
      cpu: "4"
      memory: "8Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  initContainers:
  - name: service-mesh-sidecar
    image: service-mesh:v1
  containers:
  - name: ml-training
    image: ml-training:v1
    # Under 'container' scope, this receives exclusive, NUMA-aligned resources.
    # The service-mesh sidecar runs in the node's shared pool.
    resources:
      requests:
        cpu: "3"
        memory: "6Gi"
      limits:
        cpu: "3"
        memory: "6Gi"
```

### CPU CFS Quotas and Isolation Trade-offs
Isolation enforcement diverges based on the allocation type, modifying how the Linux scheduler throttles containers:
* **Exclusive Containers:** CPU CFS quota enforcement is disabled at the container level. The container runs entirely unthrottled by the scheduler.
* **Pod Shared Pool Containers:** CPU CFS quotas are enforced at the pod level to ensure these containers do not exceed the unallocated leftover pod budget.

### Configuration Requirements
To enable this architecture in v1.36+, the `KubeletConfiguration` must be set with the following parameters:
1. **Feature Gates:** `PodLevelResources=true`, `PodLevelResourceManagers=true`
2. **Topology Manager Policy:** `best-effort`, `restricted`, or `single-numa-node` (Cannot be `none`)
3. **Topology Manager Scope:** Set `topologyManagerScope` to `pod` or `container`
4. **CPU Manager Policy:** `static`
5. **Memory Manager Policy:** `Static`

### Observability Metrics
New kubelet metrics expose the state of these allocation models:
* `resource_manager_allocations_total`: Tracks exclusive allocations. The `source` label (`pod` or `node`) differentiates between allocations drawn from a pre-allocated pod-level pool versus the node-level pool.
* `resource_manager_allocation_errors_total`: Tracks allocation failures, segmented by intended `source` (`pod` or `node`).
* `resource_manager_container_assignments`: Tracks cumulative container assignment types via the `assignment_type` label (`node_exclusive`, `pod_exclusive`, `pod_shared`).