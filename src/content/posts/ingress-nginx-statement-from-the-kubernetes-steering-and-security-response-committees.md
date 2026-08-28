---
title: "Ingress NGINX: Statement from the Kubernetes Steering and Security Response Committees"
originalUrl: "https://kubernetes.io/blog/2026/01/29/ingress-nginx-statement/"
publishDate: 2026-01-29T00:00:00+00:00
source: "kubernetes"
tags: ["kubernetes", "ingress", "networking", "security"]
---

# Ingress NGINX End-of-Life: March 2026

Kubernetes is retiring the Ingress NGINX controller in March 2026. After this date, the project will receive zero updates, including critical security patches.

**Architectural Context:** The deprecation is driven by insurmountable technical debt and fundamental design decisions that intrinsically exacerbate security flaws. The project lacks the maintainer bandwidth (historically 1-2 part-time contributors) required to safely maintain it for the ~50% of cloud-native environments currently relying on it.

**Failure Mode:** Existing deployments will not break upon retirement. They will silently continue functioning, leaving environments inherently vulnerable to unpatched exploits unless actively migrated. 

## Audit Requirement

Verify cluster dependency on Ingress NGINX (requires cluster administrator permissions):

```bash
kubectl get pods --all-namespaces --selector app.kubernetes.io/name=ingress-nginx
```

## Migration Strategies

There are no direct, drop-in replacements. Migration requires dedicated engineering cycles to translate existing `Ingress` resources and custom NGINX annotations.

### 1. Gateway API (Recommended)
The upstream standard for Kubernetes service networking. It decouples infrastructure configuration (`Gateway`) from application routing (`HTTPRoute`).

**Example Target Architecture (`HTTPRoute`):**
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: application-route
spec:
  parentRefs:
  - name: internal-gateway # Typically managed by infrastructure teams
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /api
    backendRefs:
    - name: backend-service
      port: 8080
```

### 2. Alternative Ingress Controllers
If Gateway API adoption is not feasible within the timeframe, migrate to actively maintained third-party Ingress controllers. Viable alternatives include Envoy-based controllers (e.g., Contour, Emissary), Traefik, or HAProxy Ingress. Ensure the chosen alternative supports the specific routing requirements and annotations currently in use.