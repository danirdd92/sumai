---
title: "Kubernetes v1.36: Admission Policies That Can't Be Deleted"
originalUrl: "https://kubernetes.io/blog/2026/05/04/kubernetes-v1-36-manifest-based-admission-control/"
publishDate: 2026-05-04T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "security", "admission-control", "api-machinery", "cel"]
---

# Manifest-Based Admission Control (v1.36 Alpha)

API-based admission policies (ValidatingAdmissionPolicy, webhooks) suffer from two fundamental operational limitations:
1. **Bootstrap Gap**: Policies remain inactive during cluster bootstrap or etcd recovery until their API objects are explicitly created.
2. **Self-Protection Lockout**: To prevent unrecoverable API lockouts, Kubernetes skips invoking webhooks on admission configuration resources. Consequently, privileged users can delete critical security policies.

Kubernetes v1.36 introduces **Manifest-Based Admission Control**, allowing admission webhooks and Common Expression Language (CEL) policies to be loaded directly from disk before the API server begins serving requests.

## Architecture and Configuration

Manifest-based policies are loaded via the `staticManifestsDir` field in the `AdmissionConfiguration` file passed to `kube-apiserver` via `--admission-control-config-file`.

```yaml
# /etc/kubernetes/admission-control.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: AdmissionConfiguration
plugins:
- name: ValidatingAdmissionPolicy
  configuration:
    apiVersion: apiserver.config.k8s.io/v1
    kind: ValidatingAdmissionPolicyConfiguration
    staticManifestsDir: "/etc/kubernetes/admission/validating-policies/"
```

To enable this alpha feature, the `ManifestBasedAdmissionControlConfig` feature gate must be enabled on `kube-apiserver`.

### Architectural Constraints & Failure Modes

- **Strict Naming Convention**: All resources defined in static manifests MUST end with the `.static.k8s.io` suffix to prevent collisions with API-based configurations.
- **Complete Self-Containment**: Policies must function without cluster state (e.g., prior to etcd availability). 
  - `paramKind` references are prohibited in policies.
  - Webhooks cannot use `Service` references; URL-only endpoints are required.
  - Bindings may only reference policies located within the same manifest set.
- **Fail-Closed Startup**: If any manifest is invalid during the initial load at `kube-apiserver` startup, the API server process will intentionally crash and fail to start.
- **Hot Reloading & Fallback**: Files are watched and atomically reloaded at runtime. If a hot-reloaded configuration fails validation, the API server retains the last known-good configuration and logs an error.
- **Distributed State Drift**: In multi-apiserver deployments, instances load manifests independently without cross-server synchronization. Configuration drift must be monitored externally via the configuration hash exposed as a label on API server metrics.

## Implementation: Immutable Baseline Security

Unlike API-based policies, manifest-based policies *can* intercept operations on admission configuration resources. Because the source of truth resides on disk, misconfigurations are resolved via file modification rather than API calls, eliminating the circular dependency lockout risk.

This enables platform teams to enforce baseline security primitives that cluster admins cannot bypass. The following static manifest shields any API-based policy labeled `platform.example.com/protected: "true"` from deletion or modification:

```yaml
# /etc/kubernetes/admission/validating-policies/protect-policies.yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: "protect-policies.static.k8s.io"
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
    - apiGroups: ["admissionregistration.k8s.io"]
      apiVersions: ["*"]
      operations: ["DELETE", "UPDATE"]
      resources:
      - "validatingadmissionpolicies"
      - "validatingadmissionpolicybindings"
      - "validatingwebhookconfigurations"
      - "mutatingwebhookconfigurations"
  validations:
  - expression: >-
      !has(oldObject.metadata.labels) ||
      !('platform.example.com/protected' in oldObject.metadata.labels) ||
      oldObject.metadata.labels['platform.example.com/protected'] != 'true'
    message: "Protected admission resources cannot be modified or deleted"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: "protect-policies-binding.static.k8s.io"
spec:
  policyName: "protect-policies.static.k8s.io"
  validationActions: ["Deny"]