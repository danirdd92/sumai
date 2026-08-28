---
title: "Running Agents on Kubernetes with Agent Sandbox"
originalUrl: "https://kubernetes.io/blog/2026/03/20/running-agents-on-kubernetes-with-agent-sandbox/"
publishDate: 2026-03-20T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "ai-agents", "orchestration", "security", "crd"]
---

# Architecture: The Stateful Agent Pattern
AI workloads are transitioning from stateless inference requests to long-running, autonomous agents. These agents represent isolated, stateful, singleton workloads requiring:
* **Persistent Identity**: For state management and multi-agent network discovery.
* **Secure Execution**: Isolated environments to safely run untrusted, LLM-generated code.
* **Aggressive Lifecycle Management**: The ability to scale to zero during long idle periods and rapidly resume.

Approximating this pattern using native Kubernetes primitives (e.g., a `StatefulSet` with `replicas: 1`, a Headless `Service`, and a dedicated `PersistentVolumeClaim` per agent) introduces unacceptable operational overhead and manifest bloat at scale.

# Agent Sandbox (SIG Apps)
`agent-sandbox` introduces the `Sandbox` CRD to natively orchestrate singleton, stateful agent runtimes without the overhead of combining multiple traditional primitives.

## Core Capabilities
1. **Strong Isolation**: Natively integrates with `RuntimeClass` to enforce boundary security using sandboxed runtimes (e.g., gVisor, Kata Containers).
2. **Lifecycle Management**: Built-in mechanisms to suspend idle agents to save compute resources, while maintaining state for resumption.
3. **Stable Network Identity**: Automatically provisions stable hostnames for seamless multi-agent communication.

### Example: Sandbox CRD
```yaml
apiVersion: sandbox.k8s.io/v1alpha1
kind: Sandbox
metadata:
  name: code-exec-agent
spec:
  runtimeClassName: gvisor # Enforces kernel isolation for untrusted execution
  suspend: false           # Toggle to suspend the agent during idle periods
  template:
    spec:
      containers:
      - name: workspace
        image: python:3.12-slim
        # Agent runtime entrypoint
```

## Eliminating Cold Starts: SandboxWarmPool
Standard pod provisioning latency (~1s) breaks the continuity of interactive or orchestrated agent loops. The Extensions API layer introduces `SandboxWarmPool` to maintain pre-provisioned, securely isolated environments. Orchestrators issue a `SandboxClaim` to instantly acquire a ready sandbox from the pool.

### Example: Warm Pool and Claim
```yaml
# 1. Maintain a pool of 10 pre-provisioned, isolated sandboxes
apiVersion: sandbox.k8s.io/v1alpha1
kind: SandboxWarmPool
metadata:
  name: agent-warm-pool
spec:
  minReady: 10
  template:
    spec:
      runtimeClassName: kata-containers
---
# 2. Instantly claim a pre-warmed sandbox, eliminating startup latency
apiVersion: sandbox.k8s.io/v1alpha1
kind: SandboxClaim
metadata:
  name: agent-session-123
spec:
  poolRef:
    name: agent-warm-pool
```

# Deployment
Agent Sandbox consists of core components, optional extensions, and language SDKs for programmatic orchestration.

```bash
export VERSION="v0.1.0" # Target release version

# Deploy Core Sandbox CRDs and Controller
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/manifest.yaml

# Deploy Extensions (SandboxWarmPool, SandboxClaim)
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/extensions.yaml

# Install Python SDK for agent orchestration
pip install k8s-agent-sandbox
```

# Trade-offs & Failure Modes
* **Resource Fragmentation**: Pre-warming environments via `SandboxWarmPool` trades cluster compute efficiency for latency reduction. Aggressive pooling without strict ResourceQuotas will lead to node starvation.
* **Storage Latency on Resume**: Resuming a suspended agent requires re-attaching stateful volumes. Depending on the underlying CSI driver and cloud provider, volume attachment latency can completely negate the speed benefits of state suspension.
* **Runtime Overhead**: Relying on Kata Containers or gVisor for tenant security introduces measurable CPU and network IO overhead compared to standard `runc` containers. Profiling agent IO requirements prior to production deployment is critical.