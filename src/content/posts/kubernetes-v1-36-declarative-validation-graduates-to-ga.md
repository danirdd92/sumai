---
title: "Kubernetes v1.36: Declarative Validation Graduates to GA"
originalUrl: "https://kubernetes.io/blog/2026/05/05/kubernetes-v1-36-declarative-validation-ga/"
publishDate: 2026-05-05T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "api-machinery", "golang", "code-generation"]
---

Declarative Validation for Kubernetes native types has reached General Availability (GA) in v1.36, replacing roughly 18,000 lines of imperative, handwritten Go validation logic with an Interface Definition Language (IDL) marker system.

### Architecture: `validation-gen`

Historically, Kubernetes API validation required explicit Go functions, resulting in technical debt, inconsistent enforcement, and opaque rules that tooling could not introspect. 

The new architecture relies on `validation-gen`, a code generator that parses `+k8s:` marker tags within `types.go` and automatically generates the corresponding Go validation functions. These functions are then seamlessly registered with the API scheme. The generator framework is extensible, allowing developers to plug in custom "Validators" by mapping specific tags to generated Go logic.

### Implementation Details

Validation constraints are now defined directly alongside field definitions using marker tags. 

```go
type ReplicationControllerSpec struct {
    // +k8s:optional
    // +k8s:minimum=0
    Replicas *int32 `json:"replicas,omitempty"`
}
```

**Common Supported Markers:**
*   **Presence:** `+k8s:optional`, `+k8s:required`
*   **Constraints:** `+k8s:minimum=N`, `+k8s:maximum=N`, `+k8s:maxLength=N`, `+k8s:format=k8s-short-name`
*   **Collections:** `+k8s:listType=map`, `+k8s:listMapKey=type`
*   **Unions:** `+k8s:unionMember`, `+k8s:unionDiscriminator`
*   **Immutability:** `+k8s:immutable`, `+k8s:update=[NoSet, NoModify, NoClear]`

### Architectural Nuance: Ambient Ratcheting

A critical capability introduced by this framework is built-in **validation ratcheting** (ambient ratcheting). 

**Mechanism:** During an update operation, the validation framework compares the incoming object with the `oldObject`. If a specific field's value is semantically equivalent to its prior state (i.e., the user did not mutate it), the new validation rules for that field are bypassed.

**Trade-offs & Failure Modes:** 
*   **Advantage:** API reviewers can immediately tighten validation constraints for new objects without breaking backward compatibility for existing resources that violate the new rules. 
*   **Drawback:** Clients must be aware that while reading an invalid object and writing it back without modification will succeed, mutating a previously invalid field will trigger the new, stricter validation constraints. This can cause unexpected rejections on seemingly unrelated field updates if the client logic is not prepared to handle strict validation on legacy data.

### Ecosystem Integration

Moving validation to structured markers enables static analysis and ecosystem tooling integrations:
*   **Static Enforcement:** `kube-api-linter` can now statically analyze API types to enforce conventions without executing the code.
*   **Client-Side Validation (Future):** Validation rules will be exposed via OpenAPI schemas published by the API server. This enables `kubectl`, client libraries, and IDEs to perform pre-flight validation before transmitting requests to the cluster, reducing API server load.
*   **CRD Consistency:** The declarative framework can be consumed by ecosystem tools like Kubebuilder, unifying the validation authoring experience between native Kubernetes APIs and Custom Resource Definitions (CRDs).

The `DeclarativeValidation` feature gate is now enabled by default. The migration of legacy handwritten validation to the declarative format across all Kubernetes native types remains ongoing.