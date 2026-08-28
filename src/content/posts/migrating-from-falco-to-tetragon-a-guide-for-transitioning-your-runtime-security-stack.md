---
title: "Migrating from Falco to Tetragon: A Guide for Transitioning Your Runtime Security Stack"
originalUrl: "https://cilium.io/blog/2026/01/19/tetragon-falco-migrate"
publishDate: 2026-01-19T12:00:00+00:00
source: "cilium"
tags: ["security", "ebpf", "kubernetes", "tetragon", "falco"]
---

## Architectural Paradigm Shift

The fundamental difference between Falco and Tetragon lies in where policy evaluation and enforcement occur.

*   **Falco (Asynchronous User-Space):** Relies on a kernel driver or eBPF probe to collect system calls, pushing them via a ring buffer to a user-space daemon for evaluation against rules. This introduces context-switching overhead. Enforcement is asynchronous; a malicious process executes briefly before external response engines can mitigate it.
*   **Tetragon (Synchronous In-Kernel):** Evaluates policies directly within the kernel using eBPF. This enables synchronous enforcement—an offending syscall can be blocked (e.g., via `SIGKILL`) *before* the kernel executes the action, preventing the threat rather than reacting to it.

## Construct Mapping: Rules to TracingPolicies

Falco defines security policies using a custom YAML-based DSL containing macros and lists. Tetragon utilizes Kubernetes Custom Resource Definitions (CRDs) called `TracingPolicies` (or `ClusterTracingPolicies`).

### Example: Detecting Shell Execution in a Container

**Falco Rule:**

```yaml
- rule: Run shell in container
  desc: Detect a shell execution in a container
  condition: >
    spawned_process and container and
    proc.name in (shell_binaries)
  output: "Shell executed in container (user=%user.name container_id=%container.id command=%proc.cmdline)"
  priority: WARNING
```

**Tetragon TracingPolicy:**

Tetragon hooks directly into the `execve` syscall and provides native, in-band mitigation.

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: block-shell-in-container
spec:
  kprobes:
  - call: "sys_execve"
    syscall: true
    selectors:
    - matchArgs:
      - index: 0
        operator: "Equal"
        values:
        - "/bin/bash"
        - "/bin/sh"
      matchActions:
      - action: Sigkill
```

## Migration Strategy

1.  **Deconstruct Abstractions:** Falco abstracts kernel events into generic fields (`spawned_process`). Tetragon requires mapping these to specific kernel primitives (e.g., `sys_execve` kprobes or tracepoints).
2.  **Upgrade to Enforcement:** Identify high-confidence Falco rules (where false positives are zero) and translate them into Tetragon policies with `matchActions: [action: Sigkill]` to transition from detection-only to active prevention.
3.  **Adjust Pipeline Parsers:** Tetragon outputs structured JSON events natively. SIEM parsers must be rewritten, as Tetragon's schema reflects kernel internal structures rather than Falco's formatted string outputs.

## Architectural Trade-Offs & Failure Modes

*   **Kernel Version Dependency:** Tetragon requires a modern kernel (5.8+ recommended) for advanced eBPF features like ring buffers and `bpf_send_signal`. Falco supports older kernels via its legacy kernel module.
*   **Policy Complexity:** Writing Tetragon policies requires deeper knowledge of Linux kernel internals and ABI stability. If a hooked internal kernel function signature changes between kernel versions, Tetragon policies may silently fail to attach.
*   **Ecosystem Maturity:** Falco possesses a vast, community-driven default ruleset. Tetragon deployments often require building bespoke policies for environment-specific threats from scratch.