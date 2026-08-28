---
title: "Kubernetes v1.36: Deprecation and removal of Service ExternalIPs"
originalUrl: "https://kubernetes.io/blog/2026/05/14/kubernetes-v1-36-deprecation-and-removal-of-service-externalips/"
publishDate: 2026-05-14T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "security", "networking", "deprecation"]
---

Kubernetes 1.36 formally deprecates the `Service.spec.externalIPs` field. The API design inherently assumes a fully trusted cluster environment, enabling unprivileged users to claim arbitrary IP addresses and intercept traffic (CVE-2020-8554). Because this design flaw cannot be patched without breaking the API's intended behavior, the feature is being removed entirely.

### Scope of Deprecation
This deprecation is strictly limited to the `Service.spec.externalIPs` field. It **does not** affect:
* The `Node.status.addresses` field (where type is `ExternalIP`).
* The `EXTERNAL-IP` column displayed by `kubectl get svc` for `type: LoadBalancer` services.

### Immediate Action
To proactively secure clusters before the feature is physically removed from `kube-proxy`, enable the `DenyServiceExternalIPs` admission controller. This enforces an "insecure by default" prevention mechanism.

---

## Migration Patterns & Architectural Alternatives

If your non-cloud clusters rely on `externalIPs` for load-balancer-like behavior, you must migrate to patterns that separate IP address allocation (privileged) from Service definition (unprivileged).

### 1. MetalLB (Recommended for Bare Metal)
Using a third-party controller like MetalLB shifts IP assignment to the cluster administrator. The admin defines authorized IP pools, and MetalLB ensures exclusive, collision-free assignment.

**Administrator Configuration (IP Pool):**
```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: production
  namespace: metallb-system
spec:
  addresses:
  - 192.0.2.0/24
  autoAssign: true
```

**Developer Usage:**
Users request standard `LoadBalancer` services. To maintain legacy behavior (requesting a specific IP), the deprecated but temporarily supported `loadBalancerIP` field can be used, provided the requested IP is within the admin's pool.
```yaml
apiVersion: v1
kind: Service
metadata:
  name: example-service
spec:
  type: LoadBalancer
  selector:
    app: example-app
  ports:
  - port: 80
  loadBalancerIP: "192.0.2.4" # Optional: Requests specific IP from the pool
```

### 2. Gateway API (Strategic/Modern)
Gateway API decouples infrastructure provisioning from application routing. Cluster admins manage the `Gateway` (and its bound IP), while developers manage `HTTPRoute` resources. This enforces RBAC inherently.

```yaml
# Admin-managed: Provisions the IP and Gateway
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: example-gateway
spec:
  gatewayClassName: example-gateway-class
  addresses:
  - type: IPAddress
    value: "192.0.2.4"
---
# Developer-managed: Routes traffic from the Gateway to the Service
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: example-route
spec:
  parentRefs:
  - name: example-gateway
  rules:
  - backendRefs:
    - name: example-svc
      port: 80
```

### 3. Manual Status Patching (Stopgap)
**Trade-off:** This is a high-friction workaround. It mitigates the vulnerability by shifting the IP declaration from the user-editable `.spec` to the system-controlled `.status`.

Because `.status` cannot be set during resource creation, it requires a two-step process using a dummy load balancer class to prevent real controllers from acting on it.

**Step 1: Create the Service**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: manual-lb-svc
spec:
  loadBalancerClass: non-existent-class # Prevents actual LB controllers from reconciling
  type: LoadBalancer
  selector:
    app: target-app
  ports:
  - port: 80
```

**Step 2: Patch the Status (Requires elevated RBAC)**
```bash
kubectl patch service manual-lb-svc --subresource=status --type=merge \
  -p '{"status":{"loadBalancer":{"ingress":[{"ip":"192.0.2.4"}]}}}'
```

---

## Removal Timeline

*   **v1.36 (Current):** Field deprecated. API emits warnings on use.
*   **v1.40 (~1 year):** `kube-proxy` support disabled by default (opt-in available for extended migrations).
*   **v1.43 (~2 years):** Feature code fully purged. No opt-in possible.