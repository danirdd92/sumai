---
title: "Cilium 1.20: Gateway API ExternalAuth, TCPRoute/UDPRoute, ENI IPAM for IPv6, and more!"
originalUrl: "https://isovalent.com/blog/post/cilium-1-20/"
publishDate: 2026-07-31T12:40:00+00:00
source: "cilium"
tags: ["networking", "ebpf", "kubernetes", "security", "gateway-api"]
---

# Datapath & Performance

## Automatic Netkit Selection
Cilium dynamically selects the `netkit` datapath mode on kernels >= 6.8, bypassing `veth` pair overhead to achieve host-level throughput. It gracefully falls back to `veth` on legacy kernels, enabling heterogeneous node pools without segmented configurations.

**Implementation:**
```yaml
# Helm values
bpf:
  netkit: auto # Defaults to veth if kernel < 6.8
```

## Datapath Plugins
Extending the eBPF datapath previously required maintaining a hard fork. Cilium 1.20 exposes a stable `struct bpf_plugin` API, permitting custom eBPF program injection directly into the datapath pipeline.

## EndpointSlice Weights for Maglev
Maglev load balancing now supports weighted traffic distribution and graceful backend draining via `discovery.k8s.io/v1` EndpointSlices.

**Implementation:**
```yaml
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: maglev-backend-1
  annotations:
    service.cilium.io/weight: "0" # 0 drains active connections gracefully
# ...
```
*Trade-off:* Relies on manual or custom-controller management of annotations. Native Kubernetes controllers do not auto-weight EndpointSlices.

# Gateway API (v1.6)

## ListenerSets
Resolves ownership conflicts by decoupling `Gateway` listener provisioning (Platform team) from routing attachments (Application teams).

**Implementation:**
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shared-gateway
  namespace: default
spec:
  gatewayClassName: cilium
  allowedListeners:
    namespaces:
      from: Selector
      selector:
        matchLabels:
          gateway-access: "true"
---
apiVersion: gateway.networking.k8s.io/v1
kind: ListenerSet
metadata:
  name: delegated-listeners
  namespace: app-team-a
spec:
  parentRef:
    name: shared-gateway
    namespace: default
  listeners:
  - name: app-listener
    hostname: app.internal
    protocol: HTTP
    port: 80
```

## ExternalAuth Filter
Intercepts `HTTPRoute` traffic to enforce external OIDC/SSO (e.g., Dex, Keycloak) authentication flows before forwarding to backend services. 

## TCPRoute & UDPRoute
Enables Layer 4 load balancing through the Gateway API, centralizing ingress for non-HTTP workloads (DNS, telemetry, VoIP).

# Networking & Operations

## ENI IPAM Dual-Stack (IPv6)
AWS ENI IPAM mode natively provisions VPC-routable IPv6 addresses to pods. 
*Failure Mode:* Fails to initialize pods if the underlying AWS VPC CNI prefix delegation is exhausted or misconfigured for IPv6.

## Locality-Aware Traffic Distribution
Implements Kubernetes `trafficDistribution: PreferSameZone` and `PreferSameNode`.
*Nuance:* Operates as a soft preference. If local backends degrade, traffic falls back to the broader cluster to preserve availability over locality constraints.

## In-Place Multi-Pool IPAM Migration
Clusters using flat `cluster-pool` IPAM can migrate to `multi-pool` (per-namespace/tenant pools) without node rebuilds or workload re-IPing. Triggered via the operator flag `ipam.multi-pool.migration-enabled=true`.

## MCS-API Stable in ClusterMesh
Standardizes cross-cluster service discovery using the upstream Kubernetes Multi-Cluster Services API (`ServiceExport` and `ServiceImport`), replacing proprietary Cilium Global Services coupling.

# Security & Policy

## Ztunnel Sidecarless mTLS (Beta)
Supersedes older out-of-band mutual authentication. Ztunnel unifies identity authentication and encryption synchronously in the data path, preventing initial packet drops during handshakes.
*Configuration:* Opt-in via namespace label `istio.io/dataplane-mode: ambient`.

## Kubernetes ClusterNetworkPolicy (KCNP)
Implements upstream KCNP, enabling tier-based, cluster-scoped segmentation (e.g., un-overridable Admin default-denies).

**Implementation:**
```yaml
apiVersion: networking.k8s.io/v1alpha1
kind: ClusterNetworkPolicy
metadata:
  name: admin-deny-all
spec:
  tier: Admin
  subject:
    namespaceSelector: {}
  ingress:
  - action: Deny
```

## ClusterMesh Policy Entity
Introduces a native `cluster-mesh` entity for Cilium Network Policies, allowing cross-cluster ingress/egress rules without explicitly enumerating remote cluster names or relying on expansive label selectors.

**Implementation:**
```yaml
apiVersion: "cilium.io/v2"
kind: CiliumNetworkPolicy
metadata:
  name: allow-cross-cluster
spec:
  endpointSelector:
    matchLabels:
      app: backend
  ingress:
  - fromEntities:
    - cluster-mesh
```

## Granular Source IP Verification Bypass
Anti-spoofing is now bypassable per-pod for specific appliance workloads (NAT gateways, VPNs) using a strict two-level authorization gate:
1. Cluster Admin annotates the namespace: `cilium.io/allow-pod-source-ip-spoofing: "true"`
2. Pod owner explicitly requests the bypass capability in the pod spec.

## Hubble Policy Correlation
Audit Mode logs now directly map drops to the specific network policy (or absence thereof) responsible for the verdict, eliminating ambiguity when previewing default-deny configurations.

## Policy Identity Aggregation & CNI Shrink
- **Identity Aggregation:** Policy maps now compress broad entities (`world`, `remote-node`) using wildcard identities. This exponentially reduces BPF map memory utilization and churn in high-scale clusters.
- **CNI Binary Shrink:** The `cilium-cni` binary footprint was reduced by 80%, accelerating node bootstrap times and minimizing image transfer overhead.