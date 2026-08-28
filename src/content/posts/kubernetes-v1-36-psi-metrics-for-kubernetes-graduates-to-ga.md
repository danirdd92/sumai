---
title: "Kubernetes v1.36: PSI Metrics for Kubernetes Graduates to GA"
originalUrl: "https://kubernetes.io/blog/2026/05/12/kubernetes-v1-36-psi-metrics-ga/"
publishDate: 2026-05-12T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "metrics", "linux", "performance"]
---
# Kubernetes v1.36: PSI Metrics GA

Pressure Stall Information (PSI) metrics have graduated to General Availability in Kubernetes v1.36. PSI provides granular visibility into resource saturation at the node, pod, and container levels by reporting the exact percentage of time tasks are stalled waiting for CPU, memory, or I/O.

Unlike standard resource utilization metrics, PSI explicitly quantifies scheduling delays and resource contention through:
* **Cumulative Totals**: Absolute time spent in a stalled state.
* **Moving Averages**: Time-windowed metrics (10s, 60s, 300s) to distinguish transient spikes from systemic resource exhaustion.

## Prerequisites and Configuration

PSI is natively supported in Kubernetes v1.36 without feature gates, but relies strictly on the underlying OS configuration:
* **Kernel**: Linux v4.20 or later. (Metrics are omitted on Windows nodes).
* **cgroups**: cgroup v2 is mandatory.
* **Boot Parameters**: Kernel must be compiled with `CONFIG_PSI=y` and booted without `psi=0`.

Metrics are exposed via the `/metrics/cadvisor` Kubelet endpoint for Prometheus integration, or via the Kubernetes Summary API.

## Architectural Overhead & Trade-offs

Tracking and collecting PSI metrics introduces minor but measurable overhead. Benchmarks by SIG Node on 4-core instances with high-density workloads (80+ pods) establish the following baseline costs:

* **Kernel-level Tracking Cost**: Enabling PSI at the OS level (`psi=1`) consumes an additional 0.9% to 3.1% of total node capacity (0.037 – 0.125 cores). Spikes under severe load reach up to 5.6% but decay rapidly.
* **Kubelet Aggregation Cost**: The Kubelet's periodic sweeps of the cgroup hierarchy add approximately 2.5% overhead (0.1 cores). Kubelet CPU utilization rarely exceeds 6.25% during active metric collection.

### Failure Mode: Phantom Zero-Metrics (Resolved in GA)
In earlier beta releases (v1.34), if the Kubelet attempted to collect PSI metrics on an OS where `psi=0`, it would emit empty/zero-valued metrics. This caused false-positive alerts in downstream monitoring systems. In v1.36, the Kubelet interrogates cgroup configurations directly to verify OS-level support, entirely dropping the metric emission if unsupported.

## Querying Real-Time PSI via Summary API

For immediate, ad-hoc diagnosis of container-level stalls, you can proxy directly to the Kubelet's Summary API. This bypasses the metric scraping interval but requires cluster-admin privileges.

```bash
CONTAINER_NAME="example-container"
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')

kubectl get --raw "/api/v1/nodes/${NODE_NAME}/proxy/stats/summary" | \
  jq '.pods[].containers[] | select(.name=="'"$CONTAINER_NAME"'") | {
    name, 
    cpu: .cpu.psi, 
    memory: .memory.psi, 
    io: .io.psi
  }'