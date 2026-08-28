---
title: "See your serverless: introducing the Headlamp plugin for Knative"
originalUrl: "https://kubernetes.io/blog/2026/06/25/headlamp-knative-plugin/"
publishDate: 2026-06-25T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "knative", "serverless", "operations", "observability"]
---

The Headlamp Knative plugin consolidates Knative operational workflows—traffic routing, autoscaling inspection, and revision management—into a single UI, eliminating context switching between `kn`, `kubectl`, and standard Kubernetes dashboards. 

### Core Capabilities

#### KService Management and Traffic Splitting
A `KService` manages the lifecycle of Routes, Configurations, and Revisions. The plugin provides a detail view with RBAC-gated, live-edit capabilities for these components.

*   **Traffic Management:** Facilitates inline adjustments to traffic distribution across Revisions for canary deployments and A/B testing.
*   **Validation:** Client-side validation ensures traffic splits sum strictly to 100% and route tags remain unique before mutating the resource.
*   **Routing Visibility:** Surfaces readiness status, age, and configured tags per Revision. Tagged routes with reported URLs render as directly routable links.

#### Autoscaling Configuration Resolution
Knative autoscaling behavior is determined by merging cluster-wide defaults with service-specific annotations. Debugging this hierarchy via CLI can be opaque and error-prone.

The plugin dynamically parses the `config-autoscaler` and `config-defaults` ConfigMaps and diffs them against `KService` annotations. It exposes the **effective configuration** (e.g., concurrency targets, RPS targets, min/max scale, stable windows), explicitly denoting whether a setting is locally overridden or inherited from cluster defaults.

```yaml
# Mechanism: Resolving Effective Autoscaling Configuration
# 1. Cluster Default (config-autoscaler ConfigMap)
data:
  container-concurrency-target-default: "100"
  scale-down-delay: "15m"

# 2. Service Annotation Override
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: workload-svc
  annotations:
    autoscaling.knative.dev/target: "50" # Overrides default of 100
    # scale-down-delay is not defined; implicitly inherited as 15m

# The plugin evaluates this hierarchy and visualizes the final merged state.
```

#### Resource Topology Mapping
The plugin extends Headlamp’s resource graph to Knative CRDs, visually mapping the referential relationships and lifecycle states between core resources.

```text
+---------------+
| DomainMapping |
+-------+-------+
        |
        v
  +----------+       +---------------+       +------------------+
  | KService | ----> | Configuration | ----> | Latest Revision  |
  +----------+       +---------------+       +------------------+
        |
        v
    +-------+        +-----------------+
    | Route | -----> | Revision N (20%)|
    +-------+ \      +-----------------+
               \
                \    +-----------------+
                 +-> | Revision M (80%)|
                     +-----------------+
```

#### Metrics and Cluster Networking
*   **Prometheus Integration:** When deployed alongside Headlamp's Prometheus plugin, it overlays request rates, latency, and resource utilization directly onto `KService` and `Revision` views. The per-revision request rate breakdown provides immediate telemetry validation during live traffic splits.
*   **Networking State:** Aggregates the `config-network` and `config-gateway` ConfigMaps to display the effective ingress class, gateway parameters, and backing services at a global cluster level.

### Deployment
*   **Requirement:** An active Knative installation on the target cluster.
*   **Installation:** Available via the Headlamp Desktop Plugin Catalog (search: Knative). Current release is `v0.3.0-beta`.