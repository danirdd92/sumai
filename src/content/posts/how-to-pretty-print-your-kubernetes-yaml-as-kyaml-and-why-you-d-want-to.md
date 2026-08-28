---
title: "How to Pretty-Print Your Kubernetes YAML as KYAML and Why You'd Want To"
originalUrl: "https://kubernetes.io/blog/2026/08/11/how-to-pretty-print-kubernetes-yaml-as-kyaml/"
publishDate: 2026-08-11T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "yaml", "tooling", "configuration"]
---

KYAML (introduced in KEP 5295) is a strict subset of standard YAML designed to eliminate common YAML parsing ambiguities while maintaining 100% backwards compatibility with existing YAML parsers and the Kubernetes ecosystem. It enforces YAML "flow style" over the conventional "block style".

### The Problem with Standard YAML
Standard block-style YAML introduces two primary failure modes in configuration management:
1. **Whitespace Sensitivity:** Indentation defines structural hierarchy. This makes manifests fragile, particularly when generating or manipulating YAML via templating engines like Helm.
2. **Silent Type Coercion:** Unquoted strings can be inadvertently parsed as booleans, integers, or floats. The classic "Norway Bug" occurs when a country code `NO` is evaluated as the boolean `false`.

JSON is often proposed as an alternative but falls short for human-authored configuration due to a lack of comment support, strict trailing comma restrictions, and mandatory key quoting.

### The KYAML Solution
KYAML bridges the gap between YAML's readability and JSON's strictness by enforcing explicit structural boundaries and types:
* **Explicit Structure:** Uses `{}` for maps and `[]` for lists. Indentation no longer dictates structure.
* **Explicit Typing:** All string values are double-quoted, eliminating silent type coercion.
* **Developer Ergonomics:** Retains standard YAML features like comments, trailing commas, and the `---` document separator.

#### Comparison

**Standard YAML (Block Style)**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
  labels:
    app: demo
spec:
  containers:
  - name: nginx
    image: nginx:1.20
```

**KYAML (Flow Style)**
```yaml
---
{
  apiVersion: "v1",
  kind: "Pod",
  metadata: {
    name: "my-pod",
    labels: {
      app: "demo",
    },
  },
  spec: {
    containers: [
      {
        name: "nginx",
        image: "nginx:1.20",
      }
    ],
  },
}
```

### Implementation and Tooling

Because every valid KYAML file is valid YAML, adoption requires zero changes to existing CI pipelines, API servers, or third-party operators. You can generate KYAML using several methods.

#### 1. Native `kubectl` Output
Kubernetes 1.34+ supports KYAML as a native output format. 

```bash
# Kubernetes 1.35+ (beta)
kubectl get deployment my-app -o kyaml

# Kubernetes 1.34 (alpha, requires feature flag)
export KUBECTL_KYAML=true
kubectl get deployment my-app -o kyaml
```

To configure KYAML as the default `kubectl get` output (via `kuberc`):
```bash
# Kubernetes 1.36+
kubectl kuberc set --section defaults --command get --option output=kyaml

# Kubernetes 1.33–1.35
kubectl alpha kuberc set --section defaults --command get --option output=kyaml
```

#### 2. Kubernetes `yamlfmt` (sigs.k8s.io)
A standalone formatting utility that prints converted KYAML to `stdout`.

```bash
go install sigs.k8s.io/yaml/yamlfmt@latest
yamlfmt -o=kyaml my-deployment.yaml > my-deployment-kyaml.yaml
```

#### 3. Google `yamlfmt` (v0.21.0+)
Google's `yamlfmt` supports KYAML formatting and is suitable for CI enforcement (available as a Docker image or pre-commit hook).

Configure your `.yamlfmt` file at the project root:
```yaml
formatter:
  type: kyaml
```

Run the formatter:
```bash
go install github.com/google/yamlfmt/cmd/yamlfmt@latest
# Convert an entire directory in place
yamlfmt ./k8s/
```

### Trade-offs and Drawbacks

* **Visual Density:** Flow style introduces syntactic noise (brackets, braces, commas, quotes) that block-style YAML intentionally avoids. Developers accustomed to minimal YAML may find KYAML denser and harder to read at a glance.
* **Tooling Isolation:** Formatters specifically configured for KYAML (like Google's `yamlfmt` `kyaml` type) do not share configuration options with standard YAML formatters. Attempting to mix formatting rules will result in configuration errors.
* **Migration Friction:** While KYAML works with existing parsers, enforcing it across a repository requires updating linting pipelines, pre-commit hooks, and retraining team members on the new style.