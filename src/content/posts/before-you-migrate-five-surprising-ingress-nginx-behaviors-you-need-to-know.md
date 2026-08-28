---
title: "Before You Migrate: Five Surprising Ingress-NGINX Behaviors You Need to Know"
originalUrl: "https://kubernetes.io/blog/2026/02/27/ingress-nginx-before-you-migrate/"
publishDate: 2026-02-27T07:30:00-08:00
source: "kubernetes"
tags: ["kubernetes", "ingress-nginx", "gateway-api", "networking", "migration"]
---
Ingress-NGINX reaches end-of-life in March 2026. Migrating to the Gateway API requires understanding several implicit Ingress-NGINX behaviors to avoid production outages. A naive 1:1 API translation will often result in dropped traffic or unintended routing. 

*(Note: This applies to the community-maintained `ingress-nginx`, not F5's `kubernetes-ingress`.)*

### 1. Regex Matching is Implicitly Case-Insensitive and Prefix-Based

**The Behavior:**
When using the `nginx.ingress.kubernetes.io/use-regex: "true"` annotation, Ingress-NGINX evaluates regular expressions as **case-insensitive prefix matches**. A path defined as `/[A-Z]{3}` will successfully route a request for `/uuid/some/path` because `uui` matches `[A-Z]{3}` case-insensitively, and it acts as a valid prefix.

**Migration Risk:**
Gateway API `RegularExpression` matches are implementation-specific, but most Envoy-based controllers (Istio, Envoy Gateway) enforce **full, case-sensitive matches**. A direct translation will result in 404s for clients relying on the implicit prefix or case-insensitivity.

**Gateway API Implementation:**
To preserve Ingress-NGINX behavior, explicitly define the case-insensitive flag `(?i)` and wildcard suffix `.*` in your HTTPRoute.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: regex-match-route
spec:
  hostnames:
    - regex-match.example.com
  rules:
    - matches:
        - path:
            type: RegularExpression
            value: "(?i)/[a-zA-Z]{3}.*"
      backendRefs:
        - name: backend-service
          port: 8000
```

### 2. Regex Evaluation Bleeds Across Ingress Resources by Hostname

**The Behavior:**
If *any* Ingress resource for a specific `host` contains the `nginx.ingress.kubernetes.io/use-regex: "true"` annotation, Ingress-NGINX evaluates **all paths across all Ingress resources for that host** as regular expressions. This applies globally, overriding `Exact` or `Prefix` pathTypes in completely separate manifests. 

For example, an `Exact` path of `/Header` in a non-regex Ingress will match a request to `/headers` if another Ingress for the same hostname enables regex (due to the implicit case-insensitive prefix matching discussed above).

**Migration Risk:**
Gateway API strictly isolates routing logic. `Exact` and `Prefix` matches are explicitly enforced. Requests relying on global regex bleed will return 404 Not Found.

**Gateway API Implementation:**
Audit all `Exact` and `Prefix` paths on hostnames where `use-regex` is active. Convert them to explicit `RegularExpression` matches or correct the underlying typos to allow strict matching.

```yaml
# Preserving the loose matching caused by regex bleed
- matches:
    - path:
        type: RegularExpression
        value: "(?i)/Header.*"
```

### 3. `rewrite-target` Silently Enables Global Regex Evaluation

**The Behavior:**
Adding the `nginx.ingress.kubernetes.io/rewrite-target` annotation to an Ingress implicitly enables `use-regex: "true"` for that host. This triggers the host-wide regex bleed described in #2, converting all `Exact` and `Prefix` paths into case-insensitive prefix regular expressions.

**Migration Risk:**
Gateway API handles rewrites via the `URLRewrite` filter, which does not alter underlying match mechanics. Paths translated as `Exact` matches will strictly enforce case and exact length, breaking clients that previously relied on silent regex coercion.

**Gateway API Implementation:**
When translating `rewrite-target` to a Gateway API `URLRewrite` filter, evaluate if the routing logic relies on regex coercion. If so, update the match `type` to `RegularExpression`.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: rewrite-route
spec:
  hostnames:
    - rewrite.example.com
  rules:
    - matches:
        - path:
            type: RegularExpression
            value: "(?i)/IP.*"
      filters:
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplaceFullPath
              replaceFullPath: /uuid
      backendRefs:
        - name: backend-service
          port: 8000
```

### 4. Implicit 301 Redirects for Missing Trailing Slashes

**The Behavior:**
When an Ingress defines an `Exact` or `Prefix` path terminating in a slash (e.g., `/my-path/`), a request missing the trailing slash (`/my-path`) does not return a 404. Instead, Ingress-NGINX automatically issues a `301 Moved Permanently` redirecting the client to `/my-path/`. 

**Migration Risk:**
Conformant Gateway API implementations do not synthesize redirects. Requests lacking the trailing slash will return a 404 Not Found, potentially breaking downstream clients or SEO configurations relying on the 301 response.

**Gateway API Implementation:**
Explicitly define redirect behavior using a `RequestRedirect` filter on a dedicated match rule.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: trailing-slash-route
spec:
  hostnames:
    - example.com
  rules:
    # Explicitly handle the missing slash with a 301 redirect
    - matches:
        - path:
            type: Exact
            value: "/my-path"
      filters:
        - type: RequestRedirect
          requestRedirect:
            statusCode: 301
            path:
              type: ReplaceFullPath
              replaceFullPath: /my-path/
    # Handle the strictly matched normalized path
    - matches:
        - path:
            type: Exact
            value: "/my-path/"
      backendRefs:
        - name: backend-service
          port: 8000
```

### 5. Pre-Match URL Normalization 

**The Behavior:**
Ingress-NGINX normalizes URLs (per RFC 3986) *before* evaluating routing rules. This includes resolving directory traversals (`/path/../uuid` becomes `/uuid`), removing self-references (`/./`), and deduplicating slashes (`//uuid` gets a 301 redirect to `/uuid`). 

**Migration Risk:**
While many Envoy-based Gateway API implementations perform path normalization by default, it is not strictly mandated by the Gateway API specification. If your backend applications or WAF policies rely on the ingress controller sanitizing paths, migrating to an implementation that defers normalization to the backend introduces routing failures or security vulnerabilities.

**Gateway API Implementation:**
Verify the normalization capabilities of your specific Gateway API implementation. If required, configure proxy-specific settings (e.g., Envoy's `normalize_path` and `merge_slashes` parameters) via Gateway API extension policies to guarantee consistent behavior.