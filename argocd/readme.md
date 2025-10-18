# 🧭 Argo CD — App-of-Apps Overview

This directory defines the **Argo CD App-of-Apps** setup for your Homelab cluster.  
The root “GitOps” application points to **`argocd/apps/`** and manages each child application (ordered by sync waves).

---

## 📁 Folder Structure

- **`apps/`** – each YAML here defines an Argo CD `Application` (child app).  
- **`infrastructure/`** – holds the real Kubernetes resources deployed *by* those apps.  
- **`manifests/`** – cluster-wide primitives shared between apps.

---

## 🚀 Child Applications

| App Name | Sync Wave | Description |
|-----------|------------|-------------|
| **external-secrets-operator** | `5` | Installs the External Secrets Operator (controller + CRDs). |
| **1password-connect** | `7` | Deploys the 1Password Connect service used for secret retrieval. |
| **external-secrets-stores** | `8` | Applies the `ClusterSecretStore homelab` manifest that links ESO ↔ 1Password. |
| **nebula-sync** | `20` | Deploys the Nebula Sync workload **and** its `ExternalSecret` for app secrets. |

> ✅ *`nebula-sync` now manages its own ExternalSecret; no separate `nebula-secrets` app required.*

---

## 🔄 Sync Order and Dependencies

1. **external-secrets-operator**  
   Installs ESO and its CRDs so other resources become valid.
2. **1password-connect**  
   Starts the Connect service, exposing an HTTP API for ESO.
3. **external-secrets-stores**  
   Creates the `ClusterSecretStore homelab`, referencing the Connect token.
4. **nebula-sync**  
   - Applies the `ExternalSecret nebula-sync-secrets`.  
   - ESO fetches data from 1Password and creates the K8s Secret.  
   - Deploys the `nebula-sync` Deployment which consumes that Secret.

---

## ⚙️ Root Application (`gitops`)

The root application simply targets this folder:

```yaml
spec:
  source:
    repoURL: https://github.com/gregpakes/homelab
    targetRevision: main
    path: argocd/apps
    directory:
      recurse: false