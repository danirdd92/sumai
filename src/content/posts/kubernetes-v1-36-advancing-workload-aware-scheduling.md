---
title: "Kubernetes v1.36: Advancing Workload-Aware Scheduling"
originalUrl: "https://kubernetes.io/blog/2026/05/13/kubernetes-v1-36-advancing-workload-aware-scheduling/"
publishDate: 2026-05-13T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scheduling", "architecture", "batch-processing", "ai-ml"]
---
Kubernetes v1.36 redesigns workload-aware scheduling by decoupling static templates from runtime states in the `scheduling.k8s.io/v1alpha2` API. 

## Architectural Split: Workload vs. PodGroup

The v1alpha1 `Workload` object previously embedded both pod groups and their runtime states. The v1alpha2 API separates these concerns to improve scalability via per-replica sharding of status updates and to streamline `kube-scheduler` logic:

- **`Workload`**: Acts exclusively as a static template object.
- **`PodGroup`**: Manages the runtime scheduling policy and status.

`kube-scheduler` now reads `PodGroup` directly without parsing the `Workload` object. 

### Implementation

The `Workload` controller (e.g., Job controller) defines the static template:

```yaml
apiVersion: scheduling.k8s.io/v1alpha2
kind: Workload
metadata:
  name: training-job-workload
spec:
  podGroupTemplates:
    - name: workers
      schedulingPolicy:
        gang:
          minCount: 4
```

Controllers stamp out runtime `PodGroup` instances from the template:

```yaml
apiVersion: scheduling.k8s.io/v1alpha2
kind: PodGroup
metadata:
  name: training-job-workers-pg
spec:
  podGroupTemplateRef:
    workload:
      workloadName: training-job-workload
    podGroupTemplateName: workers
  schedulingPolicy:
    gang:
      minCount: 4
status:
  conditions:
    - type: PodGroupScheduled
      status: "True"
```

The Pod API `workloadRef` field is replaced by `schedulingGroup`, linking pods directly to the runtime `PodGroup`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: worker-0
spec:
  schedulingGroup:
    podGroupName: training-job-workers-pg
```

## PodGroup Scheduling Cycle & Gang Scheduling

`kube-scheduler` now features an atomic `PodGroup` scheduling cycle to prevent deadlocks in all-or-nothing deployments:

1. Takes a single snapshot of cluster state.
2. Evaluates the group using standard Pod-based filtering/scoring.
3. If `minCount` is met, all schedulable pods move to the binding phase together. 
4. If `minCount` is not met, the entire group is rejected and returns to the scheduling queue with a backoff. Bound pods remain running; the scheduler does not unassign them if subsequent cycles fail.

### Failure Modes & Limitations
The deterministic processing order of this algorithm means it is not guaranteed to find a valid placement for:
- Heterogeneous pod groups.
- Pod groups with inter-pod dependencies (affinity, anti-affinity, topology spread).
- Pod groups with intra-group dependencies.

## Topology-Aware Scheduling

PodGroups now support topology constraints to co-locate distributed workloads and minimize network latency. 

```yaml
apiVersion: scheduling.k8s.io/v1alpha2
kind: PodGroup
metadata:
  name: topology-aware-workers-pg
spec:
  schedulingPolicy:
    gang:
      minCount: 4
  schedulingConstraints:
    topology:
      - key: topology.kubernetes.io/rack
```

The algorithm uses the `PlacementGenerate` extension point to propose node subsets and `PlacementScore` to select the optimal subset. 
*Constraint:* Topology-aware scheduling does not currently trigger pod preemption to satisfy constraints.

## Workload-Aware Preemption

Preemption now evaluates the entire `PodGroup` as a single preemptor across the cluster, rather than pod-by-pod per node. This enables freeing up space across multiple nodes simultaneously.

The `PodGroup` API introduces two fields for this mechanism:
- `priority`: Overrides individual pod priorities.
- `disruptionMode`: Dictates if pods are preempted independently or in an all-or-nothing fashion.

```yaml
apiVersion: scheduling.k8s.io/v1alpha2
kind: PodGroup
metadata:
  name: victim-pg
spec:
  priorityClassName: high-priority
  priority: 1000
  disruptionMode: PodGroup
```
*Note:* In v1.36, these fields only apply to workload-aware preemption and not standard pod-by-pod preemption.

## DRA ResourceClaim for Workloads

Dynamic Resource Allocation (DRA) now supports `PodGroup` as a replicable unit for a `ResourceClaimTemplate`. A single claim can be generated and shared across all pods in a group, bypassing the previous 256-item limit in `status.reservedFor`.

```yaml
apiVersion: scheduling.k8s.io/v1alpha2
kind: PodGroup
metadata:
  name: training-job-workers-pg
spec:
  resourceClaims:
    - name: pg-claim
      resourceClaimTemplateName: my-claim-template
```
When pods in the group request `my-claim-template` under the same name `pg-claim`, they resolve to the single `ResourceClaim` generated for the group, avoiding duplicate claims per pod.

## Native Job Controller Integration

The Job controller automates `Workload` and `PodGroup` creation when the `WorkloadWithJob` feature gate is enabled, provided the Job has a fixed shape:
- `.spec.parallelism` > 1
- `.spec.completionMode` == `Indexed`
- `.spec.completions` == `.spec.parallelism`
- `.spec.template.spec.schedulingGroup` is unset.

If an external batch system manages the workload (indicated by a populated `schedulingGroup`), the Job controller defers and does not create its own objects.

## Feature Gates (Alpha in v1.36)

- **API Support**: `GenericWorkload` (kube-apiserver, kube-scheduler)
- **Gang Scheduling**: `GangScheduling` (kube-scheduler)
- **Topology-Aware Scheduling**: `TopologyAwareWorkloadScheduling` (kube-scheduler)
- **Workload-Aware Preemption**: `WorkloadAwarePreemption` (kube-scheduler, requires `GangScheduling`)
- **DRA Workloads**: `DRAWorkloadResourceClaims` (kube-apiserver, kube-controller-manager, kube-scheduler, kubelet)
- **Job Integration**: `WorkloadWithJob` (kube-apiserver, kube-controller-manager)