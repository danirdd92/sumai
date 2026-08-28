---
title: "Reconciling the Past: Correcting Records for Unfixed Kubernetes CVEs"
originalUrl: "https://kubernetes.io/blog/2026/05/26/reconciling-unfixed-kubernetes-cves/"
publishDate: 2026-05-26T09:30:00-08:00
source: "kubernetes"
tags: ["kubernetes", "security", "cve", "architecture", "rbac"]
---
On June 1, 2026, the Kubernetes Security Response Committee (SRC) corrected CVE records for four historical, unfixed vulnerabilities: CVE-2020-8554, CVE-2020-8561, CVE-2020-8562, and CVE-2021-25740. Previously, these records inaccurately listed a "fixed version." They now correctly reflect that **all versions are affected**. 

These vulnerabilities represent architectural trade-offs where full code remediation would break fundamental Kubernetes functionality. Because vulnerability scanners depend on precise version ranges, this metadata correction will trigger new alerts for these CVEs across all clusters.

### CVE-2020-8561: Webhook Redirect in kube-apiserver (Medium, 4.1)

**Architecture Risk:** The `kube-apiserver` natively follows HTTP redirects when communicating with admission webhooks. An attacker with privileges to create or modify an `AdmissionWebhookConfiguration` can return an HTTP 302 redirect, coercing the API server to issue requests against internal, private networks (an SSRF vector).

**Trade-off:** Disabling redirect following breaks standard HTTP client behavior relied upon by legitimate webhook integrations.

**Mitigation:** Prevent attackers from exfiltrating response bodies via API server logs, and disable dynamic profiling to prevent unauthorized log-level escalation.

```yaml
# kube-apiserver manifest flags
spec:
  containers:
  - command:
    - kube-apiserver
    - --v=4 # Must be < 10 to prevent logging response bodies
    - --profiling=false # Prevent unauthorized log-level changes
```

### CVE-2020-8562: Proxy Bypass via DNS TOCTOU (Low, 3.1)

**Architecture Risk:** A Time-of-Check to Time-of-Use (TOCTOU) race condition exists in the API server proxy. When enforcing IP restrictions, the system performs an initial DNS resolution to validate the IP, followed by a subsequent resolution to establish the actual connection. An attacker can rapidly swap DNS records between these checks to bypass IP filtering.

**Trade-off:** Pinning resolved IPs between the check and connection phases breaks environments relying on split-horizon DNS or highly dynamic IP assignments.

**Mitigation:** Deploy a local DNS caching resolver on control plane nodes to enforce consistent responses between the initial check and the connection attempt.

```conf
# Example dnsmasq.conf for control plane nodes
# Enforce a minimum cache TTL to span the TOCTOU window
min-cache-ttl=60
```

### CVE-2021-25740: Cross-Namespace Forwarding via Endpoints (Low, 3.1)

**Architecture Risk:** The `Endpoints` and `EndpointSlice` APIs allow manual specification of backend IP addresses. An attacker with write access to these resources can configure a `LoadBalancer` or `Ingress` in their namespace to route traffic to backend pods in a completely different namespace, bypassing network isolation.

**Trade-off:** Manual endpoint IP specification is a core design requirement for many networking operators, service meshes, and ingress controllers.

**Mitigation:** Restrict write access to `Endpoints` (legacy) and `EndpointSlices`. Kubernetes 1.22+ removes these permissions from default `edit` and `admin` ClusterRoles. Clusters upgraded from older versions retain the legacy permissions and must be manually reconciled.

```bash
# Reconcile default RBAC roles to remove broad Endpoints write access
kubectl auth reconcile -f <default-rbac-manifests.yaml>
```

```yaml
# Ensure broad roles like 'edit' do NOT contain these permissions:
- apiGroups: ["", "discovery.k8s.io"]
  resources: ["endpoints", "endpointslices"]
  verbs: ["create", "update", "patch", "delete"]
```

### CVE-2020-8554: External IP Service MITM (Unfixed)
Included in the metadata update for completeness, this remains an unfixed architectural issue affecting all versions. Its CVE record was updated solely to adopt a standardized version number format. Mitigation requires disabling the `ExternalIP` feature via admission control (e.g., OPA Gatekeeper or Kyverno) if not actively required by cluster tenants.