---
title: "Cilium 1.19, Network Policy enhancements, Multi Pool IPAM goes stable, IPv6 progress, and more!"
originalUrl: "https://isovalent.com/blog/post/cilium-119-ztunnel-transparent-encryption-multi-pool-ipam-goes-stable-ipv6-progress-and-more?&utm_medium=referral&utm_campaign=cilium-blog"
publishDate: 2026-02-24T12:40:00+00:00
source: "cilium"
tags: ["kubernetes", "networking", "security", "ebpf", "cilium"]
---
Cilium 1.19 introduces core improvements to datapath performance, Multi-Pool IPAM, advanced network policies, and observability.

## Connectivity & Datapath

### BPF Host Routing with IPsec
IPsec encryption and BPF Host Routing can now be enabled simultaneously. This combination bypasses legacy Linux routing and iptables to reduce overhead while retaining Layer 3 encryption for node-to-node traffic.

```yaml
# Helm configuration
bpf:
  hostLegacyRouting: true
encryption:
  type: ipsec
```

### Gateway API v1.4.0 & GRPCRoute
Cilium fully supports the Gateway API v1.4.0 specification, adding `GRPCRoute` as a first-class resource. This enables native gRPC routing for ingress and fulfills GAMMA mesh conformance requirements for east-west traffic.

### IPv6 L2 Announcements & Underlay
- **L2 Announcements**: Service VIPs (LoadBalancer/ExternalIPs) can now be advertised over IPv6 using Neighbor Discovery Protocol (NDP), replicating existing ARP functionality for IPv6-only or dual-stack environments.
- **Dual-Stack Underlay**: VXLAN or Geneve tunnels can now route over an IPv6 underlay in dual-stack clusters. MTU calculations are automatically adjusted based on the selected encapsulation protocol. Enabled by setting the `underlay` protocol to IPv6 in Helm.

### BGP Enhancements
BGP configuration has fully migrated to `cilium.io/v2` CRDs. The legacy `CiliumBGPPeeringPolicy` is removed.
- **Interface Advertisement**: IPs assigned to local interfaces (e.g., loopbacks) can be advertised to support multi-homing.
- **Source IP Override**: The `sourceInterface` transport configuration can explicitly bind BGP sessions to a stable interface.
- **Zero-Endpoint Route Withdrawal**: When `externalTrafficPolicy: Cluster` is set, Cilium can automatically withdraw Service VIP routes if a Service has zero active endpoints, improving anycast failover.

## Multi-Pool IPAM (Stable)

Multi-Pool IPAM graduates to stable, functioning as a strict policy-driven IP allocation system.

- **Label Selectors & Precedence**: IP pools can be assigned via pod/namespace annotations or pool label selectors. A strict `require-pool-match` annotation enforces matching, preventing unintended fallback to the default pool.
- **IPsec Compatibility**: IPsec encryption is fully supported for pods communicating across secondary IP pools in direct routing mode.
- **Masquerade Granularity**:
  - eBPF masquerade can be forced for pod-to-remote-node traffic to normalize source IPs across subnets.
  - Multi-Pool ranges can be explicitly excluded from masquerade using `--only-masquerade-default-pool` or per-pool annotations. This preserves pod IPs for downstream routing and firewalling.

## Security & Policy

### Host Firewall for VRRP and IGMP
Host firewall policies can now match VRRP (keepalived) and IGMP (multicast) traffic. Because these protocols operate below the transport layer, `toPorts` rules have been extended to allow protocol-only matching without port specifications.

```yaml
apiVersion: "cilium.io/v2"
kind: CiliumClusterwideNetworkPolicy
metadata:
  name: "allow-vrrp"
spec:
  nodeSelector:
    matchLabels:
      type: egress-worker
  egress:
    - toEntities:
        - world
      toPorts:
        - rules:
            vrrp: true # Protocol-level match without ports
```

### Fast-Fail Egress Denies (ICMP Unreachable)
Instead of silently dropping traffic denied by egress policies (which causes application timeouts), Cilium can be configured to immediately return an ICMP "Destination Unreachable" response.

```yaml
# Helm configuration
policyDenyResponse: icmp
```

### DNS Wildcards (`**.`)
Network policies now support the `**.` prefix to match cascaded subdomains spanning multiple DNS labels.
- `*.cilium.io` matches `app.cilium.io` but not `test.app.cilium.io`.
- `**.cilium.io` matches `app.cilium.io`, `test.app.cilium.io`, and deeper layers, but explicitly excludes the root domain (`cilium.io`).

### Ztunnel Integration (Beta)
Cilium adds initial support for Istio's Ztunnel as a transparent encryption mode. Cilium operates as the control plane (workload discovery, certificate issuance) and uses iptables in the pod network namespace to transparently route traffic to a local Ztunnel DaemonSet for Layer 4 mTLS.

## Observability

### IP Packet Tracing
Specific packets can be traced through the datapath via IPv4 IP Options (e.g., Stream Identifier Option 136) and emitted to Hubble. This allows tracing a single flow across NAT boundaries and overlays without enabling verbose global logging. Configured via `bpf.monitorTraceIPOption=136`.

### Hubble Enhancements
- **FlowLog Aggregation**: Hubble can aggregate flow logs by fields like namespace, service, or verdict over a specified interval, drastically reducing log export volume.
- **Encryption Status Filtering**: Flows can be filtered by `encrypted` vs `unencrypted` to audit IPsec/WireGuard deployment states.
- **VRRP/IGMP Parsing**: Hubble now explicitly classifies and logs VRRP and IGMP traffic instead of tagging it as "unknown."

## Platform & Deprecations
- **OCI Helm Charts**: Charts are now distributed via OCI at `oci://quay.io/cilium/charts/cilium`.
- **Policy Fields**: `FromRequires` and `ToRequires` are completely rejected and will cause policy validation errors.
- **Kafka Policies**: Kafka protocol matching is deprecated and slated for removal in v1.20.
- **Cluster Mesh**: Policy selectors now default to the local cluster unless explicitly cross-cluster (`policy-default-local-cluster`).