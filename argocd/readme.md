# Homelab GitOps (K3s + Argo CD)

Everything in this repository exists to run a highly-opinionated, Argo CD–managed homelab on a HA K3s cluster.  
The repo contains the bootstrap script for the cluster itself, the full App-of-Apps tree for Argo CD, and the Helm values/raw manifests for each workload (media stack, observability, networking, storage, etc.).

---

## Repository Layout

| Path | Purpose |
| --- | --- |
| `clusters/deployment/k3s.sh` | Bash automation that uses `k3sup`, `kube-vip`, MetalLB and ssh helpers to stand up a 3 master / 2 worker HA K3s cluster on Proxmox nodes. |
| `argocd/apps/` | Every Argo CD `Application` that participates in the App-of-Apps tree (core controllers, infrastructure, and homelab apps). |
| `argocd/infrastructure/` | Chart values, ExternalSecrets, PVCs, Ingress objects, namespaces, etc. for each app. Each folder mirrors the layout of `argocd/apps`. |
| `argocd/readme.md` | Quick reference for the Argo CD directory itself (sync waves, intent of each child app). |
| `renovate.json` | Keeps Helm charts and manifest versions current; Renovate scans all `argocd/**/*.yaml`. |

---

## GitOps Workflow

### App-of-Apps root
1. Manually install Argo CD once (e.g. Helm install or the upstream manifest).
2. Apply `argocd/apps/argocd/argocd.yaml` to let Argo manage its own Helm release plus CSI snapshot components.
3. Create a single Argo application named `gitops` that points at `argocd/apps/`:

   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: gitops
     namespace: argocd
   spec:
     project: default
     destination:
       server: https://kubernetes.default.svc
       namespace: argocd
     source:
       repoURL: https://github.com/gregpakes/homelab
       targetRevision: main
       path: argocd/apps
       directory:
         recurse: false
     syncPolicy:
       automated:
         selfHeal: true
   ```

Every YAML under `argocd/apps/` is ordered with sync-wave annotations so that dependencies (CRDs, operators, secrets) always land before the workloads that depend on them.

### Multi-source Application pattern
Most apps pull an upstream Helm chart and merge repo-local values via `$values/.../values.yaml`.  
When extra manifests are required (PVCs, ExternalSecrets, Traefik certificates, etc.) the application declares a second source pointing at `argocd/infrastructure/<component>` so Argo applies everything together.

### Key Applications Managed by Argo CD
- **Core GitOps & storage controllers**
  - `argocd/apps/argocd/*.yaml` – Self-managing Argo CD release plus CSI snapshot CRDs/controller.
  - `argocd/apps/cert-manager-*` – Installs Jetstack cert-manager and applies issuers + the Cloudflare API ExternalSecret stored in `argocd/infrastructure/cert-manager/`.
  - `argocd/apps/external-secrets-operator.yaml`, `onepassword-connect.yaml`, and `external-secrets-store.yaml` – End-to-end secret sync from 1Password Connect into the cluster (`argocd/infrastructure/cluster-secret-store/clustersecretstore-manifest.yaml`).
  - `argocd/apps/longhorn.yaml` & `argocd/infrastructure/longhorn/` – Deploy Longhorn with pinned chart values plus an ExternalSecret for SMB backup credentials.
  - `argocd/apps/nfs-provisioner.yaml` – RWX storage class backed by the NAS at `172.16.250.191`.

- **Networking, ingress, and load-balancing**
  - `argocd/apps/traefik/application.yaml` – Traefik helm chart with TLS/TLSStore, auth, and wildcard cert manifests from `argocd/infrastructure/traefik/certs/`.
  - `argocd/apps/metallb.yaml` – Controller install plus pools/L2 advertisements in `argocd/infrastructure/metallb/` for VLAN 50 addresses.
  - `argocd/apps/pihole.yaml` – Fully-managed Pi-hole deployment (Deployment/Service/Ingress/Middleware/PVC) defined in `argocd/infrastructure/pihole/`.
  - `argocd/apps/rancher.yaml` – Rancher chart combined with a Traefik ingress (`argocd/infrastructure/rancher/ingress.yaml`).

- **Observability & platform services**
  - `argocd/apps/kube-prometheus-stack.yaml` – Helm plus repo values and alerting secrets (`argocd/infrastructure/kube-prometheus-stack/secret-pushover.yaml`) for Alertmanager → Pushover.
  - `argocd/apps/nebula-sync.yaml` – Uses `argocd/infrastructure/nebula-sync/` (namespace, deployment, ExternalSecret, configmap) to run Nebula Sync.
  - `argocd/apps/homarr.yaml` – Homarr deployed with Helm values and namespace/secret manifests from `argocd/infrastructure/homarr/`.

- **Media stack & homelab apps (servarr)**
  - `argocd/apps/plex.yaml` – bjw-s `app-template` chart plus GPU-ready values under `argocd/infrastructure/plex/values.yaml`.
  - `argocd/apps/servarr/*.yaml` – Bazarr, Cleanarr, Flaresolverr, Jellyseer, Prowlarr, Profilarr, Sonarr, Radarr, and the download clients share the same `app-template` chart.  
    - Their folders in `argocd/infrastructure/servarr/<app>/` define PVCs (e.g. `bazarr-config-pv.yaml`, `qbit-config-pvc.yaml`) and ExternalSecrets (e.g. `downloadclients/externalsecrets.yaml`).
  - `argocd/apps/homarr.yaml` & `argocd/infrastructure/homarr/values.yaml` expose dashboards to the rest of the household.

- **GPU enablement (optional)**
  - `argocd/apps/intel-device-plugins-operator.yaml` and `intel-gpu-plugin.yaml` are currently commented templates. Uncomment them when the Intel plugin should be reconciled by Argo.

---

## Secrets Flow
1. **1Password Connect (`argocd/apps/onepassword-connect.yaml`)** runs inside `external-secrets`, exposing an HTTP API.
2. **External Secrets Operator** syncs `ClusterSecretStore homelab` (defined in `argocd/infrastructure/cluster-secret-store/clustersecretstore-manifest.yaml`).
3. Each workload folder contains its own `ExternalSecret` so credentials stay co-located with the Helm values (examples: Longhorn SMB backup, Alertmanager Pushover secret, Homarr database encryption key).

When adding a new application, keep secret data inside 1Password and reference it with an ExternalSecret in the matching `argocd/infrastructure/<app>/` folder.

---

## Cluster Bootstrap (`clusters/deployment/k3s.sh`)
- Edit the “YOU SHOULD ONLY NEED TO EDIT THIS SECTION” variables (VIP, host IPs, usernames, k3s + kube-vip version, NAS load balancer range).
- Run the script from a workstation with ssh access to each Proxmox VM. It will:
  - Push ssh certificates, disable strict host checking, and ensure `policycoreutils`, `k3sup`, and `kubectl` exist locally.
  - Bootstrap the first master with `k3sup install`, join extra masters/workers, and label worker nodes (`longhorn=true`, `worker=true`).
  - Install kube-vip (manifests copied to `/var/lib/rancher/k3s/server/manifests`), the kube-vip cloud controller, MetalLB, and a sample nginx LoadBalancer.
  - Apply MetalLB pools, test Nginx exposure, and emit node/service status to confirm the cluster is ready for Argo.

Once the cluster is online, install Argo CD as described in the GitOps workflow section and let the App-of-Apps bring the rest online.

---

## Host Requirements for Plex & Media Nodes

### NFS storage
- Each K3s node that might schedule Plex (and any RWX workloads) must have `nfs-common` installed:
  ```bash
  sudo apt update && sudo apt install -y nfs-common
  ```
- The UniFi UNAS Pro 8 only supports NFSv3, so allow the following through the firewall from the K3s node VLAN to the NAS:
  - **TCP:** `111,2049,37511,42989,58873,39543,42463`
  - **UDP:** `111,2049,46622,45992,55670,53394,50514`
- Long term: bake `nfs-common` into the Proxmox VM template to avoid manual installs.

### GPU passthrough (Intel Arc A310)
1. **Enable IOMMU on Proxmox hosts**
   ```bash
   sudo nano /etc/default/grub
   # add:
   GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"
   sudo update-grub
   sudo update-initramfs -u
   sudo reboot
   ```
2. **Find device IDs for vfio**
   ```bash
   lspci -nn | grep -i 'vga\|display\|audio'
   # Example output:
   # 03:00.0 VGA compatible controller [0300]: Intel Corporation Arc A310 [8086:56a0]
   # 03:00.1 Audio device [0403]: Intel Corporation Device [8086:56c0]
   ```
3. **Bind to vfio**
   ```bash
   sudo tee /etc/modprobe.d/vfio.conf >/dev/null <<'EOF'
   # replace IDs with the ones from the lspci step (example shows Arc A310 + audio)
   options vfio-pci ids=8086:56a6,8086:4f92
   EOF
   sudo tee /etc/modules-load.d/vfio.conf >/dev/null <<'EOF'
   vfio
   vfio_iommu_type1
   vfio_pci
   vfio_virqfd
   EOF
   sudo update-initramfs -u
   sudo reboot
   lspci -nnk | grep -A3 -E '56a0|56c0'
   # Expect "Kernel driver in use: vfio-pci"
   ```
4. **Attach the GPU to each K3s worker VM**
   - Proxmox UI → VM → Hardware → Add PCI Device → select Intel Arc 310 → tick *All Functions* → reboot VM.
5. **Install GPU userspace bits in the guest**
   ```bash
   sudo apt update
   sudo apt install -y linux-modules-extra-$(uname -r) linux-firmware
   sudo reboot
   sudo modprobe i915
   ls -l /dev/dri
   # card0 and renderD128 should exist
   ```

With the GPU visible inside the worker, the Plex Helm values (under `argocd/infrastructure/plex/values.yaml`) can request the `intel.com/gpu` resources exposed by the Intel plugin once it is enabled.

---

## Adding or Updating Applications
1. Create/update Helm values or raw manifests under `argocd/infrastructure/<component>/`.
2. Add or edit the matching `Application` under `argocd/apps/`.  
   - Use the multi-source pattern if you need both an upstream chart and repo files.
   - Add `argocd.argoproj.io/sync-wave` annotations when the app has dependencies.
3. Reference secrets through External Secrets to keep 1Password as the single source-of-truth.
4. Commit the changes and let Argo reconcile. Renovate will later propose dependency bumps automatically.

---

## Dependency Automation
`renovate.json` enables Renovate to watch every Argo CD manifest in this repo.  
Pinned Helm chart versions (Longhorn, kube-prometheus-stack, Traefik, MetalLB, Servo apps, etc.) will receive PRs whenever upstream publishes a newer release so upgrades stay controlled and reviewable.
