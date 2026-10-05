# Track Manager

The LapSmith operator console (release control, backend deploys, bug triage,
user-data export, account deletion), hosted on `traefik-internal` at
`https://lapsmith.gregpakes.co.uk` behind oauth2-proxy (GitHub sign-in).

Track Manager has no login of its own. The app side of this design — the
access gate, its two modes, and why each check exists — is documented in
gregpakes/LapSmith `tools/track_catalog_manager/README.md` ("Hosted behind an
authenticating proxy") and `tools/AGENTS.md`.

```text
browser ─▶ traefik-internal ─▶ strip-identity-headers
                            ─▶ oauth2-forward-auth ──▶ oauth2-proxy  /  (302 to GitHub, or
                            │                          202 + X-Auth-Request-User
                            │                              + X-Track-Manager-Proxy-Secret)
                            ─▶ track-manager:4173   (checks secret, allowlist, Host, Origin)

browser ─▶ /oauth2/{start,callback,sign_in,sign_out,static/} ─▶ oauth2-proxy
```

| File | What |
| --- | --- |
| `externalsecrets.yaml` | All credentials, from 1Password, split per pod |
| `oauth2-proxy.yaml` | Alpha config, Deployment, Service |
| `track-manager.yaml` | Deployment (1 replica, Recreate), Service |
| `ingress.yaml` | Middlewares and the IngressRoute |
| `networkpolicy.yaml` | Only `traefik-internal` may reach either pod |

## One-time setup

1. **GitHub OAuth App** (github.com → Settings → Developer settings → OAuth
   Apps): homepage `https://lapsmith.gregpakes.co.uk`, callback
   `https://lapsmith.gregpakes.co.uk/oauth2/callback`. Sign-in asks for
   `user:email` and `read:org`.
2. **Fine-grained GitHub token**, repository `gregpakes/LapSmith` only:
   Actions read and write, Contents read, Variables read, Environments read.
   This token can dispatch store releases and backend deploys — give it an
   expiry and keep it to this one repository.
3. **Firebase service-account key** for `track-app-13884` with the access
   Track Manager's admin pages need. Prefer a dedicated account for the
   cluster over reusing a local key, so it can be revoked on its own.
4. **1Password**, Homelab vault, item `lapsmith-track-manager` with the fields
   listed at the top of `externalsecrets.yaml`. Generate the two random ones:

   ```bash
   openssl rand -hex 32                        # proxy-secret
   openssl rand -base64 32 | tr -- '+/' '-_'   # cookie-secret
   ```

   The registry pull reuses the existing `github-ghcr-pull` item.
5. **Pi-hole**: a local DNS record `lapsmith.gregpakes.co.uk` →
   `172.16.51.66` (the `traefik-internal` LoadBalancer), unless a wildcard
   already covers it.
6. **Image**: run `CI · Track Manager image` in gregpakes/LapSmith, then
   replace `sha-PENDING` in `track-manager.yaml` with the tag it prints.
   Renovate leaves this image alone; every bump is by hand.

## Checking it after a sync

- Opening the site signs you in with GitHub, then shows the catalog. Any other
  GitHub account is refused by oauth2-proxy before Track Manager sees it.
- `kubectl -n track-manager logs deploy/track-manager` starts with
  `[operator-access] … access mode=proxy origin=https://lapsmith.gregpakes.co.uk`.
  `rejected … code=untrusted_proxy` means the secret is not arriving (check the
  `track-manager-proxy` Secret and the ForwardAuth `authResponseHeaders`);
  `code=operator_not_authenticated` means the user header is not.
- Release Control loads its board. A `github_auth_required` error means the
  `github-token` field is missing or lacks a permission above.
- Catalog edits are refused on purpose (`catalog_read_only`): the image is not a
  working tree. Edit and publish the catalog from a local checkout.

An expired oauth2-proxy session (7 days) shows up as a failed fetch on an open
page, because the 302 to GitHub cannot be followed cross-origin by `fetch`.
Reload the page to sign in again.
