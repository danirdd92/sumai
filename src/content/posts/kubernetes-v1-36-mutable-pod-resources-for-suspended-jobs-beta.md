---
title: "Kubernetes v1.36: Mutable Pod Resources for Suspended Jobs (beta)"
originalUrl: "https://kubernetes.io/blog/2026/04/27/kubernetes-v1-36-mutable-pod-resources-for-suspended-jobs/"
publishDate: 2026-04-27T10:35:00-08:00
source: "kubernetes"
tags: ["kubernetes", "scheduling", "batch", "architecture"]
---

Kubernetes 1.36 promotes **Mutable Pod Resources for Suspended Jobs** to Beta (enabled by default). This feature relaxes immutability constraints on Job pod templates, allowing queue controllers (e.g., Kueue) and cluster operators to dynamically adjust container resource requests and limits in-place before a Job runs or resumes.

### Architectural Motivation
Batch and ML workloads frequently require right-sizing based on real-time cluster capacity, hardware availability (like GPUs), or queue priority. Previously, altering resource requests required deleting and recreating the Job, destroying its metadata, operational state, and history. Mutability allows in-place adjustments, enabling dynamic downscaling (e.g., progressing a CronJob slowly under load rather than failing entirely) without losing Job provenance.

### Implementation Details
The API server now permits updates to the following fields on a Job object:
* `spec.template.spec.containers[*].resources.requests` and `.limits`
* `spec.template.spec.initContainers[*].resources.requests` and `.limits`

**Validation Requirements:**
1. The Job must be in a suspended state (`spec.suspend: true`).
2. If the Job was previously running, **all active Pods must be fully terminated** (`status.active: 0`). The API server strictly rejects mutations otherwise.
3. Standard resource validation applies (limits >= requests; extended resources require whole numbers).

### Example Workflow

**1. Initial Job Creation (Suspended & Over-provisioned):**
A machine learning training job initially requests 4 GPUs but is created in a suspended state by a job dispatcher.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-job-abcd123
spec:
  suspend: true
  template:
    spec:
      containers:
      - name: trainer
        image: example-registry.com/training:v1
        resources:
          requests:
            cpu: "8"
            memory: "32Gi"
            example-vendor.com/gpu: "4"
          limits:
            cpu: "8"
            memory: "32Gi"
            example-vendor.com/gpu: "4"
      restartPolicy: Never
```

**2. Resource Mutation and Resumption:**
A queue controller detects only 2 GPUs are available. It updates the Job in-place and resumes it.

```bash
# 1. Controller scales down resources to fit cluster capacity
kubectl patch job training-job-abcd123 --type=strategic -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "trainer",
          "resources": {
            "requests": {"cpu": "4", "memory": "16Gi", "example-vendor.com/gpu": "2"},
            "limits": {"cpu": "4", "memory": "16Gi", "example-vendor.com/gpu": "2"}
          }
        }]
      }
    }
  }
}'

# 2. Controller resumes the Job
kubectl patch job training-job-abcd123 -p '{"spec":{"suspend":false}}'
```

### Trade-offs and Failure Modes
* **Race Conditions on Suspend:** If you suspend an already-running Job to mutate it, the mutation will be rejected until the API server registers `status.active == 0`. Custom controllers must watch for full Pod termination before attempting the resource patch.
* **Overlapping Pod Contention:** For Jobs prone to Pod failures, set `podReplacementPolicy: Failed`. This ensures replacement Pods are only created after previous Pods fully terminate, avoiding a scenario where overlapping Pods cause resource starvation on the node.
* **Dynamic Resource Allocation (DRA) Blindspot:** This feature does not apply to DRA. `resourceClaimTemplates` remain strictly immutable. Modifying DRA resources requires deleting and recreating the claim templates entirely.