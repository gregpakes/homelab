# Tdarr flow

`flow.json` is the canonical definition of the Tdarr flow that strips foreign
audio, commentary and non-forced subtitles from the `/media/media` library.

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

1. Edit `flow.json` here and commit, so the repo stays the source of truth
2. Tdarr UI → **Flows** → import `flow.json`
3. Restart the tdarr pods if `tdarr-flow-plugins-configmap.yaml` also changed,
   so the init containers re-copy the plugin
4. Clear the existing **Transcode: Not required** status on the library, or the
   new flow will never re-evaluate files it has already seen

## Related

- Guard plugin: `argocd/infrastructure/servarr/tdarr/tdarr-flow-plugins-configmap.yaml`
- Deployment: `argocd/infrastructure/servarr/tdarr/values.yaml`
- Previous flow, kept for history: `argocd/infrastructure/servarr/tdarr/backup/flow.bak`
