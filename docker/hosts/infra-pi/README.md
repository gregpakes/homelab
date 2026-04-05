# infra-pi Portainer GitOps

This host is set up to run the Portainer Agent locally. The actual workloads on the box should be deployed from Portainer using this Git repository as the source of truth.

## 1. Bootstrap the Pi

Run:

```bash
./docker/hosts/infra-pi/bootstrap.sh
```

That will:

- install Docker if needed
- clone this repo to `/opt/homelab`
- start the Portainer agent on `9001`

## 2. Add the Pi to Portainer

In Portainer:

- go to `Environments`
- add a new `Docker Standalone` environment using `Agent`
- point it at `tcp://<infra-pi-ip>:9001`

## 3. Deploy stacks from Git

For each stack on this host, create it in Portainer with:

- `Environment`: `infra-pi`
- `Method`: `Repository`
- `Repository URL`: `https://github.com/gregpakes/homelab.git`
- `Repository reference`: `refs/heads/main`
- `Compose path`: `docker/hosts/infra-pi/docker-compose.yml`

Recommended stack names:

- `infra-pi`

## 4. Enable automatic updates

For Git-backed stacks, enable `Poll for changes` in Portainer.

That makes Portainer periodically check `main` and redeploy the stack when the compose file changes in Git. This is the simplest setup for a CGNAT environment because Portainer pulls from GitHub outbound and does not need any inbound webhook path.

Recommended:

- turn on `Poll for changes`
- choose an interval that matches how quickly you want changes applied
- keep this repo as the only place you edit the stack definition

## Notes

- Keep compose files self-contained and committed to Git. For Git-backed stacks, Portainer treats the repo as the source of truth.
- Avoid editing Git-backed stacks in Portainer directly. Commit changes here instead.
- If a stack needs secrets, keep them out of the compose file and inject them via Portainer environment variables, Docker secrets, or another secret source.
- Portainer's Git polling is enough here. No inbound webhook endpoint or tunnel is required.
- Keep `portainer-agent` outside the main app stack so the management plane is separate from the workloads it manages.
