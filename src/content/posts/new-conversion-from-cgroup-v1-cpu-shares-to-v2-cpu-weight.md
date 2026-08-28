---
title: "New Conversion from cgroup v1 CPU Shares to v2 CPU Weight"
originalUrl: "https://kubernetes.io/blog/2026/01/30/new-cgroup-v1-to-v2-cpu-conversion-formula/"
publishDate: 2026-01-30T08:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "cgroup", "resource-management", "oci"]
---

The mapping of Kubernetes CPU requests to cgroup parameters has been updated to address priority inversion and sub-cgroup granularity issues introduced during the transition from cgroup v1 to v2.

## The Architectural Problem

Kubernetes translates CPU requests (milliCPU) into cgroup parameters. 
- **cgroup v1:** Uses `cpu.shares`. Range: `[2, 262144]`. Default: `1024`.
- **cgroup v2:** Uses `cpu.weight`. Range: `[1, 10000]`. Default: `100`.

The original cgroup v1 formula was:
`cpu.shares = milliCPU * (1024 / 1000)`

When cgroup v2 was adopted, a linear conversion was implemented (KEP-2254):
`cpu.weight = (1 + ((cpu.shares - 2) * 9999) / 262142)`

### Failure Modes of the Linear Mapping

1. **Priority Inversion vs. System Processes:** In v1, a 1 CPU request yields 1024 shares, equalling the system default and giving K8s workloads parity with non-K8s daemons. Under the linear v2 mapping, 1024 shares converts to a weight of `39`—far below the v2 default of `100`. In resource-starved environments, K8s workloads are heavily preempted by host processes.
2. **Sub-cgroup Starvation:** A small request of 100m CPU converts to 102 shares in v1, but yields a weight of just `4` in v2. This granularity is too coarse for distributing CPU time among nested sub-cgroups (e.g., in unprivileged or writable cgroup architectures).

```text
Priority Comparison: 1 CPU Request vs Host System Daemon

[cgroup v1]
K8s Workload (Shares: 1024)  ==================== (Parity)
Host Daemon  (Shares: 1024)  ====================

[cgroup v2 - Linear Mapping]
K8s Workload (Weight: 39)    =======              (K8s Starved)
Host Daemon  (Weight: 100)   ====================

[cgroup v2 - Quadratic Mapping]
K8s Workload (Weight: 102)   ==================== (Parity Restored)
Host Daemon  (Weight: 100)   ====================
```

## The Quadratic Solution

The new conversion formula abandons linear mapping for a quadratic function intersecting three critical resource anchor points:
- **Minimum:** `(2, 1)`
- **Default:** `(1024, 100)`
- **Maximum:** `(262144, 10000)`

**Formula:**
`cpu.weight = ceil(10^(L^2/612 + 125L/612 - 7/34))` 
*(where `L = log2(cpu.shares)`)*

### Corrected Outcomes
- **1 CPU (1000m):** Results in `cpu.weight = 102` (Restores parity with system default `100`).
- **100m CPU:** Results in `cpu.weight = 17` (Provides usable granularity for sub-cgroup delegation).

## Implementation & Requirements

This mapping change is implemented entirely in the **OCI runtime layer**, not in the kubelet or the Kubernetes control plane. 

To adopt the fix, you must upgrade your container runtime:
- **runc:** `>= 1.3.2`
- **crun:** `>= 1.23`

## Trade-offs & Breaking Changes

**Lossy Parameter Reversal**
The translation from milliCPU to `cpu.weight` is now strictly one-way. 

The new quadratic mapping is a many-to-one function. For example, milliCPU values from `90m` to `109m` all map to `cpu.weight = 17`.

**Do not** attempt to calculate a pod's requested CPU by reversing its cgroup `cpu.weight`. Custom resource management tools, telemetry agents, and admission controllers that attempt to predict or validate `cpu.weight` based on the old linear formula will break. Tools requiring exact CPU request values must read them directly from the `PodSpec` rather than deriving them from cgroup parameters.