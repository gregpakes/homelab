# Technitium DNS (HA pair)

Replaces Pi-hole in k3s with two Technitium DNS servers outside the cluster behind
one floating IP, so the house keeps DNS while k3s, a node or a hypervisor is down.

The design borrows from
[fiveangle/proxmox-dns-ha-autodeploy](https://github.com/fiveangle/proxmox-dns-ha-autodeploy)
(the shape, not its deploy script): native keepalived with unicast VRRP, a health
check that only tests the local server, delayed failback, conditional-forwarder
zones for a domain you own, DoH upstream and a pinned image tag.

## Shape

```
clients ─▶ 172.16.51.67 (keepalived VIP) ─┬─▶ dns1  Technitium, cluster primary    priority 150
                                           └─▶ dns2  Technitium, cluster secondary  priority 100
```

- **dns1 / dns2** are small Debian hosts on `172.16.51.0/24`, on different Proxmox
  hosts (infra-pi can be one of them if it is on that VLAN). Each runs:
  - Technitium in Docker, as a Git-backed Portainer stack of `docker-compose.yml`.
    Renovate bumps the image tag like any other compose file.
  - keepalived natively, configured by `keepalived/install.sh` from
    `docker/hosts/<node>/keepalived.env`.
- **Technitium clustering** (v14+) keeps the two configs identical and replaces
  nebula-sync. dns1 is the primary: make every change there. If dns1 is down,
  dns2 keeps serving; changes wait until dns1 is back, or dns2 is promoted.
- **keepalived** keeps the VIP on dns1. `check_technitium.sh` asks the local server
  for `localhost` every second; two misses move the VIP to dns2 in about 2-3 s,
  and dns1 takes it back after 60 s healthy. An internet outage cannot fail the
  check, so it never pulls the VIP off both nodes.
- **The VIP is 172.16.51.67**, Pi-hole's address today, so DHCP, static clients
  and the Tailscale `172.16.51.67/32` route and global nameserver stay as they are.

keepalived runs on the host rather than in the stack so that it outlives Docker
and container restarts: the check fails and the VIP moves cleanly, instead of
going down with the container or being left behind on a dead node.

## Files

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | The Technitium stack, deployed once per node from Portainer. |
| `keepalived/keepalived.conf.tmpl` | VRRP config, rendered per node. |
| `keepalived/check_technitium.sh` | The health check keepalived tracks. |
| `keepalived/install.sh` | Installs keepalived, renders + validates the config, reloads on change. |
| `../../hosts/dns{1,2}/keepalived.env` | Per-node addresses, priority and the `VIP_ENABLED` switch. |

## 1. Hosts

- Debian 13 VM, 1 vCPU, 1 GB RAM, 8 GB disk, on VLAN 51 with a static address
  matching `NODE_IP` (reserve it in UniFi). dns1 and dns2 on different Proxmox
  hosts. A VM rather than an LXC: Docker inside LXC is the fragile part.
- Point the host's own resolver at public servers (`1.1.1.1`, `9.9.9.9`), not the
  VIP or the UniFi gateway, so it can still pull images while DNS itself is down.
- Port 53 must be free. If `systemd-resolved` is running, set `DNSStubListener=no`.

The addresses in the env files (`.53` / `.54`) are proposals. Change both files
if you pick others.

```bash
curl -fsSL https://get.docker.com | sh
sudo git clone https://github.com/gregpakes/homelab.git /opt/homelab
# Same agent definition as infra-pi
sudo docker compose -f /opt/homelab/docker/hosts/infra-pi/portainer-agent/docker-compose.yml up -d
```

Then add each host to Portainer as an Agent environment (`dns1`, `dns2`), as in
`../../hosts/infra-pi/README.md`.

## 2. Technitium stack (Portainer)

On each node: **Stacks -> Add stack -> Repository**:

- Name `technitium`, repository `https://github.com/gregpakes/homelab.git`,
  reference `refs/heads/main`, compose path `docker/stacks/technitium/docker-compose.yml`.
- Environment variables:

  | Variable | Value |
  | --- | --- |
  | `DNS_SERVER_DOMAIN` | `dns1.gregpakes.co.uk` / `dns2.gregpakes.co.uk` |
  | `DNS_SERVER_ADMIN_PASSWORD` | From 1Password, same on both |
  | `DNS_SERVER_FORWARDERS` | `https://dns.nextdns.io/<profile>` to keep NextDNS, or e.g. `https://dns.quad9.net/dns-query (9.9.9.9)` |

  Technitium reads these on first start only.
- **Poll for changes** on, but staggered: dns1 every 5 minutes, dns2 every hour.
  The VIP covers one node restarting at a time; equal intervals would let a
  Renovate bump restart both together.

Web console: `https://<node-ip>:53443` (self-signed) or `http://<node-ip>:5380`.

## 3. Cluster and config (web console)

1. Create the cluster on dns1 and join dns2 to it, using the node IPs, never the
   VIP. Technitium's guide:
   [Understanding Clustering And How To Configure It](https://blog.technitium.com/2025/11/understanding-clustering-and-how-to.html).
2. On dns1 only:
   - **Settings**: check the forwarders, DNSSEC validation and serve-stale.
   - **Settings -> Blocking**: add the adlists from Pi-hole (**Lists**). Blocked
     names get NXDOMAIN or `0.0.0.0` depending on the blocking type set there.
   - **Zones**:

     | Zone | Type | Holds |
     | --- | --- | --- |
     | `gregpakes.co.uk` | Conditional Forwarder, forwarder `this-server` | The internal records now in Pi-hole's Local DNS (Plex, Portainer, ... -> the Traefik / MetalLB IPs). Names not in the zone still resolve upstream. |
     | UniFi's local domain | Conditional Forwarder -> `172.16.51.1` | DHCP hostnames |
     | `51.16.172.in-addr.arpa` | Conditional Forwarder -> `172.16.51.1` | Reverse lookups |

     Keep UniFi's own upstream DNS off the VIP. Otherwise a name UniFi doesn't
     know in its local domain loops between the two.
   - **Apps**: install *Query Logs (Sqlite)* for a Pi-hole-style query log.
3. Check that dns2 shows the same zones and blocklists.

Test against the node IPs before going near the VIP:

```bash
dig @172.16.51.53 plex.gregpakes.co.uk +short
dig @172.16.51.54 plex.gregpakes.co.uk +short
dig @172.16.51.53 doubleclick.net        # blocked: NXDOMAIN or 0.0.0.0
dig @172.16.51.53 -x 172.16.51.1 +short  # UniFi reverse lookup
```

## 4. keepalived (staged)

```bash
cd /opt/homelab && sudo git pull
sudo docker/stacks/technitium/keepalived/install.sh docker/hosts/dns1/keepalived.env   # dns2: hosts/dns2
```

With `VIP_ENABLED=false` this installs keepalived and leaves it configured,
validated and stopped. Re-run it after any change to the template or env file.
It reloads keepalived only when the rendered config changed.

## 5. Cutover

`172.16.51.67` is held by Pi-hole's MetalLB LoadBalancer until this step.

1. One PR:
   - `argocd/infrastructure/pihole/service.yaml`: `type: ClusterIP`, and drop
     `loadBalancerIP` and `externalTrafficPolicy`. Pi-hole keeps running with its
     data and only lets go of `.67`, so rolling back is a revert.
   - `argocd/infrastructure/metallb/ipaddresspools-firstpool.yaml`: split the range
     into `172.16.51.60-172.16.51.66` and `172.16.51.68-172.16.51.80`, so nothing
     else is ever handed `.67`.
   - `VIP_ENABLED=true` in both `keepalived.env` files.
   - Scale nebula-sync to 0: it only syncs Pi-holes.
2. Merge and let Argo sync. `kubectl -n pihole get svc pihole` shows `ClusterIP`.
3. On dns1, then dns2: `git pull` and re-run `install.sh`. `ip -4 addr` on dns1
   now lists `172.16.51.67`.
4. `dig @172.16.51.67 plex.gregpakes.co.uk` from the LAN, and from a tailnet device
   off the LAN.

DNS is down only between steps 2 and 3. To roll back, run
`sudo systemctl stop keepalived` on both nodes and revert the PR.

## Failover test

```bash
# on dns1
sudo docker stop technitium               # VIP is on dns2 within ~3 s
dig @172.16.51.67 plex.gregpakes.co.uk    # still answers, from dns2
sudo docker start technitium              # VIP returns to dns1 after 60 s healthy
journalctl -u keepalived -f               # state changes on either node
```

## Afterwards

- Remove Pi-hole, nebula-sync and pihole2 once settled, and update the Pi-hole
  mentions in `argocd/readme.md` and `argocd/infrastructure/tailscale/README.md`.
- Backups: VolSync doesn't reach these hosts. Use Proxmox vzdump of both VMs, plus
  Technitium's own **Settings -> Backup**.
- Alerting: the VIP hides a dead node, and nothing alerts on one yet. A blackbox
  probe of both node IPs from kube-prometheus-stack would cover it.
