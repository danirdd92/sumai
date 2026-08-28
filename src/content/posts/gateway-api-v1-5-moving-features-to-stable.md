---
title: "Gateway API v1.5: Moving features to Stable"
originalUrl: "https://kubernetes.io/blog/2026/04/21/gateway-api-v1-5/"
publishDate: 2026-04-21T08:30:00-08:00
source: "kubernetes"
tags: ["kubernetes", "networking", "tls", "gateway-api"]
---

Gateway API v1.5 promotes six routing and security features to the Standard (Stable) channel. The release focuses on scaling Gateway configurations, route-level CORS management, and expanding mutual TLS (mTLS) capabilities for both frontend and backend connections.

### ListenerSet

`ListenerSet` allows listeners to be defined independently and merged onto a target `Gateway` object. This solves coordination bottlenecks in multi-tenant environments where platform and application teams modify the same proxy. It also bypasses the hard limit of 64 listeners per `Gateway`, enabling large-scale deployments with thousands of hostnames.

**Implementation Nuance:** The `listener` field on the `Gateway` resource remains mandatory. A `Gateway` must define at least one valid listener itself before `ListenerSet` resources can append to it.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shared-gateway
spec:
  gatewayClassName: internal-proxy
  listeners:
    - name: default-http
      protocol: HTTP
      port: 80
---
apiVersion: gateway.networking.k8s.io/v1
kind: ListenerSet
metadata:
  name: team-a-listeners
spec:
  parentRef:
    name: shared-gateway
  listeners:
    - name: https-team-a
      protocol: HTTPS
      port: 443
      hostname: a.example.com
      tls:
        certificateRefs:
          - name: a-cert
```

### TLSRoute

`TLSRoute` routes TCP streams based on the Server Name Indication (SNI) presented during the TLS handshake. The Gateway listener operates in one of two modes:

1.  **Passthrough:** Proxies the encrypted byte stream directly to the backend. The Gateway has no access to unencrypted data or private keys. Essential for strict end-to-end encryption or backend-terminated client authentication.
2.  **Terminate:** Terminates the TLS session centrally at the Gateway and forwards a plain-text TCP stream to the backend.

**Failure Mode:** Upgrading to v1.5 Standard will break existing Experimental `TLSRoute` configurations (`v1alpha2` or `v1alpha3`). You must migrate existing `TLSRoute` resources to the `v1` API group to restore routing.

```yaml
# Example: Passthrough Mode
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: secure-gateway
spec:
  gatewayClassName: example-class
  listeners:
    - name: tls-passthrough
      protocol: TLS
      port: 8443
      tls:
        mode: Passthrough
---
apiVersion: gateway.networking.k8s.io/v1
kind: TLSRoute
metadata:
  name: secure-backend-route
spec:
  parentRefs:
    - name: secure-gateway
      sectionName: tls-passthrough
  hostnames:
    - "secure.example.com"
  rules:
    - backendRefs:
        - name: secure-backend-svc
          port: 8443
```

### HTTPRoute CORS Filter

Cross-Origin Resource Sharing (CORS) is now natively configured via `HTTPRoute` filters, removing the dependency on vendor-specific annotations. 

**Configuration Parameters:**
*   `allowOrigins`: Accepts strict URLs, a global wildcard (`*`), or subdomain wildcards (`https://*.example.com`).
*   Additional granular controls: `allowCredentials`, `allowMethods`, `allowHeaders`, `exposeHeaders`, `maxAge`.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api-cors-route
spec:
  parentRefs:
    - name: public-gateway
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      filters:
        - cors:
            allowOrigins:
              - "https://*.frontend.example.com"
            allowMethods: ["GET", "OPTIONS"]
            allowCredentials: true
            maxAge: 3600
            type: CORS
      backendRefs:
        - name: api-backend
          port: 8080
```

### Client Certificate Validation (Frontend mTLS)

Gateways can enforce frontend mTLS by validating client certificates against trusted Certificate Authorities (CAs). Validation is defined globally per-Gateway or overridden per-port via the `frontendValidation` struct.

**Modes:**
*   `AllowValidOnly` (Default): Rejects connections failing CA validation.
*   `AllowInsecureFallback`: Accepts connections lacking a certificate or failing validation. 
    *   *Drawback:* This delegates authorization entirely to the backend service. Misconfiguration heavily risks exposing services to unauthenticated traffic.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: mtls-gateway
spec:
  gatewayClassName: internal-lb
  tls:
    frontend:
      default:
        validation:
          caCertificateRefs:
            - kind: ConfigMap
              name: enterprise-ca-bundle
      perPort:
        - port: 8443
          tls:
            validation:
              caCertificateRefs:
                - kind: ConfigMap
                  name: legacy-ca-bundle
              mode: AllowInsecureFallback
```

### Certificate Selection for TLS Origination

To establish mTLS with upstream backends, the Gateway must present a client certificate. This is defined using `tls.backend.clientCertificateRef` on the `Gateway` resource.

**Architectural Trade-off:** This configuration dictates the client certificate used for *all* upstream connections managed by that specific Gateway. Fine-grained, route-specific upstream mTLS certificates are not supported via this mechanism.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: egress-gateway
spec:
  gatewayClassName: egress-proxy
  tls:
    backend:
      clientCertificateRef:
        kind: Secret
        name: gateway-upstream-cert
```

### ReferenceGrant Promotion

`ReferenceGrant`, which facilitates secure cross-namespace references (such as routing to a backend in a different namespace), has been promoted to `v1` (Stable) with no breaking API changes.