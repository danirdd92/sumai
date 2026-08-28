---
title: "Announcing the AI Gateway Working Group"
originalUrl: "https://kubernetes.io/blog/2026/03/09/announcing-ai-gateway-wg/"
publishDate: 2026-03-09T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "gateway-api", "networking", "ai", "architecture"]
---

**Architecture Overview**
An AI Gateway in Kubernetes is a network infrastructure layer that extends the Gateway API specification to enforce policies specifically designed for AI workloads. It operates at L7 but requires deep integration into payload semantics (e.g., token counting, prompt inspection) rather than just HTTP headers.

**Core Capabilities**
* **Token-Aware Traffic Management:** Rate limiting based on LLM token counts rather than standard HTTP request rates.
* **Payload Inspection:** Deep packet inspection of HTTP requests/responses for intelligent routing, caching, and guardrails.
* **Fine-Grained Access Control:** Identity and RBAC applied at the inference API level.

**Active Specifications**

### 1. Payload Processing
Defines standards for inspecting and transforming full HTTP payloads in transit.
* **Security:** Inline defense against prompt injection attacks, content filtering (DLP), and signature/anomaly detection.
* **Optimization:** Semantic routing (routing based on request intent/content), intelligent caching to reduce upstream inference costs, and RAG context enhancement at the network edge.
* **Design Requirements:** Declarative configuration, ordered execution pipelines, and explicit failure modes.

### 2. Egress Gateways
Standardizes secure, managed routing to external AI services (e.g., OpenAI, Vertex AI) and cross-cluster inference endpoints.
* **Integration & Auth:** Centralized token injection and authentication management for third-party APIs, removing credential management from application pods.
* **Resiliency:** Cross-provider inference failover and traffic mirroring.
* **Traffic Control:** Backend resource definitions for external FQDNs, strict TLS policy enforcement, and regional compliance routing.

**Architectural Trade-Offs & Failure Modes**
* **Latency vs. Security:** Deep payload processing (e.g., evaluating prompts against ML models inline) introduces significant latency on the critical path.
* **Failure Modes:** Payload processors must explicitly define behavior (`FailOpen` vs. `FailClosed`) if the inspection engine times out or crashes. Security-critical deployments require `FailClosed`, sacrificing availability.
* **State Management:** Token-based rate limiting requires high-speed distributed state stores at the gateway layer, creating potential bottlenecks for high-throughput inference traffic.

**Implementation Pattern**
The following is an architectural representation using standard and extension Gateway API Custom Resources to demonstrate an egress routing policy with prompt guardrails and cross-provider failover:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: llm-egress-route
spec:
  parentRefs:
  - name: ai-egress-gateway
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /v1/chat/completions
    filters:
    # 1. Attach AI Payload Processing Pipeline via ExtensionRef
    - type: ExtensionRef
      extensionRef:
        group: ai.gateway.k8s.io/v1alpha1
        kind: PayloadProcessor
        name: strict-prompt-guardrails
    backendRefs:
    # 2. Primary External AI Provider
    - name: ext-openai-svc
      weight: 90
    # 3. Fallback / Failover Provider
    - name: ext-vertex-svc
      weight: 10
---
apiVersion: ai.gateway.k8s.io/v1alpha1
kind: PayloadProcessor
metadata:
  name: strict-prompt-guardrails
spec:
  pipeline:
    - type: PromptInjectionDetector
      action: Block
    - type: PIIFilter
      action: Redact
  # Explicit failure mode for the inspection engine
  failureMode: FailClosed 
  timeout: 50ms