---
title: "Kubernetes v1.36: New Metric for Route Sync in the Cloud Controller Manager"
originalUrl: "https://kubernetes.io/blog/2026/05/15/ccm-new-metric-route-sync-total/"
publishDate: 2026-05-15T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "metrics", "cloud-controller-manager", "networking"]
---
# New CCM Route Sync Metric

Kubernetes v1.36 introduces an alpha counter metric, `route_controller_route_sync_total`, to the Cloud Controller Manager (CCM) route controller (`k8s.io/cloud-provider`). This metric increments on every route synchronization with the underlying cloud provider.

## Validating Watch-Based Route Reconciliation

The primary use case for this metric is validating the `CloudControllerManagerWatchBasedRoutesReconciliation` feature gate (introduced in v1.35). 

This feature gate shifts the route controller's behavior:
* **Disabled (Default):** The controller uses a fixed-interval polling loop, executing continuous, unnecessary API calls to the infrastructure provider regardless of cluster state.
* **Enabled:** The controller switches to an event-driven, watch-based approach, triggering reconciliation strictly when node events (adds, updates, removals) occur.

**Architectural Benefit:** Transitioning to event-driven reconciliation drastically reduces unnecessary infrastructure API calls, alleviating pressure on provider rate limits and preserving API quota for other operations.

## Validation via Metrics

Operators can validate the feature gate's efficiency gains by monitoring `route_controller_route_sync_total`. In environments with infrequent node churn, enabling the feature gate should result in a near-flatline sync rate.

### Expected Metric Behavior

**Fixed-Interval (Feature Gate Disabled):**
```text
# Continuous increments despite a stable cluster state
route_controller_route_sync_total 60   # @ 10 minutes
route_controller_route_sync_total 120  # @ 20 minutes
```

**Watch-Based (Feature Gate Enabled):**
```text
# Increments only on actual node state changes
route_controller_route_sync_total 1    # @ 10 minutes, stable state
route_controller_route_sync_total 1    # @ 20 minutes, stable state
route_controller_route_sync_total 2    # A new node joins the cluster