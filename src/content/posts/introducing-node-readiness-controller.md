---
title: "Introducing Node Readiness Controller"
originalUrl: "https://kubernetes.io/blog/2026/02/03/introducing-node-readiness-controller/"
publishDate: 2026-02-03T10:00:00+08:00
source: "kubernetes"
tags: ["kubernetes", "scheduling", "infrastructure", "reliability"]
---

The Kubernetes core `Ready` condition is binary and often insufficient for nodes requiring complex bootstrapping (e.g., CNI agents, storage drivers, GPU firmware). The **Node Readiness Controller** introduces the `NodeReadinessRule` (NRR) API to declaratively manage node taints based on custom infrastructure health signals, preventing workloads from scheduling on unready nodes.

### Architecture and Core Mechanisms
The controller operates by dynamically applying and removing node taints in response to standard Node Conditions. It does not perform health checks itself, decoupling the readiness evaluation from enforcement. This requires integration with condition reporters like:
*   **Node Problem Detector (NPD):** Exposes custom script or daemon health as node conditions.
*   **Readiness Condition Reporter:** A lightweight HTTP-polling agent provided by the project for patching node conditions.

By managing scheduling gates via taints, operators can enforce heterogeneous readiness criteria across different node groups (e.g., verifying specialized drivers exclusively on GPU-equipped node pools).

### Enforcement Modes
The controller provides two operational models depending on the dependency's lifecycle:
1.  **Continuous Enforcement:** Actively monitors the configured condition throughout the node's lifecycle. If the underlying dependency fails post-initialization, the node is immediately re-tainted, halting new pod placement.
2.  **Bootstrap-only Enforcement:** Designed for one-time initialization procedures (e.g., image pre-pulling, hardware provisioning). Monitoring ceases once the initial condition is met, and the taint is permanently removed.

### Operational Safety
To prevent accidental cluster-wide scheduling lockouts when introducing new rules, the controller implements a **Dry Run** mode. This allows operators to validate rules by logging intended actions and updating the rule's status to reflect affected nodes without actually applying the taints.

### Implementation Example: CNI Bootstrapping
The following `NodeReadinessRule` enforces that worker nodes remain unschedulable until the CNI agent is fully functional. The controller monitors a custom condition (`cniplugin.example.net/NetworkReady`) and removes the specified taint only when the condition evaluates to `True`.

```yaml
apiVersion: readiness.node.x-k8s.io/v1alpha1
kind: NodeReadinessRule
metadata:
  name: network-readiness-rule
spec:
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/worker: ""
  conditions:
    - type: "cniplugin.example.net/NetworkReady"
      requiredStatus: "True"
  taint:
    key: "readiness.k8s.io/acme.com/network-unavailable"
    value: "pending"
    effect: "NoSchedule"
  enforcementMode: "bootstrap-only"