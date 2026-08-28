---
title: "Announcing etcd 3.7.0-beta.0"
originalUrl: "https://kubernetes.io/blog/2026/05/20/etcd-370-beta/"
publishDate: 2026-05-20T00:00:00+00:00
source: "kubernetes"
tags: ["etcd", "database", "distributed-systems", "rpc"]
---

# etcd v3.7.0-beta.0

The v3.7.0 release introduces the `RangeStream` RPC for chunked data retrieval and completely removes the legacy `v2store` architecture.

## RangeStream RPC

Prior to v3.7, clients querying large datasets were forced to wait for the entire result set to be assembled and transmitted in a single unary response. This model caused unpredictable latency spikes and unbounded memory consumption on both the client and server.

`RangeStream` implements a chunked, streaming response model for range queries. This architecture allows applications to process data iteratively, capping buffer memory usage and significantly reducing time-to-first-byte (TTFB) for large reads.

### Architectural Diagram

```text
+--------+                         +---------------+
| Client |                         | etcd v3.7+    |
+--------+                         +---------------+
    |       RangeStream Request            |
    |------------------------------------->|
    |                                      |
    |       Chunk 1 (Keys 1-1000)          |
    |<-------------------------------------|
    |                                      |
    |       Chunk 2 (Keys 1001-2000)       |
    |<-------------------------------------|
    |                                      |
    |       Chunk N (EOF)                  |
    |<-------------------------------------|
```

### Conceptual Implementation (Go)

```go
ctx, cancel := context.WithTimeout(context.Background(), requestTimeout)
defer cancel()

// Initiate the RangeStream RPC
stream, err := client.RangeStream(ctx, "prefix-", clientv3.WithPrefix())
if err != nil {
    log.Fatalf("Failed to initialize stream: %v", err)
}

for {
    chunk, err := stream.Recv()
    if err == io.EOF {
        break // Result set complete
    }
    if err != nil {
        log.Fatalf("Stream interrupted: %v", err)
    }

    // Iteratively process KVs, bounding memory usage
    for _, kv := range chunk.Kvs {
        processKeyValue(kv)
    }
}
```

### Trade-offs & Failure Modes
- **Throughput vs. Latency**: While streaming reduces peak memory and TTFB for large datasets, the network and processing overhead of multiple stream frames may introduce slight latency regressions for very small queries compared to a standard unary RPC.
- **Client Complexity**: Calling applications must implement stream handling, chunk assembly, and robust error handling for connection interruptions mid-stream.

## Complete Removal of v2store

etcd v3.7 marks the complete deprecation and removal of the `v2store` architecture. The database now operates 100% on `v3store`.

**Removed Components:**
- v2 API requests and v2 clients
- v2 discovery and bootstrap mechanisms
- Associated deprecated experimental flags

**Breaking Changes**: Applications relying on legacy v2 endpoints or behaviors will experience immediate failures upon upgrading. Clusters must be fully migrated to v3.6.x (specifically `v3.6.11` or higher is recommended) and validated against v3 APIs before attempting a v3.7 upgrade.

## Core Component Updates

- **bbolt**: Upgraded to `v1.5.0`
- **raft**: Upgraded to `v3.7.0`

## Support Lifecycle

- **v3.4**: End-of-Life (EOL) as of May 15, 2026. Clusters must be upgraded immediately.
- **v3.5**: Supported for 1 year following the v3.7.0 final release.
- **v3.6**: Actively maintained current stable version.