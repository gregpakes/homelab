# Configarr

[Configarr](https://configarr.de) runs as an hourly CronJob (`:17` past the hour) and
pushes the settings declared here into Radarr, Sonarr, Lidarr and Prowlarr. Git
wins: a UI change to anything declared here is reverted by the next run.

| File | What it holds |
| --- | --- |
| `config.yml` | Instances, API keys and download-client logins (`!env`), the download clients and their completed-download settings, Lidarr's naming, media management, root folder and delay profile, and Prowlarr's indexers, FlareSolverr proxy, sync profile and app links |
| `templates/homelab-radarr.yml` | Radarr's 126 custom formats, 6 quality profiles, quality sizes, naming, media management, root folders and delay profile |
| `templates/homelab-sonarr.yml` | The same for Sonarr: 119 custom formats, 5 profiles |
| `kustomization.yaml` | Turns the three files into ConfigMaps, which the CronJob mounts at `/app/config` |
| `local.env` | `op://` references for running the exporter or Configarr by hand |

The CronJob is `argocd/infrastructure/servarr/configarr/values.yaml`. Its Secret,
`configarr-secrets`, comes from the 1Password items `servarr-api-keys`, `nzbget`,
`qbittorrent` and `prowlarr-indexers` (`externalsecret.yaml` there).

## Why it lives here and not in `argocd/`

The configarr Application syncs `argocd/infrastructure/servarr/configarr` as a
plain directory. Argo parses every `.yaml`/`.yml` file in such a directory as a
Kubernetes manifest. A Configarr template has no `kind`, so it would fail the
whole app with `Object 'Kind' is missing`, as `tdarr/README.md` describes. This folder is
a separate kustomize source instead, and Argo only reads what `kustomization.yaml` lists.

## Where the templates came from

`scripts/export-arr-config.py` wrote both templates on 2026-10-21 from the live
apps. Profilarr's last sync was 2025-11-07, so those were the profiles it left
behind, frozen since. The export was checked against a Configarr dry run until
nothing would change, apart from one thing noted below. **The templates are now
the source of truth. Edit them, not the UI.**

Re-running the exporter overwrites the templates with whatever the UI holds at
that moment. That is only useful to capture a UI change on purpose before
Configarr reverts it.

## Changing something

1. Edit the template or `config.yml`, and commit.
2. Argo updates the ConfigMaps. The next hourly run applies the change.
3. To apply it straight away: `kubectl -n servarr create job --from=cronjob/configarr configarr-manual-$(date +%s)`.
   Read the result with `kubectl -n servarr logs job/<name>`. The run ends with a
   "Diff Report" per instance.

A new custom format needs two entries:
- a `customFormatDefinitions` item with a new `hl-<arr>-<slug>` id
- a `custom_formats` item that gives its score in **every** profile, `0` included

A profile's `qualities` are the API's `items` in reverse, highest priority
first. The members inside a group are reversed the same way, because Configarr
flips both levels back.

## What Configarr 1.35.0 does not enforce

These come from reading its diff code. A UI change to any of them survives until something else forces a rewrite:
- **Which qualities are allowed in a profile.** Only the order of qualities is compared. The `enabled: false` flags are applied only when the order differs too.
- **"Unlimited" quality sizes.** The API returns those as null, and Configarr cannot declare null, so those keys are left out of `quality_definition`.
- **Download-client passwords.** The arrs only return `********`, so with `update_password: false` a password is set when a client is created and never compared after that.

Also:
- Profiles with upgrades off always get `cutoffFormatScore: 1`. Radarr's **Any** and **Ultra-HD** had 0, so the first live run (2026-10-21) wrote 1 there. Radarr doesn't use the field for grabbing while upgrades are off.
- Lidarr's quality and metadata profiles aren't declared, so they stay in the UI.
- Prowlarr only compares the fields listed, but a rewrite of an indexer or app starts from its definition's defaults. So every field with a value is listed, apart from the definitions' `info_*` help text.
- Prowlarr returns Cardigann logins (TorrentLeech's username and password) in plain text, and Configarr compares them exactly. The `prowlarr-indexers` values must match what Prowlarr holds. Changing them there changes Prowlarr on the next run.
- Newznab indexers are declared by preset name (`definition: NZBgeek`). `definition: Newznab` would pick the first preset, abNZB, as the template.
- Indexers that aren't listed are left alone while `delete_unmanaged` is off.
- Indexer and app API keys come back as `********`, so any non-empty value "matches" and a dry run can't tell a wrong key from a right one. The key is only written when something else about that indexer changes, so keep 1Password's copy equal to the one that works in Prowlarr.
- Root folders that aren't listed are **deleted**, so every root folder must stay listed.
- The `may be required` warnings for `url_base`, `api_key` and `*_imported_category` are cosmetic. Those fields are empty on the server, and declaring them as empty would itself be a change.
- Every run clones the TRaSH-Guides and Recyclarr repos into `/app/repos` before it starts. Nothing from them is used, but the job needs internet access.

## When a run fails

`STOP_ON_ERROR` and `CONFIGARR_ENFORCE_CONFIG_VALIDATION` are on, so any of these
fail the Job instead of being logged and skipped:
- an arr that errors or can't be reached
- a quality, custom format or quality size the server doesn't have
- an invalid download-client field

These are what an arr upgrade tends to break. The failed Job fires
kube-prometheus-stack's `KubeJobFailed` alert to Pushover after 15 minutes. It
repeats every 12 hours until the Job is gone, and `ttlSecondsAfterFinished`
removes it after a day. Logs are in Loki, or for that day:

```bash
kubectl -n servarr get pods -l app.kubernetes.io/name=configarr
```

```bash
kubectl -n servarr logs <failed-pod>
```

Runs go Sonarr, Radarr, Lidarr, then Prowlarr, so a failure also skips the arrs
after it for that hour.

After an arr upgrade, the next `:17` run's Diff Report should still say "up to
date". A major version (Sonarr v5, for example) changes the API under Configarr:
re-export and dry-run before merging that image bump. Do the same for Configarr's
own version bumps, since its diff logic changes between releases.

## Checking a change before it goes live

**Without any keys.** This replays saved API responses to the real Configarr
image. `RAW` is a directory written by `export-arr-config.py --raw-dir`. That
saves Radarr and Sonarr; Lidarr's and Prowlarr's responses were saved by hand
into `RAW/lidarr/` and `RAW/prowlarr/`, with the TorrentLeech login replaced by
`REPLAY-username` and `REPLAY-password`:

```bash
python3 scripts/arr-api-replay.py "$RAW" --port 8765 &
docker run --rm -e DRY_RUN=true -e TELEMETRY_ENABLED=false \
  -e STOP_ON_ERROR=true -e CONFIGARR_ENFORCE_CONFIG_VALIDATION=true \
  -e RADARR_URL=http://host.docker.internal:8765/radarr -e RADARR_API_KEY=replay \
  -e SONARR_URL=http://host.docker.internal:8765/sonarr -e SONARR_API_KEY=replay \
  -e LIDARR_URL=http://host.docker.internal:8765/lidarr -e LIDARR_API_KEY=replay \
  -e PROWLARR_URL=http://host.docker.internal:8765/prowlarr -e PROWLARR_API_KEY=replay \
  -e SPORTARR_API_KEY=replay -e NZBGEEK_API_KEY=replay -e ALTHUB_API_KEY=replay \
  -e TORRENTLEECH_USERNAME=REPLAY-username -e TORRENTLEECH_PASSWORD=REPLAY-password \
  -e NZBGET_USERNAME=nzbget -e NZBGET_PASSWORD=replay \
  -e QBITTORRENT_USERNAME=admin -e QBITTORRENT_PASSWORD=replay \
  -v "$PWD/configarr:/app/config:ro" ghcr.io/raydak-labs/configarr:1.35.0
```

The replay server answers GETs only. It logs `MISSING` for an endpoint that
wasn't saved, and `WRITE` for anything that would have changed an arr.

**Against the live apps.** Run from the repo root. It needs 1Password:

```bash
op run --env-file configarr/local.env -- docker run --rm -e DRY_RUN=true -e TELEMETRY_ENABLED=false \
  -e STOP_ON_ERROR=true -e CONFIGARR_ENFORCE_CONFIG_VALIDATION=true \
  -e RADARR_URL=https://radarr.gregpakes.co.uk -e SONARR_URL=https://sonarr.gregpakes.co.uk \
  -e LIDARR_URL=https://lidarr.gregpakes.co.uk -e PROWLARR_URL=https://prowlarr.gregpakes.co.uk \
  -e RADARR_API_KEY -e SONARR_API_KEY -e LIDARR_API_KEY -e PROWLARR_API_KEY -e SPORTARR_API_KEY \
  -e NZBGEEK_API_KEY -e ALTHUB_API_KEY -e TORRENTLEECH_USERNAME -e TORRENTLEECH_PASSWORD \
  -e NZBGET_USERNAME -e NZBGET_PASSWORD \
  -e QBITTORRENT_USERNAME -e QBITTORRENT_PASSWORD \
  -v "$PWD/configarr:/app/config:ro" ghcr.io/raydak-labs/configarr:1.35.0
```

## Rollout

1. Merged with `DRY_RUN: "true"`, so the job only logged what it would change (#406).
2. After Radarr and Sonarr backups, `DRY_RUN: "false"` and Profilarr scaled to zero in the same change, so the two never fight (#407).
3. Add Lidarr (#408), then Prowlarr, each dry-run first.
4. Retire Profilarr.
5. After about two weeks of clean runs, turn on `delete_unmanaged_custom_formats`, `delete_unmanaged_quality_profiles` and `download_clients.delete_unmanaged`.
