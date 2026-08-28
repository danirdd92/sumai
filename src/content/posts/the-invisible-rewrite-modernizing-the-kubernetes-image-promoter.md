---
title: "The Invisible Rewrite: Modernizing the Kubernetes Image Promoter"
originalUrl: "https://kubernetes.io/blog/2026/03/17/image-promoter-rewrite/"
publishDate: 2026-03-17T00:00:00+00:00
source: "kubernetes"
tags: ["kubernetes", "architecture", "supply-chain-security", "performance"]
---

The Kubernetes Image Promoter (`kpromo`) automates the movement of container images from staging registries to production (`registry.k8s.io`). Its critical path responsibilities include copying images, signing them via `cosign`, replicating signatures across 20+ regional mirrors, and generating SLSA provenance attestations. 

### Architectural Shift: Monolith to Pipeline Engine

Historically, `kpromo` operated as a tightly coupled monolith. This architecture suffered from severe API rate-limiting contention, causing production promotion jobs to exceed 30 minutes and frequently fail. Extending the tool to support modern supply-chain requirements (like vulnerability scanning or SLSA provenance) was prohibitively complex.

The core rewrite decoupled the monolithic function into a discrete, sequential pipeline engine. Registry and authentication operations were abstracted behind clean interfaces to enable independent testing and swapping. 

Crucially, **image signing was separated from signature replication**. Signature replication was removed from the primary promotion pipeline entirely and shifted to a dedicated, periodic Prow job. This architectural split eliminated the primary source of rate-limit contention during image promotion.

#### The Promotion Pipeline

Execution is now serialized across seven distinct phases. Because phases run sequentially, each phase receives exclusive access to the full rate-limit budget.

```text
[Setup]      Validate options, prewarm TUF cache
   │
   ▼
[Plan]       Parse manifests, read registries in parallel, compute diff
   │
   ▼
[Provenance] Verify SLSA attestations on staging images
   │
   ▼
[Validate]   Check cosign signatures (Dry runs terminate here)
   │
   ▼
[Promote]    Execute server-side image copy, preserving digests
   │
   ▼
[Sign]       Sign promoted images using keyless cosign
   │
   ▼
[Attest]     Generate promotion provenance (custom in-toto predicate)
```

### Performance & Reliability Optimizations

The decoupled architecture enabled highly targeted I/O optimizations that drastically reduced execution time and eliminated pipeline hangs.

1. **Parallelized Registry Reads**: Reading 1,350 registries sequentially during the `Plan` phase was parallelized, reducing the phase duration from ~20 minutes to ~2 minutes.
2. **Two-Phase Tag Listing**: Instead of aggressively querying 46,000 image groups across 20+ mirrors, the engine first checks source repositories. Because ~57% of legacy images lack signatures, skipping them cuts API calls in half.
3. **Optimized Replication Checks**: Before iterating across mirrors for a specific image, the system verifies the signature's existence on the primary registry. In steady-state, this reduced replication verification from ~17 hours to ~15 minutes.
4. **Network Resilience**: Implemented strict per-request timeouts to prevent multi-hour hangs on stalled connections, adaptive backoff for rate limits, automatic retries for transient network failures, and robust HTTP connection/auth state reuse.

### Trade-offs and Architectural Bottlenecks

While the rewrite reduced the codebase by 20% (net -5,000 lines) and resolved immediate rate-limiting failures without breaking legacy downstream manifests, a significant architectural bottleneck remains.

**The Signature Replication Problem:** Replicating OCI signatures across all regional mirror registries is fundamentally inefficient and remains the most expensive operation in the lifecycle. The current mitigation—offloading replication to an asynchronous Prow job—prevents pipeline failures but accepts eventual consistency for image signatures across regions.

Future architectural iterations propose eliminating replication entirely by configuring `archeio` (the `registry.k8s.io` redirect service) to selectively route all signature tag requests to a single canonical upstream, bypassing regional backends. Alternatively, signing operations could be shifted lower into the registry infrastructure itself.