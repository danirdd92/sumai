---
title: "Tetragon 1.7: Precision filtering, richer context, and better performance"
originalUrl: "https://isovalent.com/blog/post/tetragon-v1.7-release"
publishDate: 2026-05-06T12:40:00+00:00
source: "cilium"
tags: ["ebpf", "security", "observability", "kubernetes"]
---

Tetragon 1.7 introduces several architectural enhancements focusing on low-overhead execution, precise kernel-space filtering, and richer runtime telemetry.

### `fentry` Sensor Support
Tetragon now supports attaching eBPF programs via `fentry`/`fexit` hooks, providing an alternative to traditional `kprobes`.

*   **Mechanism**: Leverages BPF trampolines to attach directly to kernel functions without the breakpoint/trap overhead of `kprobes`.
*   **Trade-offs**: 
    *   *Advantage*: Near-zero overhead for entry/exit tracing.
    *   *Limitation*: Currently supports **monitoring only**. Runtime enforcement (e.g., blocking system calls or terminating processes) still requires `kprobes`.
*   **Implementation**: Migration from `kprobes` requires only changing the hook declaration in the TracingPolicy.

```yaml
# Fentry-based TracingPolicy
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: fentry-mount-monitor
spec:
  fentries:
  - call: "sys_mount"
```

### In-Kernel CEL Evaluation
Tetragon implements a Common Expression Language (CEL) to BPF compiler, executing complex filtering logic entirely in kernel space.

*   **Mechanism**: CEL syntax is compiled directly into native BPF bytecode. Supports arithmetic (`+`, `-`, `*`, `/`, `>>`, `<<`), comparisons (`==`, `!=`, `>`, `>=`, `<`, `<=`), and logical operators across 32-bit and 64-bit integers. Function arguments are accessed directly via `arg0`, `arg1`, etc.
*   **Performance Impact**: Eliminates the overhead of copying event data to userspace for evaluation (zero-copy filtering).
*   **Compatibility**: Adapts across kernel versions 4.19 to 6.1+, with graceful fallbacks for missing kernel capabilities.

### `matchParentBinaries` Selector
Filters process events based on the parent process lineage rather than just the executing binary.

*   **Mechanism**: Evaluates the process tree to determine if a binary was spawned by a specific parent. Supports `followChildren: true` to evaluate transitive parents across the entire process lineage.
*   **Use Case**: Reducing false positives by distinguishing legitimate invocations (e.g., a shell spawned by `sshd`) from suspicious ones (e.g., a shell spawned by a web server).

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: suspicious-shell-lineage
spec:
  kprobes:
  - call: "sys_execve"
    selectors:
    - matchBinaries:
      - operator: "In"
        values: ["/bin/sh", "/bin/bash"]
      matchParentBinaries:
      - operator: "NotIn"
        values: ["/usr/sbin/sshd", "/bin/login", "/usr/bin/sudo"]
        followChildren: true
```

### Environment Variable Collection
Extracts environment variables at process startup and embeds them within `process_exec` events.

*   **Mechanism**: Captures both explicitly passed variables and inherited environment state. 
*   **Implementation**: Disabled by default. Enabled via daemon flags. Integrates directly with Tetragon's redaction engine to scrub sensitive data (passwords, tokens) before telemetry export.

```bash
# Tetragon daemon configuration to selectively capture env vars
tetragon --enable-process-environment-variables \
         --filter-environment-variables="ENV,AWS_REGION,KUBECONFIG"
```

### Granular Workload Scoping (`hostSelector`)
Introduces `hostSelector` to complement existing `podSelector` and `containerSelector` primitives, enabling explicit scoping of policies to the host operating system versus containerized workloads.

*   **Mechanism**: Replaces brittle namespace-based filtering.
    *   `hostSelector: {}` targets host-level execution.
    *   `hostSelector: null` ignores host-level execution.
*   **Use Case**: Separating audit trails for infrastructure operations from business application telemetry.

### Additional Engineering Improvements
*   **IPC Isolation**: The Tetragon gRPC server now binds to UNIX Domain Sockets (UDS) instead of `localhost`, improving security isolation.
*   **Memory Management**: Addressed memory leaks affecting long-running deployments.
*   **Safety**: Improved BPF NULL pointer handling and userspace string matching reliability. 
*   **Platform**: Extended ARM architecture support and optimized `uprobe` functionality.