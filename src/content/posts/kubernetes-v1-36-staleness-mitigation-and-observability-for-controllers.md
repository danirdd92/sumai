---
title: "Kubernetes v1.36: Staleness Mitigation and Observability for Controllers"
originalUrl: "https://kubernetes.io/blog/2026/04/28/kubernetes-v1-36-staleness-mitigation-for-controllers/"
publishDate: 2026-04-28T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "client-go", "architecture", "observability"]
---

# Controller Staleness & Mitigation
Controller cache staleness occurs when a controller reconciles against an outdated local state (e.g., following a restart or API server unavailability), resulting in incorrect or delayed actions. Kubernetes v1.36 introduces "read your own writes" consistency mechanisms to prevent controllers from acting on stale cache data.

## Architectural Changes

### client-go: Atomic FIFO and Resource Version Tracking
- **Atomic FIFO Processing** (`AtomicFIFO` feature gate): Processes batched operations (like informer initialization `list`s) atomically. This maintains queue consistency even when events arrive out-of-order.
- **Cache Introspection**: The `Store` interface exposes `LastStoreSyncResourceVersion()`, allowing clients to query the highest resource version successfully processed by the cache.

### kube-controller-manager
Staleness mitigation is enabled by default for highly contended, pod-managing controllers: DaemonSet, StatefulSet, ReplicaSet, and Job.
- **Feature Gates**: Controlled per-API via `StaleControllerConsistency<API type>` (e.g., `StaleControllerConsistencyDaemonSet`).
- **Mechanism**: Before reconciling, the controller compares its cache's latest resource version against the resource version of its most recent API server write. If the cache is behind, reconciliation is skipped.

## Implementation for Informer Authors
Custom controllers can implement staleness mitigation using the `ConsistencyStore` interface provided by `client-go`. 

```go
type ConsistencyStore interface {
    // Records an API write. Tracks the owning object's resource version.
    WroteAt(owningObj runtime.Object, uid types.UID, groupResource schema.GroupResource, resourceVersion string)
    
    // Evaluates if the cache has caught up to the written resource version.
    EnsureReady(namespacedName types.NamespacedName) bool
    
    // Cleans up tracking data on object deletion. 
    // UID is required to prevent accidental removal of recreated objects with the same name.
    Clear(namespacedName types.NamespacedName, uid types.UID)
}
```

### Reconciliation Pattern Example
To achieve read-after-write consistency in a custom controller loop:

```go
func (r *Reconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    // 1. Check if cache has caught up to our last write
    if !r.consistencyStore.EnsureReady(req.NamespacedName) {
        // Cache is stale; skip and wait for informer updates
        return ctrl.Result{Requeue: true}, nil
    }
    
    // ... standard reconciliation logic ...
    
    // 2. Perform write to API Server
    if err := r.client.Update(ctx, obj); err != nil {
        return ctrl.Result{}, err
    }
    
    // 3. Record the write's ResourceVersion
    r.consistencyStore.WroteAt(
        obj, 
        obj.GetUID(), 
        obj.GroupVersionKind().GroupResource(), 
        obj.GetResourceVersion(),
    )
    
    return ctrl.Result{}, nil
}
```
*Note: Native integration of these semantics into `controller-runtime` is planned for future releases.*

## Observability (Alpha)
New metrics allow monitoring of cache synchronization and staleness events to debug controller lag.

| Metric | Subsystem | Description |
| :--- | :--- | :--- |
| `stale_sync_skips_total` | `kube-controller-manager` | Counter for reconciliations skipped due to a stale cache. Grouped by controller subsystem. |
| `store_resource_version` | `client-go` | Exposes the latest resource version of each shared informer. Can be diffed against the API server's current resource version to measure replication lag. Labels: `Group`, `Version`, `Resource`. |