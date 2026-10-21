#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""
Export Radarr's and Sonarr's live quality setup into Configarr templates.

    op run --env-file configarr/local.env -- uv run scripts/export-arr-config.py --raw-dir DIR
    uv run scripts/export-arr-config.py --offline --raw-dir DIR

Writes configarr/templates/homelab-{radarr,sonarr}.yml. The first form reads the
APIs (it needs the keys) and saves every response under DIR; the second rebuilds
the templates from those files with no keys or network. This was run once, on
2026-10-21, to move the profiles Profilarr had last synced (2025-11-07) into
git without changing what gets grabbed. From then on the templates are the
source of truth: edit them, not the UI, because Configarr reverts the UI hourly.
Re-running the exporter overwrites the templates with whatever the UI says now.

Each template is shaped so that a Configarr v1.35.0 dry run against the same
instance reports no changes. The rules come from reading Configarr's diff code:

- Custom formats become inline `customFormatDefinitions` with `hl-<arr>-<slug>`
  ids. Configarr compares specifications and their fields by position, so both
  keep the server's order, and the API's field list becomes a map in that order.
- Every profile lists every custom format's score, zeros included, and sets
  `reset_unmatched_scores`, so formats added later in the UI are zeroed too.
  Without one explicit score Configarr skips a profile's scoring entirely.
- `qualities` is the API's `items` reversed, at both levels: Configarr reverses
  the list, and each group's members, back into API order.
- Quality definitions that are "unlimited" (null) in the API are left out of
  that field; Configarr has no way to declare null and only compares what is set.

The saved responses are sorted like `jq -S`, so DIR/<arr>/qualityprofile.json
and customformat.json double as the snapshot to compare against after a sync.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "configarr" / "templates"
CONFIGMAP_LIMIT = 1024 * 1024

ARRS = {
    "radarr": {"url": "https://radarr.gregpakes.co.uk", "env": "RADARR"},
    "sonarr": {"url": "https://sonarr.gregpakes.co.uk", "env": "SONARR"},
}


class Flow(dict):
    """A mapping emitted on one line, for score and size tables."""


class FlowList(list):
    """A short list emitted on one line."""


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(Flow, lambda d, data: d.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True))
Dumper.add_representer(FlowList, lambda d, data: d.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True))
# Indent list items under their key, like the rest of the repo's YAML.
Dumper.increase_indent = lambda self, flow=False, indentless=False: yaml.SafeDumper.increase_indent(self, flow, False)


# What the exporter reads, then everything else a Configarr dry run GETs, so that
# scripts/arr-api-replay.py can stand in for the arr. None of these responses holds
# a secret: the arrs return download-client passwords as "********".
ENDPOINTS = (
    "system/status",
    "customformat",
    "qualityprofile",
    "qualitydefinition",
    "tag",
    "config/naming",
    "config/mediamanagement",
    "rootfolder",
    "delayprofile",
)
REPLAY_ONLY = (
    "",
    "language",
    "health",
    "config/ui",
    "config/downloadclient",
    "downloadclient",
    "downloadclient/schema",
    "releaseprofile",
    "remotepathmapping",
)


def raw_path(raw_dir: Path, arr: str, endpoint: str) -> Path:
    return raw_dir / arr / f"{endpoint.replace('/', '-') or 'api'}.json"


def api_url(base_url: str, endpoint: str) -> str:
    # "" is the bare /api root, which Sonarr's client reads to pick v3 or v5.
    return f"{base_url}/api/v3/{endpoint}" if endpoint else f"{base_url}/api"


def fetch(arr: str, raw_dir: Path | None) -> dict[str, object]:
    prefix = ARRS[arr]["env"]
    key = os.environ.get(f"{prefix}_API_KEY")
    if not key:
        raise SystemExit(f"{arr}: {prefix}_API_KEY is not set; run under `op run --env-file configarr/local.env`")
    base_url = os.environ.get(f"{prefix}_URL", ARRS[arr]["url"])

    responses = {}
    for endpoint in ENDPOINTS + (REPLAY_ONLY if raw_dir else ()):
        request = urllib.request.Request(api_url(base_url, endpoint), headers={"X-Api-Key": key, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            responses[endpoint] = json.load(response)
        if raw_dir:
            path = raw_path(raw_dir, arr, endpoint)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(responses[endpoint], sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return responses


def load(arr: str, raw_dir: Path) -> dict[str, object]:
    return {endpoint: json.loads(raw_path(raw_dir, arr, endpoint).read_text(encoding="utf-8")) for endpoint in ENDPOINTS}


def slug(name: str) -> str:
    s = name.lower().replace("+", " plus ").replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "cf"


def assign_ids(arr: str, cfs: list[dict]) -> dict[int, str]:
    ids: dict[int, str] = {}
    taken: set[str] = set()
    for cf in sorted(cfs, key=lambda c: c["id"]):
        base = f"hl-{arr}-{slug(cf['name'])}"
        cid, n = base, 2
        while cid in taken:
            cid, n = f"{base}-{n}", n + 1
        taken.add(cid)
        ids[cf["id"]] = cid
    return ids


def cf_definition(cf: dict, cid: str) -> dict:
    specs = []
    for spec in cf["specifications"]:
        # Positional comparison: a field without a value still holds its slot.
        fields = {f["name"]: f.get("value") for f in spec["fields"]}
        specs.append(
            {
                "name": spec["name"],
                "implementation": spec["implementation"],
                "negate": spec["negate"],
                "required": spec["required"],
                "fields": fields,
            }
        )
    return {
        "configarr_id": cid,
        "name": cf["name"],
        "includeCustomFormatWhenRenaming": cf["includeCustomFormatWhenRenaming"],
        "specifications": specs,
    }


def item_name(item: dict) -> str:
    return item["name"] if item.get("items") else item["quality"]["name"]


def item_id(item: dict) -> int:
    return item["id"] if item.get("items") else item["quality"]["id"]


def profile_qualities(profile: dict, warnings: list[str]) -> list[dict]:
    out = []
    for item in reversed(profile["items"]):
        entry: dict = {"name": item_name(item)}
        if item.get("items"):
            members = item["items"]
            if any(m["allowed"] != item["allowed"] for m in members):
                warnings.append(f"{profile['name']}: group '{item['name']}' has members whose allowed flag differs from the group")
            entry["qualities"] = FlowList(m["quality"]["name"] for m in reversed(members))
        if not item["allowed"]:
            entry["enabled"] = False
        out.append(entry)
    return out


def quality_profile(arr: str, profile: dict, warnings: list[str]) -> dict:
    cutoff = next((item_name(i) for i in profile["items"] if item_id(i) == profile["cutoff"]), None)
    if cutoff is None:
        raise SystemExit(f"{arr}: profile '{profile['name']}' cutoff {profile['cutoff']} matches no item")

    if profile["upgradeAllowed"]:
        upgrade = {
            "allowed": True,
            "until_quality": cutoff,
            "until_score": profile["cutoffFormatScore"],
            "min_format_score": profile["minUpgradeFormatScore"],
        }
    else:
        # Configarr always writes cutoffFormatScore 1 and minUpgradeFormatScore 1 when
        # upgrades are off. Radarr ignores both then, but a dry run lists the change.
        upgrade = {"allowed": False, "until_quality": cutoff}
        for field in ("cutoffFormatScore", "minUpgradeFormatScore"):
            if profile[field] != 1:
                warnings.append(
                    f"{profile['name']}: upgrades are off and {field} is {profile[field]}; Configarr will set it to 1 (no effect while upgrades are off)"
                )

    out = {"name": profile["name"]}
    if arr == "radarr":
        out["language"] = profile["language"]["name"]
    out["min_format_score"] = profile["minFormatScore"]
    out["upgrade"] = upgrade
    out["reset_unmatched_scores"] = {"enabled": True}
    out["qualities"] = profile_qualities(profile, warnings)
    return out


def quality_definitions(qds: list[dict]) -> dict:
    rows = []
    for qd in qds:
        row = Flow(quality=qd["quality"]["name"])
        if qd["title"] != qd["quality"]["name"]:
            row["title"] = qd["title"]
        for key, field in (("min", "minSize"), ("preferred", "preferredSize"), ("max", "maxSize")):
            if qd.get(field) is not None:
                row[key] = qd[field]
        rows.append(row)
    return {"qualities": rows}


def without_id(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if k != "id"}


def delay_profiles(profiles: list[dict], tags: dict[int, str]) -> dict:
    keys = (
        "enableUsenet",
        "enableTorrent",
        "preferredProtocol",
        "usenetDelay",
        "torrentDelay",
        "bypassIfHighestQuality",
        "bypassIfAboveCustomFormatScore",
        "minimumCustomFormatScore",
        "order",
    )
    out: dict = {}
    additional = []
    for p in profiles:
        entry = {k: p[k] for k in keys if k in p}
        if p.get("tags"):
            entry["tags"] = [tags[t] for t in p["tags"]]
            additional.append(entry)
        else:
            out["default"] = entry
    if additional:
        out["additional"] = additional
    return out


def export(arr: str, api: dict) -> tuple[Path, list[str]]:
    get = api.__getitem__
    status = get("system/status")
    cfs = sorted(get("customformat"), key=lambda c: c["id"])
    profiles = sorted(get("qualityprofile"), key=lambda p: p["id"])
    warnings: list[str] = []

    ids = assign_ids(arr, cfs)
    ordered = sorted(cfs, key=lambda c: (c["name"].lower(), c["id"]))
    scores = {p["name"]: {f["format"]: f["score"] for f in p["formatItems"]} for p in profiles}

    custom_formats = []
    for cf in ordered:
        assign = [Flow(name=p["name"], score=scores[p["name"]].get(cf["id"], 0)) for p in profiles]
        custom_formats.append({"trash_ids": FlowList([ids[cf["id"]]]), "assign_scores_to": assign})

    tags = {t["id"]: t["label"] for t in get("tag")}
    template = {
        "customFormatDefinitions": [cf_definition(cf, ids[cf["id"]]) for cf in ordered],
        "custom_formats": custom_formats,
        "quality_profiles": [quality_profile(arr, p, warnings) for p in profiles],
        "quality_definition": quality_definitions(get("qualitydefinition")),
        "media_naming_api": without_id(get("config/naming")),
        "media_management": without_id(get("config/mediamanagement")),
        "root_folders": [r["path"] for r in get("rootfolder")],
        "delay_profiles": delay_profiles(get("delayprofile"), tags),
    }

    header = (
        f"# {arr.capitalize()} quality setup for Configarr: custom formats, quality profiles, sizes,\n"
        f"# naming, media management, root folders and delay profiles.\n"
        f"#\n"
        f"# Exported by scripts/export-arr-config.py from {arr.capitalize()} {status['version']} on {dt.date.today()}.\n"
        f"# This file is now the source of truth: Configarr reverts UI changes every hour.\n"
        f"# See configarr/README.md before editing.\n"
    )
    body = yaml.dump(template, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=1000)
    path = TEMPLATE_DIR / f"homelab-{arr}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body, encoding="utf-8")

    print(f"{arr}: {status['version']}, {len(cfs)} custom formats, {len(profiles)} profiles -> {path.relative_to(REPO_ROOT)}")
    return path, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--only", choices=list(ARRS), help="export one arr instead of both")
    parser.add_argument("--raw-dir", type=Path, help="save the API responses here, or read them from here with --offline")
    parser.add_argument("--offline", action="store_true", help="build from --raw-dir instead of calling the APIs")
    args = parser.parse_args()
    if args.offline and not args.raw_dir:
        parser.error("--offline needs --raw-dir")

    arrs = [args.only] if args.only else list(ARRS)
    # Read everything before writing anything, so a failed export still leaves the raw files.
    apis = {arr: load(arr, args.raw_dir) if args.offline else fetch(arr, args.raw_dir) for arr in arrs}

    failed = False
    for arr, api in apis.items():
        path, warnings = export(arr, api)
        for w in warnings:
            print(f"  warning: {w}")
        size = path.stat().st_size
        print(f"  ConfigMap data {size / 1024:.0f} KiB of {CONFIGMAP_LIMIT // 1024} KiB")
        failed |= size >= CONFIGMAP_LIMIT
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
