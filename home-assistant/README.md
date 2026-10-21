# Home Assistant

Home Assistant runs on its own box (HA OS, 172.16.30.124, `https://ha.gregpakes.co.uk`),
outside the cluster. Nothing here is deployed: HA keeps its automations and scripts in
its own storage and never reads this repo. This folder is the copy in git of the voice
and music setup, so it can be rebuilt if HA is lost.

HA is the live copy. Change things in HA's UI, then re-export (see below), or the copy
here goes stale.

| File | What it does |
| --- | --- |
| `automations/voice_play_music_fast_via_music_assistant.yaml` | "Alexa, play X": finds an exact artist, song, album or playlist in your own library, then Spotify, and plays it on the room's Music Assistant player without the LLM. Anything else goes to the Haiku agent. Matched artists, albums and songs go to Lidarr |
| `automations/music_download_albums_played_from_spotify.yaml` | Sends the album of any Spotify track a Music Assistant player has played for 30 s to Lidarr, so it plays from the library next time |
| `automations/kitchen_lower_sonos_while_the_echo_listens.yaml` | Ducks the kitchen Sonos to 30% while the kitchen Echo listens, then restores it |
| `scripts/voice_send_music_request_to_lidarr.yaml` | Adds an artist (whole discography) or one album to Lidarr, monitors it and searches. Logs each request on the Music requests to-do list |
| `scripts/voice_start_music_assistant_playback.yaml` | Starts playback in the background, so the spoken reply doesn't wait for it |
| `configuration/rest_command.yaml` | The `rest_command` block from `configuration.yaml` that the Lidarr script calls |

## How the music flows

1. The Echo Dot (echo-dot-assist firmware) hears "Alexa" and sends the request to the
   "Openrouter - Haiku" Assist pipeline.
2. A "play …" sentence fires the fast-play automation, which plays the match through
   Music Assistant and passes it to the Lidarr script.
3. Spotify plays on any Music Assistant player also reach the Lidarr script, one album at
   a time.
4. Lidarr grabs the album through NZBGet or qBittorrent and imports it into
   `/downloads/media/music`, tagging the files.
5. Music Assistant reads that folder over NFS, so the next request finds it in the library
   first.
6. If an import fails, Cleanuparr removes and blocklists the download after five hourly
   strikes, and Lidarr searches for another release. The Lidarr patterns it acts on are in
   `argocd/infrastructure/servarr/cleanuparr/values.yaml`.

## Settings that only exist in a UI (recorded 2026-10-21)

- Assist pipeline "Openrouter - Haiku", used by the Echo:
  - Speech-to-text and text-to-speech: Home Assistant Cloud, en-GB, voice Libby.
  - Conversation agent: OpenRouter `anthropic/claude-haiku-5.5`, with control of Home
    Assistant (Assist) and "Prefer handling commands locally" both on.
- The Echo (ESPHome device "Echo Dot - Custom") is in the Kitchen area. That is how
  "play X" with no room picks `media_player.kitchen_2`. `media_player.kitchen` and
  `media_player.kitchen_4` are unexposed from Assist, so the agent doesn't pick them.
- To-do list "Music requests" (`todo.music_requests`, Local To-do). It must exist before
  the Lidarr script runs.
- Music Assistant:
  - Spotify provider with a personal developer client ID, set under Reconfigure, last step.
  - Filesystem (NFS) provider reading the Lidarr library from UniFi Drive:
    - server 172.16.250.191, NFS v3
    - export path `/volume/436abd4c-9876-40b2-9887-a2a1e3104d5a/.srv/.unifi-drive/Media/.data`,
      subfolder `music`
    - The `/var/nfs/shared/...` alias doesn't work over v3.
  - Core settings: playing an in-library artist selects top tracks only, because all
    tracks hit Spotify's rate limit. Volume step 10.
- The "Music Assistant Local LLM Enhanced Voice Support" blueprint automation is disabled,
  not deleted. It used `conversation.chatgpt`, which has no credit, and replied "Done" to
  every play request.

## Restoring

1. Add `configuration/rest_command.yaml` to `/config/configuration.yaml`, and
   `lidarr_api_key` to `/config/secrets.yaml`. Restart HA.
2. Create the Music requests to-do list (Settings → Devices & services → Add integration →
   Local To-do).
3. For each file in `scripts/`: Settings → Automations & scenes → Scripts → Create script →
   ⋮ → Edit in YAML, then paste the file. When saving, the entity ID must match the file
   name, because the automations call `script.voice_send_music_request_to_lidarr` and
   `script.voice_start_music_assistant_playback`.
4. For each file in `automations/`: Automations → Create automation → ⋮ → Edit in YAML,
   then paste the file. If HA saves it under a new config id, update `ITEMS` in the
   export script to match.
5. Check the IDs that come from other integrations, which change if those are set up
   again:
   - the Music Assistant `config_entry_id` in the fast-play automation
   - the conversation agent `conversation.anthropic_claude_haiku_5_5`
   - the media player and Assist satellite entity IDs

## Re-exporting after a change in HA

```bash
HA_TOKEN=<long-lived token> uv run scripts/export-ha-config.py
```

The token comes from an admin user: Profile → Security → Long-lived access tokens. The
script rewrites `automations/` and `scripts/` and checks that each file loads back to
exactly what HA returned. It does not touch `configuration/`, which is kept by hand. To
keep another automation or script, add it to `ITEMS` in the script.
