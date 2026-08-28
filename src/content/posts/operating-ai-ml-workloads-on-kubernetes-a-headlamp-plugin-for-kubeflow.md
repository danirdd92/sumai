---
title: "Operating AI/ML Workloads on Kubernetes: A Headlamp Plugin for Kubeflow"
originalUrl: "https://kubernetes.io/blog/2026/07/13/introducing-headlamp-plugin-for-kubeflow/"
publishDate: 2026-07-13T12:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "kubeflow", "mlops", "observability", "crd"]
---

# Architecture and Motivation

Kubeflow implements ML orchestration—notebooks, distributed training, hyperparameter tuning, and pipelines—using Kubernetes Custom Resource Definitions (CRDs). While this aligns ML workloads with Kubernetes primitives, purpose-built ML dashboards abstract away the underlying infrastructure state. 

When an ML workload fails or stalls, operators are typically forced out of the ML dashboard to use `kubectl` to diagnose standard Kubernetes failures like `ImagePullBackOff`, `OOMKilled`, or unbound `PersistentVolumeClaims`. 

The **Headlamp Kubeflow Plugin** resolves this by surfacing Kubeflow CRDs directly within Headlamp, a general-purpose Kubernetes web UI. This allows cluster operators and SREs to introspect ML resources alongside core Kubernetes resources without context switching.

# Implementation Details

The plugin dynamically discovers installed Kubeflow API groups and queries the Kubernetes API server directly. Crucially, it does not rely on intermediate Kubeflow backend services or databases (like the Kubeflow Pipelines API). This guarantees observability even when the ML control plane is degraded or unavailable.

## Supported Capabilities

| Component | API Resources |
| :--- | :--- |
| **Notebooks** | `Notebook`, `Profile`, `PodDefault` |
| **Pipelines** | `Pipeline`, `PipelineVersion`, `Run`, `RecurringRun`, `Experiment` |
| **Katib** | `Experiment`, `Trial`, `Suggestion` |
| **Training** | `TrainJob`, `TrainingRuntime`, `ClusterTrainingRuntime` |
| **Spark** | `SparkApplication`, `ScheduledSparkApplication` |

## Core Observability Features

1. **Notebook Introspection**: Aggregates Pod conditions, resource requests/limits, volume mounts (PVCs, ConfigMaps, Secrets), and sidecars. This replaces the need for exhaustive `kubectl describe` parsing.
2. **Stateless Pipeline Diagnostics**: Reads pipeline states natively from the Kubernetes API, bypassing the backend database. Includes side-by-side YAML diffing for `PipelineVersion` specifications.
3. **Katib Tuning Visibility**: Exposes tuning algorithms, search spaces, live trial statuses, optimal parameter assignments, and early-stopping metrics natively.
4. **Resource Topology Mapping**: Parses `.metadata.ownerReferences` to render graph-based node representations of ML resources and their dependencies.

## Example: Resource Topology Mapping

The plugin builds visual graphs based on Kubernetes ownership models. A simplified Katib hyperparameter tuning execution maps hierarchically as follows:

```text
[Experiment] (Katib)
      │
      ├── (owns) ──> [Suggestion] (Generates hyperparameters)
      │
      └── (owns) ──> [Trial] (Individual run)
                       │
                       └── (owns) ──> [Job] (Standard K8s Job)
                                        │
                                        └── (owns) ──> [Pod] (Execution environment)
```

## Architectural Trade-offs and Failure Modes

* **API Server Load**: By intentionally bypassing the ML backend database, the plugin shifts read pressure directly to the Kubernetes API server. In clusters with extreme CRD churn (e.g., thousands of ephemeral pipeline runs or rapid Katib trials), this could impact API server latency and etcd performance.
* **Control Plane vs. Data Plane**: The plugin provides a strict infrastructure-level view. It is read-only for ML operations and does not replace the specialized UIs data scientists require for submitting experiments or managing datasets.
* **UI Fragmentation**: Utilizing this plugin requires adopting Headlamp as a cluster UI. For teams already deeply invested in other Kubernetes dashboards (e.g., Lens, ArgoCD, or native Grafana/Prometheus stacks), this introduces another pane of glass to maintain and secure.