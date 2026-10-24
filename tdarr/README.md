# Tdarr flows

- `flow.json` is the canonical definition of the Tdarr flow that strips foreign
  audio, commentary and non-forced subtitles from the `/media/media` library.
- `music-integrity-flow.json` is the "Music integrity" flow for the Music library
  (`/media/media/music`). It decodes every music file and, when fewer samples decode
  than the file declares, has Lidarr replace it: the grab is marked failed (the release
  is blocklisted and Lidarr re-searches), the track file is deleted and the album is
  searched. See "Music integrity" below.

## Why it lives here and not in `argocd/`

Two reasons, and the second one bites:

1. **ArgoCD cannot apply it.** Tdarr keeps flows in its own SQLite database
   (`/app/server/Tdarr/DB2/SQL`), not in Kubernetes. The flow has to be imported
   through the Tdarr UI.
2. **ArgoCD cannot even parse it.** The tdarr Application syncs
   `argocd/infrastructure/servarr/tdarr` with `directory.recurse: true`, so it
   tries to unmarshal every `.yaml`/`.json` file under that path as a Kubernetes
   manifest. A flow JSON has no `kind`, so its presence there fails the whole
   comparison with `Object 'Kind' is missing` - taking the entire tdarr app out
   of sync, not just the one file. (`backup/flow.bak` survives only because
   ArgoCD ignores the `.bak` extension.)

Keeping it outside `argocd/` makes that structurally impossible rather than
relying on an `exclude` glob staying correct.

## Applying a change

1. Edit the flow JSON here and commit, so the repo stays the source of truth
2. Tdarr UI → **Flows** → import it
3. Restart the tdarr pods if `tdarr-flow-plugins-configmap.yaml` also changed,
   so the init containers re-copy the plugin
4. Clear the existing **Transcode: Not required** status on the library, or the
   new flow will never re-evaluate files it has already seen

## Related

- Guard plugin: `argocd/infrastructure/servarr/tdarr/tdarr-flow-plugins-configmap.yaml`
- Deployment: `argocd/infrastructure/servarr/tdarr/values.yaml`
- Previous flow, kept for history: `argocd/infrastructure/servarr/tdarr/backup/flow.bak`

## Music integrity

Why it exists: on 2026-10-24, 12 of the 13 tracks of Justin Bieber's *Believe* (one
qBittorrent grab from The Pirate Bay) were full-size files whose middle was zeros. They
played for a few seconds and stopped. ffmpeg decodes such a file without an error, so
Tdarr's health check would pass it; and the Media library's video-only container filter
never showed Tdarr the music at all.

- `checkAudioIntegrity` counts the samples that decode (ffmpeg `astats`) and compares
  them with the declared duration. Below 98%, or more than 5 decode errors, is broken.
  It counts samples rather than trusting ffmpeg's `time=`, because FLAC frames carry their
  own position and a zeroed FLAC still reports its full time. FLAC `PADDING` metadata is
  also zeros, which is why a plain zero-byte scan gives false positives and this doesn't.
  If ffmpeg can't run the file goes to output 3 and nothing is deleted.
- `reportBrokenToLidarr` finds the Lidarr track file by path (`/media/media/music` in
  Tdarr is `/downloads/media/music` in Lidarr), marks the grab it came from as failed
  (once per release: later broken tracks of the same grab skip this step),
  deletes the file and queues an `AlbumSearch`. Lidarr's "Redownload failed" is on, so the
  failed grab triggers a search too. At most 40 files a day per node; set the flow's
  `dryRun` input to `true` to log what it would do instead. The node's `LIDARR_API_KEY`
  comes from the `lidarr-secrets` Secret.
- Every file that isn't OK fails the flow, so Tdarr's error list shows what was caught
  and why (the job log carries the decoded and declared lengths).
- The Music library holds new files for 10 minutes, so a file Lidarr is still copying
  in isn't checked half-written.
- Its health checks must stay on (thorough, i.e. ffmpeg): with them off Tdarr shows a
  warning and queues nothing from the library. HandBrake's quick check expects video.
