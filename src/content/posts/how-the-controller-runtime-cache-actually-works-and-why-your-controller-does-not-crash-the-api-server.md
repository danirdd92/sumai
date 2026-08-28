---
title: "How the controller-runtime Cache Actually Works, and Why Your Controller Does Not Crash the API Server"
originalUrl: "https://kubernetes.io/blog/2026/07/29/controller-runtime-cache-explained/"
publishDate: 2026-07-29T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "golang", "controller-runtime", "architecture"]
---

`controller-runtime` avoids overloading the Kubernetes API server by operating against a local in-memory cache populated via a `list` and `watch` mechanism. 

## The Read/Write Split

The `client.Client` provided by `controller-runtime` is a composite object:
*   **Reads (`Get`, `List`):** Served entirely from the local in-memory cache.
*   **Writes (`Create`, `Update`, `Patch`, `Delete`):** Go directly to the API server, bypassing the cache.

Writing directly to the API server prevents split-brain scenarios where the local cache registers a write that the API server subsequently rejects. 

## Cache Architecture

The `controller-runtime` cache is a wrapper around `k8s.io/client-go/tools/cache`. The pipeline flows as follows:

1.  **Reflector:** Maintains a connection to the API server. It fetches an initial snapshot (via a streaming list) and opens a `watch` stream starting from the snapshot's `resourceVersion`. Changes are written as deltas into a queue. If the connection drops, it resumes from the last known `resourceVersion`. If the server returns `410 Gone`, it performs a full relist.
2.  **Delta Queue (`RealFIFO`):** A flat, strictly ordered queue of deltas (Added, Updated, Deleted). It delivers events in sequence without deduplication. Intermediate states (e.g., rapid consecutive updates) are all emitted to the informer.
3.  **Indexer (Store):** An in-memory `map[string]interface{}` keyed by `namespace/name`, protected by a `sync.RWMutex`. 
4.  **SharedIndexInformer:** Orchestrates the Reflector, Delta Queue, and Indexer. It writes objects to the Indexer and asynchronously dispatches events (`OnAdd`, `OnUpdate`, `OnDelete`) to all subscribed controllers. One informer exists per GroupVersionKind (GVK).
5.  **Workqueue:** Controller-specific queue. Event handlers extract the `namespace/name` from the object and enqueue it. Deduplication occurs here: multiple consecutive events for the same key coalesce into a single reconcile trigger.

## Consistency and Optimistic Concurrency

Because reads hit a local cache and writes hit the API server, the system is eventually consistent.

When executing an `Update`, the API server checks the `resourceVersion` of the provided object against `etcd`. If they match, the write succeeds. If `etcd` holds a newer version, the API server returns `409 Conflict`. 

```go
// Optimistic concurrency control via resourceVersion
if err := r.Update(ctx, &obj); err != nil {
    // If err is a 409 Conflict, the object was modified concurrently.
    // Return the error to re-queue and re-read in the next loop.
    return ctrl.Result{}, err
}
```

## Common Pitfalls

### 1. Expecting Read-After-Write Consistency

Because the cache catches up asynchronously via the `watch` stream, an `r.Get()` immediately following an `r.Update()` may return the old state.

**Anti-pattern:**
```go
r.Update(ctx, &obj)
r.Get(ctx, req.NamespacedName, &freshObj)
// freshObj may still reflect the state prior to the Update
```

**Solution:** Do not rely on immediate freshness. Ensure `Reconcile` is idempotent. If a stale read occurs, the subsequent reconcile trigger (fired when the watch stream processes your write) will provide the updated state.

### 2. Mutating Shared Objects in Predicates/Handlers

Objects returned by `r.Get()` and `r.List()` are deep-copied by default and are safe to mutate. However, objects passed to `Predicate` or `EventHandler` functions are pointers to the shared instances residing in the informer's store.

Mutating these objects without calling `DeepCopy()` silently corrupts the cache for all other controllers watching that GVK.

**Anti-pattern:**
```go
func(e event.UpdateEvent) bool {
    // CORRUPTS CACHE FOR ALL SUBSCRIBERS
    e.ObjectNew.GetLabels()["processed"] = "true" 
    return true
}
```

**Solution:** Always `DeepCopy()` shared objects before modification.
```go
func(e event.UpdateEvent) bool {
    obj := e.ObjectNew.DeepCopyObject().(client.Object)
    obj.GetLabels()["processed"] = "true"
    return true
}
```

### 3. Cache Warm-up and APIReader

The cache is fully warmed up before the manager starts invoking `Reconcile` loops. The initial `r.Get()` is just a map lookup; it does not block for network I/O. 

To read objects before `mgr.Start()` (e.g., during controller initialization), the standard client will fail with `ErrCacheNotStarted`. Use `mgr.GetAPIReader()` to bypass the cache and query the API server directly.