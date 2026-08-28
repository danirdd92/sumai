---
title: "Building a Custom Metrics Exporter for Kubernetes"
originalUrl: "https://kubernetes.io/blog/2026/07/14/custom-metrics-exporter-kubernetes/"
publishDate: 2026-07-14T10:00:00-08:00
source: "kubernetes"
tags: ["kubernetes", "prometheus", "golang", "metrics"]
---

## Architecture

A metrics exporter bridges Kubernetes' default CPU/memory metrics with application-specific signals (queue depths, active connections) to drive scaling decisions. It operates as a lightweight HTTP server exposing application state as plain text on a `/metrics` endpoint. Prometheus periodically scrapes this endpoint, storing time-series data for querying, alerting, and consumption by the HorizontalPodAutoscaler (HPA).

**Architectural Trade-off**: Direct application instrumentation (embedding the Prometheus client) is computationally cheaper and less operationally complex. Standalone exporters should be reserved for external data sources or third-party applications you cannot modify.

## Prometheus Data Model

Metrics must map to one of three primary primitives. Naming should follow the `<namespace>_<name>_<unit>` `snake_case` convention (e.g., `worker_jobs_processed_total`).

*   **Counters**: Monotonically increasing values (e.g., requests served, errors). *Failure Mode*: Never use a counter for a value that can decrease; rate calculations will break.
*   **Gauges**: Point-in-time snapshots that fluctuate (e.g., queue depth, cache size).
*   **Histograms**: Value distributions used to calculate percentiles (e.g., request latency). 

## Implementation (Go)

Initialize the module and pull the official `client_golang` dependencies:

```bash
go mod init example.com/my-exporter
go get github.com/prometheus/client_golang/prometheus
go get github.com/prometheus/client_golang/prometheus/promhttp
```

### 1. Metric Registration
Register metrics globally to ensure they are published on the `/metrics` endpoint prior to the first observed event. Use `prometheus.MustRegister()` for application code to trigger a fast failure (panic) on misconfiguration (e.g., duplicate metrics). If writing a shared library, use `prometheus.Register()` and handle the error.

```go
package main

import (
	"log"
	"net/http"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	jobsProcessed = prometheus.NewCounterVec(
		prometheus.CounterOpts{Name: "worker_jobs_processed_total", Help: "Total jobs processed."},
		[]string{"status"},
	)
	queueDepth = prometheus.NewGauge(
		prometheus.GaugeOpts{Name: "worker_queue_depth", Help: "Jobs waiting in queue."},
	)
	jobDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{Name: "worker_job_duration_seconds", Help: "Job processing time.", Buckets: prometheus.DefBuckets},
	)
)

func init() {
	prometheus.MustRegister(jobsProcessed, queueDepth, jobDuration)
}
```

### 2. Data Collection Loop
Metrics can be updated synchronously upon state changes or via an asynchronous polling loop. If polling, the loop interval must be shorter than the Prometheus scrape interval (default: 15s) to prevent stale reads.

```go
import (
	"math/rand"
	"time"
)

func collectMetrics() {
	for {
		// Replace with internal API, DB, or broker calls
		queueDepth.Set(float64(rand.Intn(50)))
		
		start := time.Now()
		time.Sleep(time.Duration(rand.Intn(200)) * time.Millisecond) // Simulated latency
		
		jobDuration.Observe(time.Since(start).Seconds())
		jobsProcessed.WithLabelValues("success").Inc()
		
		time.Sleep(5 * time.Second)
	}
}
```

### 3. HTTP Server
Expose the metrics handler alongside a segregated `/healthz` endpoint to satisfy Kubernetes liveness probes without polluting metric scrape logs.

```go
func main() {
	go collectMetrics()
	
	http.Handle("/metrics", promhttp.Handler())
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatalf("server error: %v", err)
	}
}
```

## Containerization

Use a multi-stage Dockerfile to output a statically linked binary mounted inside a distroless container. This minimizes attack surface, avoids shipping a toolchain, and satisfies non-root security policies.

```dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /exporter .

FROM gcr.io/distroless/static:nonroot
COPY --from=builder /exporter /exporter
EXPOSE 8080
ENTRYPOINT ["/exporter"]
```

## Kubernetes Deployment

Deploy a Deployment with restrictive CPU/Memory limits and a Service to provide a stable network abstraction.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-exporter
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: my-exporter
  template:
    metadata:
      labels:
        app: my-exporter
    spec:
      containers:
      - name: exporter
        image: <registry>/my-exporter:v1.0.0
        ports:
        - name: metrics
          containerPort: 8080
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
        resources:
          requests:
            cpu: 50m
            memory: 32Mi
          limits:
            cpu: 100m
            memory: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: my-exporter
  namespace: monitoring
spec:
  selector:
    app: my-exporter
  ports:
  - name: metrics
    port: 8080
    targetPort: metrics
```

## Scrape Configuration

Prometheus must be configured to discover the exporter.

**Method 1: Prometheus Operator (Recommended)**
Use a `ServiceMonitor`. Ensure the `release` label matches the label selector of your Prometheus instance (`kube-prometheus-stack` is standard).

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-exporter
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app: my-exporter
  endpoints:
  - port: metrics
    interval: 15s
    path: /metrics
```

**Method 2: Annotation-Based Discovery**
If relying on standard Kubernetes service discovery (SD) configurations instead of CRDs, apply these annotations to the Pod template:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"
  prometheus.io/path: "/metrics"
```

## Verification & HPA Integration

1.  **Verify Target State**: Port-forward Prometheus and check the `/targets` page. Target must be `UP`. 
    ```bash
    kubectl port-forward svc/prometheus-operated 9090 -n monitoring
    ```
2.  **Query Flow**: Confirm data propagation via PromQL:
    ```promql
    rate(worker_jobs_processed_total{status="success"}[2m])
    ```

**Next Step for HPA**: A running exporter is insufficient for autoscaling. To drive an HPA off these metrics, you must install a metrics adapter (e.g., `prometheus-adapter`) to translate PromQL queries into the Kubernetes Custom Metrics API.