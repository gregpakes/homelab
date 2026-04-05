# Docker Hosts

GitOps-managed Docker Compose workloads running on bare-metal Raspberry Pi hosts (outside the k3s cluster).

## Structure

```
docker/
  hosts/
    <hostname>/
      <app>/
        docker-compose.yml
        .env.example
```

Each host gets its own directory. Each app under a host is self-contained with its own `docker-compose.yml`.

## Hosts

| Host | Role |
|---|---|
| `infra-pi` | Infrastructure / telephony |

## Deploying

On each Pi, clone this repo and set up a simple pull-and-apply loop. For example, using a systemd service or cron:

```bash
# One-time setup on the Pi
git clone https://github.com/gregpakes/homelab.git /opt/homelab
cd /opt/homelab/docker/hosts/<hostname>/<app>
cp .env.example .env
# Edit .env as needed
docker compose up -d
```

To sync changes from git:

```bash
cd /opt/homelab && git pull
cd docker/hosts/<hostname>/<app>
docker compose up -d --remove-orphans
```

A cron entry to auto-apply on the Pi:

```cron
*/5 * * * * cd /opt/homelab && git pull --ff-only && cd docker/hosts/infra-pi/raspbx && docker compose up -d --remove-orphans 2>&1 | logger -t homelab-gitops
```

## Secrets

Secrets are **not** stored in this repo. Use `.env` files on the host (generated from `.env.example`) or pull from 1Password using the `op` CLI before running compose.
