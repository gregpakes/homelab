#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""
Export the Home Assistant automations and scripts that home-assistant/ keeps a copy of.

    HA_TOKEN=... uv run scripts/export-ha-config.py [--raw-dir DIR]
    uv run scripts/export-ha-config.py --offline --raw-dir DIR

Writes home-assistant/automations/*.yaml and home-assistant/scripts/*.yaml.
Home Assistant is the live copy: these are made in its UI and it never reads
this repo, so change them there, then re-run this to bring git up to date.

The first form reads HA's config API with a long-lived access token from an
admin user (Profile → Security → Long-lived access tokens) and, with
--raw-dir, saves each response as DIR/<automation|script>/<id>.json. The
second rebuilds the YAML from those files with no token or network.

Every file is loaded back before it is written and must equal what HA
returned, so a restore pastes exactly the live config. To keep another
automation or script, add it to ITEMS.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "home-assistant"
HA_URL = "https://ha.gregpakes.co.uk"

# (kind, config id, entity id without the domain). An automation's config id is
# the number at the end of its editor URL; a script's is its script id.
ITEMS = (
    ("automation", "1792566409191", "voice_play_music_fast_via_music_assistant"),
    ("automation", "1792602065968", "music_download_albums_played_from_spotify"),
    ("automation", "1792565711045", "kitchen_lower_sonos_while_the_echo_listens"),
    ("script", "voice_send_music_request_to_lidarr", "voice_send_music_request_to_lidarr"),
    ("script", "voice_start_music_assistant_playback", "voice_start_music_assistant_playback"),
    ("automation", "media_arr_alerts", "media_arr_alerts"),
    ("automation", "media_health_report", "media_health_report"),
    ("automation", "media_stuck_downloads", "media_stuck_downloads"),
    ("automation", "1792841672349", "voice_announce_to_the_house"),
    ("script", "voice_announce", "voice_announce"),
    ("automation", "1792848361589", "voice_media_controls"),
)

# A webhook ID is the only thing that lets a caller in, and this repo is public, so every
# one is written as <redacted>, whatever it looks like (a random part can contain
# underscores, so keeping a "prefix" could leak some of it). The real ones live in
# Home Assistant and in 1Password; the automation's alias says which is which.
def redact(config: dict) -> dict:
    config = json.loads(json.dumps(config))
    for trigger in config.get("triggers", []):
        if trigger.get("trigger") == "webhook" and "webhook_id" in trigger:
            trigger["webhook_id"] = "<redacted>"
    return config


class Dumper(yaml.SafeDumper):
    pass


def represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    # Long templates fold onto several lines; YAML joins them back with spaces.
    style = "|" if "\n" in value else ">" if len(value) > 80 else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


Dumper.add_representer(str, represent_str)
# Indent list items under their key, like the rest of the repo's YAML.
Dumper.increase_indent = lambda self, flow=False, indentless=False: yaml.SafeDumper.increase_indent(self, flow, False)


def raw_path(raw_dir: Path, kind: str, config_id: str) -> Path:
    return raw_dir / kind / f"{config_id}.json"


def fetch(kind: str, config_id: str, raw_dir: Path | None) -> dict:
    token = os.environ.get("HA_TOKEN")
    if not token:
        raise SystemExit("HA_TOKEN is not set: create a long-lived access token for an admin user")
    base_url = os.environ.get("HA_URL", HA_URL)
    request = urllib.request.Request(
        f"{base_url}/api/config/{kind}/config/{config_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        config = json.load(response)
    if raw_dir:
        path = raw_path(raw_dir, kind, config_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return config


def render(kind: str, name: str, config: dict) -> str:
    entity = f"{kind}.{name}"
    header = (
        f'# Copy of the Home Assistant {kind} "{config["alias"]}" ({entity}),\n'
        "# written by scripts/export-ha-config.py. Home Assistant is the live copy:\n"
        "# change it there, then re-export. home-assistant/README.md says how to restore it.\n"
    )
    body = yaml.dump(config, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100)
    if yaml.safe_load(body) != config:
        raise SystemExit(f"{entity}: the YAML does not load back to what Home Assistant returned")
    return header + body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="read the configs from --raw-dir instead of Home Assistant")
    parser.add_argument("--raw-dir", type=Path, help="where to save (or, with --offline, read) each config as JSON")
    args = parser.parse_args()
    if args.offline and not args.raw_dir:
        parser.error("--offline needs --raw-dir")

    for kind, config_id, name in ITEMS:
        if args.offline:
            config = json.loads(raw_path(args.raw_dir, kind, config_id).read_text(encoding="utf-8"))
        else:
            config = fetch(kind, config_id, args.raw_dir)
        path = OUT_DIR / f"{kind}s" / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(kind, name, redact(config)), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
