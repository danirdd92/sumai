---
title: "Kubernetes v1.36: In-Place Vertical Scaling for Pod-Level Resources Graduates to Beta"
originalUrl: "https://kubernetes.io/blog/2026/04/30/kubernetes-v1-36-inplace-pod-level-resources-beta/"
publishDate: 2026-04-30T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scaling", "cgroups", "resource-management"]
---

# In-Place Pod-Level Resources Vertical Scaling (v1.36)

Enabled by default in Kubernetes v1.36 via the `InPlacePodLevelResourcesVerticalScaling` feature gate, this feature permits dynamic updates to the aggregate Pod resource budget (`.spec.resources`) for running Pods. This allows the shared pool of resources to be resized without restarting containers, avoiding downtime during scaling operations.

## Architecture and Mechanics

The Pod-level resource model enables containers to share a collective resource pool. Containers lacking individual limit definitions automatically inherit and scale their effective boundaries to match the resized Pod-level dimensions.

Upon initiating a Pod-level resize, the Kubelet interprets the change as a resize event for all containers inheriting the Pod's limits. The Kubelet determines the update mechanism by checking the `resizePolicy` for each container:

*   **`NotRequired`**: Kubelet attempts to dynamically update cgroup limits via the Container Runtime Interface (CRI).
*   **`RestartContainer`**: Kubelet restarts the container to enforce the new resource boundary safely.

*Note: `resizePolicy` is evaluated per container. It is not currently supported at the Pod level.*

## Update Sequencing and Safety

To prevent resource overshoot and maintain node stability, Kubelet coordinates cgroup updates in a strict sequence:

1.  **Scaling Up**: The Pod-level cgroup expands first, allocating capacity before individual container cgroups are enlarged.
2.  **Scaling Down**: Individual container cgroups are throttled first, followed by the reduction of the aggregate Pod-level cgroup.

Prior to admitting a resize operation, the Kubelet executes a feasibility check against the Node's allocatable capacity. If the Node is overcommitted, the resize request is not discarded. Instead, it is recorded in the `PodResizePending` condition with a status of `Deferred` or `Infeasible`.

## Observability

Resize lifecycle states are surfaced via Pod Conditions:

*   `PodResizePending`: The Pod spec `.resources` is updated, but Node admission is pending (typically due to capacity constraints).
*   `PodResizeInProgress`: The Node has admitted the resize (`status.allocatedResources` reflects the new values), but the modifications are not yet fully propagated to the underlying cgroups (`status.resources` remains unupdated).

## Implementation Example

The following configuration defines a Pod where two containers share a 2 CPU pool without individual limit constraints. 

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: shared-pool-app
spec:
  resources:
    limits:
      cpu: "2"
      memory: "4Gi"
  containers:
    - name: main-app
      image: my-app:v1
      resizePolicy:
        - resourceName: "cpu"
          restartPolicy: "NotRequired"
    - name: sidecar
      image: logger:v1
      resizePolicy:
        - resourceName: "cpu"
          restartPolicy: "NotRequired"
```

To dynamically double the CPU capacity to 4 CPUs, apply a patch via the `resize` subresource:

```bash
kubectl patch pod shared-pool-app --subresource resize --patch \
  '{"spec":{"resources":{"limits":{"cpu":"4"}}}}'
```

## Constraints and Prerequisites

*   **cgroup v2**: Mandatory for accurate aggregate resource enforcement.
*   **CRI Support**: The container runtime must support the `UpdateContainerResources` CRI call (e.g., containerd v2.0+ or CRI-O).
*   **Linux Only**: This feature is currently exclusive to Linux-based nodes.
*   **Feature Gates**: Requires `PodLevelResources`, `InPlacePodVerticalScaling`, `InPlacePodLevelResourcesVerticalScaling`, and `NodeDeclaredFeatures` to be active.