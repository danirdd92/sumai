---
title: "Securing CI/CD for an open source project: lessons from Cilium"
originalUrl: "https://cilium.io/blog/2026/05/06/securing-cicd-open-source-lessons-from-cilium"
publishDate: 2026-05-06T16:00:00+00:00
source: "cilium"
tags: ["ci-cd", "security", "github-actions", "devsecops"]
---
# CI/CD Security Architecture

Cilium’s CI/CD security model assumes individual layers will fail. The architecture relies on defense-in-depth to isolate CI compromise from production release artifacts. Supply chain hardening focuses on three vectors: access control, dependency immutability, and credential isolation.

## 1. Access Control & Execution Boundaries

### Trigger Controls and CODEOWNERS
CI workflows must not execute untrusted code automatically. 
* **Ariane:** An internal tool restricts CI triggers to an explicit allow-list of verified organization members via PR comments.
* **Review Gates:** Modifications to `.github/` require explicit approval from the security team, enforced via GitHub `CODEOWNERS`.

### Two-Phase Checkouts (`pull_request_target`)
`pull_request_target` workflows run with elevated privileges. Executing code from the PR head introduces a critical remote code execution (RCE) vector. Cilium uses a two-phase checkout to separate trusted execution logic from untrusted build context.

```yaml
# .github/workflows/build.yml
on:
  pull_request_target:
    branches: [main]

jobs:
  secure-build:
    runs-on: ubuntu-latest
    steps:
      # Phase 1: Checkout trusted base branch for CI scripts
      - name: Checkout trusted base
        uses: actions/checkout@v4
        with:
          ref: ${{ github.base_ref }}
          persist-credentials: false

      # Phase 2: Checkout untrusted PR head into isolated directory
      - name: Checkout untrusted PR head
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          path: untrusted-pr
          persist-credentials: false

      # Execution: Trusted scripts operate on untrusted data
      - name: Build Docker Image
        run: make -f ./Makefile build-context=./untrusted-pr
```

**Trade-offs:** Two-phase checkouts increase workflow complexity and require strict discipline to ensure no execution (e.g., `make`, `npm install`) occurs directly within the `untrusted-pr` directory.

## 2. Dependency Hardening

Mutable tags (`v1`, `v2`) are attack vectors if an upstream repository is compromised and the tag is reassigned. Cilium pins all GitHub Actions and container images to absolute 40-character commit SHAs or image digests.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Setup Go
        # Pinned to specific SHA, not a mutable tag like @v5
        uses: actions/setup-go@0a12ed9d6a96ab950c8f026ed9f722fe0da7ef32 
        with:
          go-version: '1.21'
```

**Failure Mode:** SHA pinning does not protect against hidden transitive dependencies where a pinned action internally references another action via a mutable tag. Full immutability requires auditing the upstream action's source.

## 3. Credential Isolation and Verification

To minimize blast radius, CI activities are strictly segregated from production releases.

* **Registry Isolation:** CI workflows only possess credentials for development registries (e.g., `quay.io/cilium/*-ci`).
* **Protected Environments:** Production release credentials reside in highly restricted GitHub Environments requiring manual maintainer approval.
* **Zero-Persistence:** All `actions/checkout` steps use `persist-credentials: false` to prevent downstream steps from hijacking the `GITHUB_TOKEN`.

### Artifact Signing with Keyless OIDC
Releases are signed using Sigstore Cosign in keyless OIDC mode, tying the artifact signature directly to the GitHub Actions workflow identity. Software Bill of Materials (SBOMs) are attached using the `spdxjson` predicate.

```yaml
jobs:
  release:
    permissions:
      id-token: write # Required to fetch OIDC token for Sigstore
      contents: read
    steps:
      - name: Install Cosign
        uses: sigstore/cosign-installer@e1523de7587f0bb5f7b0121102466c1b222cbb5a # v3.4.0
      
      - name: Sign Container Image
        env:
          IMAGE_DIGEST: ${{ steps.build.outputs.digest }}
        # Keyless signing leverages GitHub's OIDC identity
        run: cosign sign --yes quay.io/cilium/cilium@${IMAGE_DIGEST}
```

**Nuance:** Keyless OIDC removes the burden of long-lived key management but introduces a hard dependency on the availability and integrity of the Sigstore transparency log (Rekor) and GitHub's OIDC provider. Tag immutability must be enabled at the repository level to ensure release tags cannot be silently overwritten.