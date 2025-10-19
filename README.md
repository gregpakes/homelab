# 🧭 Argo CD — App-of-Apps Overview

This directory defines the **Argo CD App-of-Apps** setup for your Homelab cluster.  
The root “GitOps” application points to **`argocd/apps/`** and manages each child application (ordered by sync waves).

---

## 📁 Folder Structure

- **`apps/`** – each YAML here defines an Argo CD `Application` (child app).  
- **`infrastructure/`** – holds the real Kubernetes resources deployed *by* those apps.  

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
```

## Plex

In order to run Plex on K3S, each K3S node needs to have `nfs-common` installed.

```bash
sudo apt update && sudo apt install -y nfs-common
```

At the moment, this is installed manually on each k3s node.

>Todo: Look into building it into the proxmox vm template

#### Firewall

I have a UniFi Unas Pro 8 which only supports NFS v3.  Therefore there needs to be a firewall rule to allow NFS v3 traffic from the K3s Node vlan to the Unas Pro 8.

> TCP: `111,2049,37511,42989,58873,39543,42463`  
> UDP: `111,2049,46622,45992,55670,53394,50514`

### NFS Provisioner (K3s)

With this in place, the NFS-Provisioner application (in argocd) is able to install on any k3s node and provision NFS shares available to pods.
