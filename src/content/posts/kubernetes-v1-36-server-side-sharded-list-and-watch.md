---
title: "Kubernetes v1.36: Server-Side Sharded List and Watch"
originalUrl: "https://kubernetes.io/blog/2026/05/06/kubernetes-v1-36-server-side-sharded-list-and-watch/"
publishDate: 2026-05-06T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scalability", "architecture", "api-machinery"]
---

# Server-Side Sharded List and Watch

## Architectural Context
Controllers watching high-cardinality resources (e.g., Pods) in large clusters hit a scaling limit due to redundant data transmission. Historically, client-side sharding (like in `kube-state-metrics`) required every controller replica to receive the complete event stream from the API server and discard unowned objects locally. This meant network bandwidth and CPU deserialization overhead scaled proportionally with the number of controller replicas (`N replicas × full event stream`).

Kubernetes v1.36 introduces **server-side sharded list and watch** (Alpha, KEP-5866) to shift the filtering upstream to the API server, transmitting only the relevant slice of the resource collection to each replica.

## How it Works
Clients specify a `shardSelector` inside their `ListOptions`. The API server computes a deterministic 64-bit FNV-1a hash of a specified resource field and returns only objects whose hash falls within the requested half-open range `[start, end)`. 

*   **Hash Function:** 64-bit FNV-1a (deterministic across all API server instances).
*   **Supported Fields:** `object.metadata.uid`, `object.metadata.namespace`.
*   **Feature Gate:** `ShardedListAndWatch` (API Server).

## Implementation

To adopt sharded informers, inject the `shardSelector` into the `ListOptions` via `WithTweakListOptions`.

```go
import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/informers"
)

// Example: Assign Replica 0 the lower half of the 64-bit hash space
shardSelector := "shardRange(object.metadata.uid, '0x0000000000000000', '0x8000000000000000')"

factory := informers.NewSharedInformerFactoryWithOptions(
	client,
	resyncPeriod,
	informers.WithTweakListOptions(func(opts *metav1.ListOptions) {
		opts.ShardSelector = shardSelector
	}),
)
```

For more complex topologies, non-contiguous hash ranges can be covered by a single replica using the logical OR operator (`||`):

```go
"shardRange(object.metadata.uid, '0x0000000000000000', '0x4000000000000000') || " +
"shardRange(object.metadata.uid, '0x8000000000000000', '0xc000000000000000')"
```

## Trade-offs and Failure Modes

**Required Fallback Mechanism**: The API server is not guaranteed to honor the `shardSelector` (e.g., if the `ShardedListAndWatch` feature gate is disabled or the request hits an older API server replica). 

Controllers must verify if server-side filtering was applied by checking the `shardInfo` block in the list response metadata:

```json
{
  "kind": "PodList",
  "apiVersion": "v1",
  "metadata": {
    "resourceVersion": "10245",
    "shardInfo": {
      "selector": "shardRange(object.metadata.uid, '0x0000000000000000', '0x8000000000000000')"
    }
  },
  "items": [ ... ]
}
```

If `shardInfo` is missing, the API server ignored the shard request and transmitted the full collection. To maintain correctness and prevent duplicate processing across horizontally scaled controllers, **the client must implement a fallback mechanism to perform client-side filtering** on the incoming event stream before yielding objects to the reconciliation loop.