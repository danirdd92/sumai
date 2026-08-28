---
title: "Inspect Volcano workloads faster with Headlamp"
originalUrl: "https://kubernetes.io/blog/2026/06/25/visual-context-volcano-headlamp-plugin/"
publishDate: 2026-06-25T12:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scheduling", "batch-processing", "volcano", "headlamp"]
---

# Headlamp Integration with Volcano

Volcano extends Kubernetes batch scheduling capabilities for high-performance computing (HPC) and AI/ML workloads by introducing queueing, resource quotas, priority classes, and gang scheduling. 

The **Headlamp Volcano plugin** exposes Volcano Custom Resource Definitions (CRDs) within the Headlamp Web UI, resolving the fragmented operational experience of using `kubectl` and the Volcano CLI to traverse complex object relationships (`Job` → `PodGroup` → `Queue`).

## Architectural Context

Standard Kubernetes controllers expect long-running services, evaluating and scheduling Pods independently. Volcano introduces holistic job evaluation, where batch workloads compete for limited resources and require simultaneous multi-worker startup (gang scheduling) to prevent resource deadlocks. 

The Headlamp plugin visualizes these relationships by observing the core Volcano resources:

- **Job (`batch.volcano.sh/v1alpha1`)**: Encapsulates tasks, retry policies, and associated Pods.
- **Queue (`scheduling.volcano.sh/v1beta1`)**: Manages cluster capacity allocation using weighted priorities and quotas.
- **PodGroup (`scheduling.volcano.sh/v1beta1`)**: The core primitive for gang scheduling, defining the minimum threshold of Pods required to run concurrently before execution begins.

### Example Volcano Configuration

Headlamp interprets definitions like the following to render its UI components and dependency graphs:

```yaml
# Example Queue definition observed by the plugin
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
metadata:
  name: ml-training-queue
spec:
  weight: 1
  capability:
    cpu: "20"
    memory: "64Gi"
---
# Example Job illustrating gang scheduling via minAvailable
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: pytorch-training
spec:
  minAvailable: 4 # Gang scheduling threshold enforced by PodGroup
  schedulerName: volcano
  queue: ml-training-queue
  tasks:
    - replicas: 4
      name: worker
      template:
        spec:
          containers:
            - name: pytorch
              image: pytorch/pytorch:latest
```

## Plugin Capabilities

1. **Job Lifecycle Management**: 
   - Surfaces state metrics (running vs. minimum-available).
   - Exposes mutation actions (Suspend/Resume) for `Job` objects directly from the UI.
   - Aggregates multi-pod container logs with filtering and timestamp tracking, bypassing standard CLI multiplexing challenges.
2. **Queue Utilization Constraints**: 
   - Visualizes capacity limits, active reservations, and deserved vs. guaranteed resource splits across parent/child queue hierarchies.
3. **PodGroup Condition Monitoring**: 
   - Highlights gang scheduling progress against `minAvailable` requirements.
   - Explicitly surfaces blocked workloads waiting for global scheduling conditions, accelerating root cause analysis for pending batches.
4. **Relational Topology (Map View)**: 
   - Dynamically renders the object graph connecting `Jobs` → `PodGroups` → `Queues` → `Pods`. 
   - Maps error and warning states (e.g., pending due to quota exhaustion) across the hierarchy.

## Operational Trade-offs & Limitations

- **UI vs. CLI**: The plugin optimizes for interactive troubleshooting, visual state correlation, and manual lifecycle management. It does not replace the Volcano CLI or `kubectl` for automated CI/CD pipelines, bulk object mutations, or scripted infrastructure provisioning. 
- **Monitoring Scope**: The plugin currently relies strictly on Kubernetes API state (Events, Conditions, Status). It lacks native Prometheus metric integration, meaning deep performance profiling requires external observability stacks (planned as future work).
- **Dependency**: Operates entirely client-side as a Headlamp extension; it requires the Volcano control plane to be independently installed and healthy on the target cluster.

## Deployment

Install via the Headlamp Plugin Catalog:

```bash
# Verify Volcano is present in the target cluster:
kubectl get crds | grep volcano

# Install the Volcano plugin from the Headlamp UI Plugin Catalog
# Connect Headlamp to the cluster context to begin introspection.