# Home Assistant

Home Assistant runs on its own box (HA OS, 172.16.30.124, `https://ha.gregpakes.co.uk`),
outside the cluster. Nothing here is deployed: HA keeps its automations and scripts in
its own storage and never reads this repo. This folder is the copy in git of the voice
and music setup, so it can be rebuilt if HA is lost.

HA is the live copy. Change things in HA's UI, then re-export (see below), or the copy
here goes stale.

| File | What it does |
| --- | --- |
| `automations/voice_play_music_fast_via_music_assistant.yaml` | "Alexa, play X": finds an exact artist, song, album or playlist in your own library, then Spotify, and plays it on the room's Music Assistant player without the LLM. With no exact match it plays a near-miss (plural, punctuation or spacing difference, such as "Salmon Cats" → "Salmon Cat") if it is the only one of its kind, and says "Playing …". Asking again within 30 s of a near-miss skips the guess, and "… on Spotify" skips the library. Anything else goes to the Haiku agent. Matched artists, albums and songs go to Lidarr |
| `automations/music_download_albums_played_from_spotify.yaml` | Sends the album of any Spotify track a Music Assistant player has played for 30 s to Lidarr, so it plays from the library next time |
| `automations/voice_announce_to_the_house.yaml` | Fast path for "Alexa, announce/broadcast X" (or "tell everyone X"): hands the message to the announce script without the LLM and says "Announced.". Replaces HA's built-in broadcast, which only reaches HA satellites and says "Done" when none is online |
| `scripts/voice_announce.yaml` | "Announce to the house": sends an Alexa announcement to every online Echo labelled Announce and announces on every idle HA voice satellite labelled Announce (the one handling the request is busy, so it is skipped). Exposed to Assist, so Haiku calls it when a sentence misses the fast path |
| `automations/kitchen_lower_sonos_while_the_echo_listens.yaml` | Ducks the kitchen Sonos to 30% while the kitchen Echo listens, then restores it |
| `automations/patchmon_notify_phone.yaml` | Pushes PatchMon alerts (host down, failed patch runs, reboots, login problems) to the iPhone. PatchMon calls it through a webhook; the real webhook ID is redacted here because this repo is public |
| `scripts/voice_send_music_request_to_lidarr.yaml` | Adds an artist (whole discography) or one album to Lidarr, monitors it and searches. Logs each request on the Music requests to-do list |
| `scripts/voice_start_music_assistant_playback.yaml` | Starts playback in the background, so the voice request ends without waiting for it |
| `automations/media_arr_alerts.yaml` | Lidarr, Radarr and Sonarr post their webhook events here. Only health errors notify the phone and open an item on the Media issues list, once per open item; health items are keyed on the app and health check, so a restore closes them even when the message has changed |
| `automations/media_stuck_downloads.yaml` | Cleanuparr clears failed and stuck downloads itself, so the phone only hears about one when an arr's "needs attention" count has stayed above 0 for 8 hours. Opens a Media issues item, closed when the count is back to 0 |
| `automations/media_health_report.yaml` | Takes the `media-health-reporter` CronJob's counts every 15 minutes (Tdarr music check, Tdarr video errors, each arr's stuck queue items, health warnings, missing items) into the Media dashboard's helpers. Notifies when more music files need attention, and once when no report has come for an hour |
| `dashboards/media.json` | The "Media" dashboard (`dashboard-media`), as Home Assistant stores it |
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
6. Each night (01:00-06:00) the `ma-spotify-linker` CronJob
   (`argocd/infrastructure/servarr/ma-spotify-linker/`) links new library tracks to their
   Spotify versions through Music Assistant's `music/match_providers`. A Spotify playlist
   or radio then plays your own copy of any track you have, because Music Assistant swaps
   a Spotify track for the linked library track when it loads it, and streams the
   best-quality copy.
7. If an import fails, Cleanuparr removes and blocklists the download after five hourly
   strikes, and Lidarr searches for another release. The Lidarr patterns it acts on are in
   `argocd/infrastructure/servarr/cleanuparr/values.yaml`.

## Settings that only exist in a UI (recorded 2026-10-21)

- Assist pipeline "Openrouter - Haiku", used by the Echo:
  - Speech-to-text: Home Assistant Cloud, en-GB. It sometimes loses or garbles the first
    word ("The announce …", "Face" for "Play"). ElevenLabs Scribe v2 (integration
    option `stt_model`, language `en-US`, its only English code) is the alternative tried
    on 2026-10-24, but the ElevenLabs API key lacks the `speech_to_text` permission, so
    every request failed with a 401. Add that permission to the key before trying it again.
  - Text-to-speech: ElevenLabs (integration default model Flash v2.5), language `en`.
    The voice is picked on the pipeline. Changed from Home Assistant Cloud's Libby on
    2026-10-23.
  - Conversation agent: OpenRouter `anthropic/claude-haiku-5.5`, with control of Home
    Assistant (Assist) and "Prefer handling commands locally" both on.
  - The agent's prompt (Settings → Devices & services → OpenRouter → the Haiku
    conversation entry → Reconfigure) ends with the "OK" music rule and this announce rule:
    "To announce, broadcast or tell everyone something, always use the "Announce to the
    house" script, never HassBroadcast (it cannot reach the Echos). Pass the message as
    said, without the word announce. If it reached any speakers, reply with just:
    Announced. Speech recognition sometimes adds a stray word ("The announce dinner is
    ready"): still treat it as an announcement." `script.voice_announce` is exposed to Assist.
- The Echo (ESPHome device "Echo Dot - Custom") is in the Kitchen area. That is how
  "play X" with no room picks `media_player.kitchen_2`. `media_player.kitchen` and
  `media_player.kitchen_4` are unexposed from Assist, so the agent doesn't pick them.
- Label "Announce" (`announce`, added 2026-10-24) decides who hears voice announcements:
  the Echos `media_player.alexa_play_room`, `camille_s_echo_spot`, `sloane_s_echo_spot_2`,
  `show`, `alexa_kitchen`, `alexa_dining_room` (Alexa Media Player), and the satellites
  `assist_satellite.echo_dot_2_15ecca_assist_satellite`,
  `home_assistant_voice_096e49_assist_satellite`, `samsung_sm_x210_assist_satellite`.
  TVs, the soundbar and the Fire TV are left out on purpose, and so is
  `media_player.greg_s_echo_dot`, the Echo that now runs echo-dot-assist.
- To-do list "Music requests" (`todo.music_requests`, Local To-do). It must exist before
  the Lidarr script runs.
- Media alerts (set up 2026-10-24):
  - To-do list "Media issues" (`todo.media_issues`, Local To-do).
  - Helpers the reporter fills: input_number `tdarr_music_passed`, `tdarr_music_queued`,
    `tdarr_music_needs_attention`, `tdarr_video_errors`, `{lidarr,radarr,sonarr}_queue_needs_attention`,
    `{lidarr,radarr,sonarr}_health_warnings`, `lidarr_missing_albums`,
    `radarr_missing_movies`, `sonarr_missing_episodes` (all 0-100000, step 1, box), and
    input_datetime `media_health_last_report` (date and time).
  - The two webhook IDs are in 1Password item `media-alerts-webhooks` (Homelab vault):
    `arr-webhook-id` for "Media: arr alerts", `health-webhook-id` for "Media: health report"
    (the CronJob reads that one through its ExternalSecret).
  - Lidarr, Radarr and Sonarr each have a Settings > Connect > Webhook called
    "Home Assistant (media alerts)", POST to `http://172.16.30.124:8123/api/webhook/<arr-webhook-id>`,
    health warnings not included. All three send only On Health Issue and On Health Restored
    (failed downloads and imports are Cleanuparr's job; Lidarr's import-failure payload
    carries no artist, album or reason anyway). Configarr doesn't manage notifications, so these are UI-only.
- Text helper "Voice last music request" (`input_text.voice_last_music_request`, max
  length 255). The fast-play automation stores the last request in it as JSON, so it can
  tell when a near-miss is asked for again.
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
   Local To-do), and the "Voice last music request" text helper (Settings → Devices &
   services → Helpers → Create helper → Text, max length 255).
3. For each file in `scripts/`: Settings → Automations & scenes → Scripts → Create script →
   ⋮ → Edit in YAML, then paste the file. When saving, the entity ID must match the file
   name, because the automations call `script.voice_send_music_request_to_lidarr` and
   `script.voice_start_music_assistant_playback`.
4. For each file in `automations/`: Automations → Create automation → ⋮ → Edit in YAML,
   then paste the file. If HA saves it under a new config id, update `ITEMS` in the
   export script to match.
5. For announcements: create the Announce label (Settings → Areas, labels & zones →
   Labels) and put it on the entities listed above.
6. For the media alerts: create the Media issues to-do list and the helpers listed above,
   paste the two automations with the webhook IDs from 1Password in place of
   `<redacted>` (the export writes every webhook ID that way), re-create the arrs' webhook connections, and create a dashboard with
   URL `dashboard-media` whose raw configuration is `dashboards/media.json`.
7. Check the IDs that come from other integrations, which change if those are set up
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
