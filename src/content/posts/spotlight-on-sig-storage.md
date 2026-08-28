---
title: "Spotlight on SIG Storage"
originalUrl: "https://kubernetes.io/blog/2026/06/15/sig-storage-spotlight-2026/"
publishDate: 2026-06-15T00:00:00+00:00
source: "kubernetes"
tags: ["kubernetes", "storage", "csi", "stateful-workloads", "backup"]
---

SIG Storage defines the standard interfaces for persistent data and volume management in Kubernetes, enabling out-of-tree storage plugins via the Container Storage Interface (CSI) and maintaining core primitives (PVs, PVCs, StorageClasses). 

## Core Infrastructure Advancements

Recent releases introduce K8s primitives for dynamic scaling, crash-consistent backups, and object storage standardization.

### Dynamic Storage Tuning: VolumeAttributesClass (GA v1.34)
Prior to `VolumeAttributesClass`, modifying volume attributes (IOPS, throughput) required out-of-band operations or workload downtime. This primitive enables dynamic, API-driven tuning of storage characteristics without recreating the volume, allowing automated scaling for peak loads and cost optimization.

```yaml
# Example: Modifying volume characteristics dynamically
apiVersion: storage.k8s.io/v1
kind: VolumeAttributesClass
metadata:
  name: high-iops-tier
driverName: pd.csi.storage.gke.io
parameters:
  type: pd-extreme
  provisioned-iops: "100000"
```

### Crash-Consistent Backups: VolumeGroupSnapshot (GA v1.36)
`VolumeGroupSnapshot` captures atomic, point-in-time snapshots across multiple PersistentVolumes simultaneously. This is critical for data integrity in multi-volume databases where capturing state sequentially would result in corrupted or unrecoverable backups.

```yaml
# Example: Triggering a group snapshot across database volumes
apiVersion: snapshot.storage.k8s.io/v1alpha1
kind: VolumeGroupSnapshot
metadata:
  name: pg-cluster-snapshot-t0
spec:
  volumeGroupSnapshotClassName: csi-snap-class
  source:
    selector:
      matchLabels:
        app: postgres-cluster
```

### Efficient Backups: CSI Changed Block Tracking (Beta v1.36)
Changed Block Tracking (CBT) optimizes incremental backups by allowing storage systems to report only the blocks modified since a prior snapshot, drastically reducing data transfer overhead. 
**Trade-offs:** Relies on the underlying storage driver implementing the CBT API. Fallback mechanisms (e.g., full volume scans) must be maintained if the driver fails to track changes accurately.

### Container Object Storage Interface (COSI) (v1alpha2)
COSI standardizes object storage provisioning and consumption, bringing the CSI operational model to object buckets. It abstracts bucket lifecycle management, enabling K8s workloads to claim S3-compatible storage natively.

```yaml
# Example: Provisioning object storage natively in K8s
apiVersion: objectstorage.k8s.io/v1alpha1
kind: BucketClaim
metadata:
  name: ai-dataset-claim
spec:
  bucketClassName: s3-standard
  protocols:
    - s3:
        signatureVersion: s3v4
```

## Architectural Challenges & Failure Modes

Operating stateful workloads in an ephemeral orchestration environment introduces specific operational hurdles.

*   **Data Gravity vs. Storage Locality:** Pods are highly mobile; persistent data is not. 
    *   *Failure Mode:* If a node fails, a pod bound to local storage becomes trapped. The K8s scheduler cannot easily distinguish between a transient network partition and a permanent node failure. Incorrect automated remediation (e.g., force-deleting the pod to reschedule) can lead to split-brain scenarios or data corruption. SIG Storage is extending **Volume Health** metrics to expose hardware degradation events to the K8s control plane, enabling safer, state-aware automated recovery.
*   **Day 2 Complexity:** Native K8s controllers (e.g., `StatefulSet`) provide a baseline deployment topology but lack the domain-specific operational logic required for tasks like schema upgrades, engine patching, or cross-cluster migrations.
*   **Data Mobility:** Synchronous replication for high availability and disaster recovery across Availability Zones or disparate clusters remains difficult. The K8s-native `Mutable PV Affinity` feature (Alpha v1.35) targets this space by enabling declarative volume migration between zones or disk tiers.

## AI/ML Workload Evolution

As Kubernetes absorbs large-scale AI pipelines, storage architectures are adapting to meet GPU throughput demands and massive dataset requirements.

*   **Data-Aware Scheduling:** Standard K8s scheduling evaluates CPU and RAM constraints. Future scheduler iterations will calculate the latency cost of moving data versus moving compute, prioritizing pod placement based on existing data locality to optimize network bandwidth and Kubelet performance.
*   **Object Storage Primacy:** Exabyte-scale AI datasets mandate object storage as a first-class citizen. COSI is critical for unifying object, block, and file consumption under a single operational workflow for data scientists.
*   **High-Throughput Paradigms:** To prevent storage I/O bottlenecks from starving GPU compute, K8s integration with high-performance parallel file systems and NVMe-over-Fabrics (NVMe-oF) is accelerating. The storage abstraction layer is shifting to manage memory-speed storage natively via Kubernetes APIs.