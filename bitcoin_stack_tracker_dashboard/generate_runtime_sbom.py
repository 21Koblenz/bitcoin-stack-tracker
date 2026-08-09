#!/usr/bin/env python3
"""Generate a compact CycloneDX runtime SBOM from the built add-on container."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4


def _run(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return ""


def _apk_components() -> list[dict]:
    result: list[dict] = []
    # Alpine versions normally end in -rN. Split from the right around the
    # version start while allowing dashes in package names.
    pattern = re.compile(r"^(?P<name>.+)-(?P<version>[0-9][A-Za-z0-9._+~-]*-r[0-9]+)$")
    for line in sorted(set(_run("apk", "info", "-v").splitlines())):
        value = line.strip()
        if not value:
            continue
        match = pattern.match(value)
        if match:
            name, version = match.group("name"), match.group("version")
        else:
            name, version = value, "unknown"
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "properties": [{"name": "bst:package-manager", "value": "apk"}],
        }
        if version != "unknown":
            component["purl"] = f"pkg:apk/alpine/{name}@{version}"
        result.append(component)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    components = _apk_components()
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "bitcoin-stack-tracker-tor-gateway",
                "version": args.version,
            },
            "properties": [
                {"name": "bst:inventory-kind", "value": "built-container-runtime"},
                {"name": "bst:generated-by", "value": "bitcoin-stack-tracker build"},
            ],
        },
        "components": components,
    }
    Path(args.output).write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
