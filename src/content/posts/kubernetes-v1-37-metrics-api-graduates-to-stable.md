---
title: "Kubernetes v1.37: Metrics API graduates to stable"
originalUrl: "https://kubernetes.io/blog/2026/08/27/kubernetes-v1-37-metrics-api-ga/"
publishDate: 2026-08-27T10:30:00-08:00
source: "kubernetes"
tags: ["kubernetes", "metrics", "autoscaling", "api"]
---

# Metrics API (metrics.k8s.io) Reaches Stable (v1)

The `metrics.k8s.io` API, responsible for exposing CPU and memory usage data for nodes and Pods, is now stable (`v1`) in Kubernetes v1.37. The `v1` API surface is structurally identical to `v1beta1`. This is purely an API-version graduation; the underlying metrics and data structures remain unchanged.

## Architecture & Scope

The API exposes two primary resources:
- `NodeMetrics`: Node-level CPU and memory consumption.
- `PodMetrics`: Pod-level CPU and memory consumption, including a per-container breakdown via the `containers` field.

**Scope Limits:** The API is deliberately constrained. It satisfies requirements for basic autoscaling and `kubectl top` functionality. It does not replace full observability pipelines and cannot handle arbitrary application telemetry (which remains the domain of `custom.metrics.k8s.io`). 

Metrics are served via the **API aggregation layer**. An active backend implementation (such as `metrics-server`) must be deployed in the cluster to expose the `v1.metrics.k8s.io` endpoint, coupled with an `APIService` registration.

## Compatibility & Client Behavior

Implementations are expected to serve both `v1` and `v1beta1` simultaneously to maintain backwards compatibility with older clients.

- **`kubectl top`**: Natively supports both versions. It prefers `v1` but gracefully falls back to `v1beta1` if the cluster does not yet serve the stable endpoint.
- **HorizontalPodAutoscaler (HPA)**: **Critical limitation in v1.37** — The HPA controller currently *only* supports the `v1beta1` endpoint. Discovery-based version negotiation is not supported in this release.

## Implementation Validation

**Verify available metrics API versions on the cluster:**
```bash
kubectl get --raw /apis/metrics.k8s.io/ | jq .
```

**Validate the v1 APIService is registered and available:**
```bash
kubectl get apiservice v1.metrics.k8s.io
```

**Query raw node metrics via the stable API endpoint:**
```bash
kubectl get --raw /apis/metrics.k8s.io/v1/nodes
```

**Query raw pod metrics within a namespace via the stable API endpoint:**
```bash
kubectl get --raw /apis/metrics.k8s.io/v1/namespaces/default/pods