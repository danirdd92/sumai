---
title: "Announcing Ingress2Gateway 1.0: Your Path to Gateway API"
originalUrl: "https://kubernetes.io/blog/2026/03/20/ingress2gateway-1-0-release/"
publishDate: 2026-03-20T11:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "networking", "gateway-api", "migration"]
---

With Ingress-NGINX scheduled for retirement in March 2026, migrating to the Gateway API is an operational requirement. The Gateway API provides a modular, RBAC-native model, unlike the legacy Ingress API which relied heavily on implementation-specific, unstructured annotations.

Ingress2Gateway 1.0 is a migration utility that translates legacy Ingress resources to Gateway API manifests. It supports over 30 common Ingress-NGINX annotations (CORS, TLS, regex matching, rewrites) and uses integration tests to verify runtime routing behavior equivalence. 

## Architecture and Migration Workflow

Migration is not a one-click automated process. The tool operates on a translation and validation model:

1. **Translation**: Maps Ingress resources and annotations to standard Gateway API objects (`Gateway`, `HTTPRoute`).
2. **Identification**: Flags unsupported configuration snippets or annotations requiring manual intervention via stdout logs.
3. **Emitter-Specific Extensions**: By default, it outputs standard Gateway API YAML. Using specific emitters (e.g., `--emitter envoy-gateway`), it can generate implementation-specific configurations for behaviors not covered by the core standard.

### Installation & Execution

```bash
# Install via Homebrew or Go
brew install ingress2gateway
# go install github.com/kubernetes-sigs/ingress2gateway@v1.0.0

# Translate specific manifests
ingress2gateway print --input-file legacy-ingress.yaml --providers=ingress-nginx > gwapi.yaml

# Translate a live cluster namespace
ingress2gateway print --namespace my-api --providers=ingress-nginx > gwapi.yaml

# Translate using a specific emitter for extended configuration (e.g., Envoy, Kgateway)
ingress2gateway print --input-file legacy-ingress.yaml --providers=ingress-nginx --emitter envoy-gateway > gwapi.yaml
```

## Translation Nuances and Failure Modes

The generated `gwapi.yaml` **must be manually reviewed**. Ingress2Gateway makes best-effort assumptions during translation that may conflict with your production requirements.

### Translation Trade-offs

Consider an Ingress with the following NGINX annotations:

```yaml
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "1G"
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "1"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "1"
    nginx.ingress.kubernetes.io/enable-cors: "true"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Request-Id: $req_id";
```

When translating these parameters, Ingress2Gateway handles them with varying degrees of fidelity:

1. **Regex Matching**: Ingress-NGINX regex matches are case-insensitive prefix matches. The tool translates a path like `/users/(\d+)` to `(?i)/users/(\d+).*`. 
   * **Fix:** Manually remove `(?i)` and `.*` if exact, case-sensitive matching is required.
2. **Timeouts**: Ingress-NGINX uses TCP-level timeouts. The tool performs a best-effort mapping to the Gateway API's HTTP-level `timeouts.request`. 
   * **Fix:** Review the generated timeout values and adjust them to your application's actual HTTP timeout requirements.
3. **Dropped Configuration**: `proxy-body-size` and `configuration-snippet` do not have direct 1:1 Gateway API equivalents and are dropped with warnings. 
   * **Fix:** Rely on the target Gateway controller's default buffering limits, or use an implementation-specific `--emitter` to capture the body size logic. Custom headers (from snippets) must be manually recreated using Gateway API `RequestHeaderModifier` filters.
4. **URL Normalization**: Gateway API lacks standard URL normalization configuration (RFC 3986). Normalization behavior will depend entirely on the underlying Gateway controller implementation (Envoy, Istio, etc.). Test this explicitly.
5. **Implicit Redirects**: To match NGINX defaults, the tool automatically generates a port 80 listener and an `HTTPRoute` with a `RequestRedirect` filter to enforce HTTPS. 
   * **Fix:** Remove the HTTP listener and route entirely if serving any HTTP traffic is strictly prohibited.

### Refined `HTTPRoute` Output

After manual review and correction of the tool's output, a production-ready `HTTPRoute` should look similar to this:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-ingress-my-host-example-com
  namespace: my-ns
spec:
  hostnames:
  - my-host.example.com
  parentRefs:
  - name: nginx
    port: 443
  rules:
  - backendRefs:
    - name: website-service
      port: 80
    filters:
    - type: CORS
      cors:
        allowCredentials: true
        allowHeaders: ["DNT", "Keep-Alive", "User-Agent", "X-Requested-With", "If-Modified-Since", "Cache-Control", "Content-Type", "Range", "Authorization"]
        allowMethods: ["GET", "PUT", "POST", "DELETE", "PATCH", "OPTIONS"]
        allowOrigins: ['*']
        maxAge: 1728000
    matches:
    - path:
        type: RegularExpression
        value: /users/(\d+) # Cleaned from the auto-generated (?i)/users/(\d+).*
    timeouts:
      request: 3s # Adjusted from generic best-effort translation
```

## Production Rollout Strategy

Migrating networking infrastructure requires a phased approach to limit blast radius. Do not perform an immediate cutover.

1. **Verify Defaults**: Ensure the new Gateway controller's baseline defaults (e.g., maximum body size, timeout limits) align with the dropped NGINX annotations.
2. **Parallel Deployment**: Deploy the validated `Gateway` and `HTTPRoute` manifests alongside the existing legacy `Ingress` objects in the same cluster.
3. **Traffic Splitting**: Use DNS weighting, external cloud load balancers, or your platform's traffic-splitting features to shift a small percentage of traffic to the new Gateway infrastructure.
4. **Decommission**: Once 100% of traffic routes through the Gateway API controllers successfully and metrics are stable, delete the legacy `Ingress` resources and uninstall the Ingress-NGINX controller.