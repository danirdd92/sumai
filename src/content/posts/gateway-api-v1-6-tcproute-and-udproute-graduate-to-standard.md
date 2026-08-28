---
title: "Gateway API v1.6: TCPRoute and UDPRoute Graduate to Standard"
originalUrl: "https://kubernetes.io/blog/2026/08/03/gateway-api-v1-6-release/"
publishDate: 2026-08-03T08:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "networking", "gateway-api", "routing"]
---

Gateway API v1.6 stabilizes layer 4 routing and formalizes a dedicated API boundary for experimental resources.

## TCPRoute and UDPRoute Graduate to Standard

`TCPRoute` and `UDPRoute` have reached GA stability in the `v1` API version (the `v1alpha2` versions are deprecated). These resources enable raw L4 routing based strictly on protocol and port, providing a standardized ingress mechanism for databases, DNS, IoT telemetry, and gaming workloads without requiring L7 inspection or implementation-specific CRDs.

**Implementation**
A `Gateway` defines a listener specifying the protocol and port. A corresponding `TCPRoute` or `UDPRoute` attaches to this listener and defines the backend forwarding rules.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: example-l4-gateway
spec:
  gatewayClassName: example-class
  listeners:
    - name: l4-listener
      protocol: TCP # Or UDP
      port: 12345
      allowedRoutes:
        kinds:
          - kind: TCPRoute # Or UDPRoute
---
apiVersion: gateway.networking.k8s.io/v1
kind: TCPRoute # Or UDPRoute
metadata:
  name: l4-app-route
spec:
  parentRefs:
    - name: example-l4-gateway
      sectionName: l4-listener
  rules:
    - backendRefs:
        - name: backend-service
          port: 6000
```

*(Note: Omitting `sectionName` and `port` from `parentRefs` attaches the route to every listener of the matching protocol on the Gateway).*

## Experimental API Group Boundary

To strictly delineate production-ready APIs from experimental features, experimental resources have been moved to a distinct API group: `gateway.networking.x-k8s.io`. 

These resources now carry an `X` prefix (e.g., `XBackend`, `XMesh`). Upon graduation to Standard, the resource drops the prefix and moves to the standard `gateway.networking.k8s.io` group.

## New Experimental Resource: XBackend

`XBackend` is introduced as a general-purpose decorator for `Service` and other backend types. It is designed to extend backend functionality without complicating the highly stable core `Service` API.

**ExternalHostname Support**
The first iteration of `XBackend` introduces support for `ExternalHostname` destinations. This enables routing traffic to external endpoints (e.g., managed cloud services or APIs), which is highly relevant for formalizing egress traffic patterns.

**Security Trade-off:** `ExternalHostname` routing introduces the risk of confused deputy attacks. Because of this, it is explicitly excluded from standard `Service` support in the Gateway API. In `XBackend`, it is classified as an Extended/Optional feature, forcing cluster administrators to explicitly opt-in and accept the security tradeoffs.

```yaml
# Gateway terminates incoming TLS
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
spec:
  listeners:
    - name: https
      protocol: HTTPS
      tls:
        certificateRefs:
          - name: gateway-cert
---
# XBackend defines the external destination
apiVersion: gateway.networking.x-k8s.io/v1alpha1
kind: XBackend
metadata:
  name: external-ai-api
spec:
  type: ExternalHostname
  externalHostname:
    hostname: api.ai-provider.com
---
# Route directs traffic to the XBackend
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
spec:
  rules:
    - backendRefs:
        - name: external-ai-api
          kind: XBackend
          group: gateway.networking.x-k8s.io
```

Future development of `XBackend` aims to absorb application-specific configurations currently difficult to manage at the route level, including session persistence, retries, and TLS origination.