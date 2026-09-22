# Tailscale

Remote access to Plex that bypasses both Cloudflare and Plex Relay.

## Why

`plex.gregpakes.co.uk` resolves through the Cloudflare tunnel, and `cloudflared` runs
at `replicas: 0`. Behind CGNAT there is no port forward for Plex's own remote access
either, so remote playback falls back to Plex Relay and its ~2 Mbps cap. Proxying
video through a Cloudflare tunnel is also outside Cloudflare's terms.

Tailscale gives a direct WireGuard path (DERP-relayed only when NAT traversal fails),
with no ports opened on the router.

## Shape

- `tailscale-operator` Helm chart, namespace `tailscale`.
- A `Connector` running a subnet router that advertises **host routes only**:
  - `172.16.51.70/32` - Plex
  - `172.16.51.67/32` - Pi-hole, as the tailnet nameserver

Plex keeps its LAN IP, so the existing `ALLOWED_NETWORKS: 172.16.0.0/16` in
`../plex/values.yaml` already treats tailnet clients as local and no bitrate cap is
applied. **No change to the Plex app is needed.**

The rest of `172.16.51.0/24` - the k3s API VIP on `.50`, the nodes on `.201-.205`,
both Traefik LBs on `.65`/`.66` - is deliberately not advertised. Widen
`advertiseRoutes` in `connector.yaml` if that changes, and write an ACL first.

## Client support

Tailscale needs a client on the device. iOS, Android, macOS, Windows, Linux, Apple TV
(tvOS) and the Nvidia Shield all have one. **webOS / LG TVs do not** - a remote LG TV
can only be covered by a subnet router on that network, not by Tailscale on the TV.

## One-time manual setup

These are console-side and cannot live in git.

### 1. OAuth client

At <https://login.tailscale.com/admin/settings/oauth>, create a client with:

- scope `auth_keys` (write)
- tag `tag:k8s-operator`

Both `tag:k8s-operator` and `tag:k8s` must exist in the tailnet policy file first,
with the OAuth client as an owner:

```jsonc
"tagOwners": {
  "tag:k8s-operator": [],
  "tag:k8s":          ["tag:k8s-operator"],
}
```

### 2. 1Password item

Vault `Homelab`, item titled **`tailscale-operator`**, two fields:

| Field           | Value                     |
| --------------- | ------------------------- |
| `client_id`     | OAuth client ID           |
| `client_secret` | OAuth client secret       |

`externalsecret.yaml` renders this into the `operator-oauth` Secret the chart's
Deployment mounts. The Secret name and both key names are fixed by the chart.

### 3. Approve the routes

Advertised routes are inert until approved. Either tick them under **Machines ->
`ts-plex-subnet-router` -> Edit route settings**, or auto-approve in the policy file:

```jsonc
"autoApprovers": {
  "routes": {
    "172.16.51.70/32": ["tag:k8s"],
    "172.16.51.67/32": ["tag:k8s"],
  },
},
```

### 4. Pi-hole as tailnet DNS

**DNS -> Nameservers -> Global nameserver** -> `172.16.51.67`.

Leave **Override local DNS** off. With it on, every tailnet device depends on the
subnet router for all name resolution - if the cluster or the Connector is down,
remote devices lose DNS entirely, not just internal names.

Pi-hole sees these queries arriving from the router pod's `10.42.x.x` address
because Tailscale SNATs subnet routes. If replies do not come back, check Pi-hole's
DNS listening mode permits non-local origins.

## Verifying

From a tailnet device, off the LAN:

```bash
tailscale status          # ts-plex-subnet-router present, routes listed
tailscale ping 172.16.51.70
curl -sI http://172.16.51.70:32400/identity
```

`tailscale status` shows `direct` for a working NAT-traversed path and `relay
"<derp>"` if it fell back - relayed still works but adds latency and is bandwidth
limited, which matters for 4K.

In Plex, **Settings -> Status -> Now Playing** should show the session as `LAN`, not
`WAN`. A `WAN` session means the SNAT assumption above is wrong and the bitrate cap
still applies.
