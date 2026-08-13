#!/usr/bin/env python3
"""Generate Claude and Codex marketplace manifests from catalog.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "catalog.json"
OUTPUT_PATHS = {
    "claude": ROOT / ".claude-plugin" / "marketplace.json",
    "codex": ROOT / ".agents" / "plugins" / "marketplace.json",
}
CATEGORIES = {
    "developer-tools": {"claude": "development", "codex": "Developer Tools"},
    "education": {"claude": "education", "codex": "Education"},
    "productivity": {"claude": "productivity", "codex": "Productivity"},
}


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error

    if not isinstance(catalog, dict):
        raise ValueError("catalog root must be an object")

    marketplace = catalog.get("marketplace")
    if not isinstance(marketplace, dict):
        raise ValueError("marketplace must be an object")
    require_string(marketplace.get("name"), "marketplace.name")
    require_string(marketplace.get("displayName"), "marketplace.displayName")
    require_string(marketplace.get("description"), "marketplace.description")

    owner = marketplace.get("owner")
    if not isinstance(owner, dict):
        raise ValueError("marketplace.owner must be an object")
    require_string(owner.get("name"), "marketplace.owner.name")
    require_string(owner.get("email"), "marketplace.owner.email")
    require_string(owner.get("url"), "marketplace.owner.url")

    # The catalog starts empty. This check tightens to reject an empty array
    # once the first plugin is listed.
    plugins = catalog.get("plugins")
    if not isinstance(plugins, list):
        raise ValueError("plugins must be an array")

    names: set[str] = set()
    for index, plugin in enumerate(plugins):
        label = f"plugins[{index}]"
        if not isinstance(plugin, dict):
            raise ValueError(f"{label} must be an object")

        name = require_string(plugin.get("name"), f"{label}.name")
        if name in names:
            raise ValueError(f"duplicate plugin name: {name}")
        names.add(name)

        require_string(plugin.get("description"), f"{label}.description")
        github = require_string(plugin.get("github"), f"{label}.github")
        if github.count("/") != 1 or any(not part for part in github.split("/")):
            raise ValueError(f"{label}.github must use owner/repository form")
        require_string(plugin.get("ref"), f"{label}.ref")

        category = require_string(plugin.get("category"), f"{label}.category")
        if category not in CATEGORIES:
            choices = ", ".join(sorted(CATEGORIES))
            raise ValueError(f"{label}.category must be one of: {choices}")

        subdirectory = plugin.get("subdirectory")
        if subdirectory is not None:
            subdirectory = require_string(subdirectory, f"{label}.subdirectory")
            path = PurePosixPath(subdirectory)
            if path.is_absolute() or ".." in path.parts or subdirectory.startswith("./"):
                raise ValueError(
                    f"{label}.subdirectory must be a repository-relative path "
                    "without './' or '..'"
                )

    validate_renames(catalog.get("renames"), names)

    return catalog


def validate_renames(renames: Any, names: set[str]) -> None:
    """Check that every rename chain terminates at null or a listed plugin.

    Claude Code follows these chains to migrate users off a former plugin name,
    so a chain that cycles or dead-ends leaves them with `plugin-not-found`.
    """
    if renames is None:
        return
    if not isinstance(renames, dict):
        raise ValueError("renames must be an object")

    for former, current in renames.items():
        label = f"renames[{former!r}]"
        require_string(former, f"{label} key")
        if former in names:
            raise ValueError(f"{label} key is also a current plugin name")
        if current is not None:
            require_string(current, label)

    for former in renames:
        seen = [former]
        current = renames[former]
        while current is not None and current not in names:
            if current in seen:
                cycle = " -> ".join(seen + [current])
                raise ValueError(f"renames chain cycles: {cycle}")
            if current not in renames:
                raise ValueError(
                    f"renames[{former!r}] resolves to {current!r}, which is "
                    "neither a listed plugin nor another renames entry"
                )
            seen.append(current)
            current = renames[current]


def source_for(plugin: dict[str, Any], harness: str) -> dict[str, str]:
    github = plugin["github"]
    ref = plugin["ref"]
    subdirectory = plugin.get("subdirectory")
    if subdirectory:
        return {
            "source": "git-subdir",
            "url": f"https://github.com/{github}.git",
            "path": f"./{subdirectory}",
            "ref": ref,
        }
    if harness == "claude":
        return {"source": "github", "repo": github, "ref": ref}
    return {
        "source": "url",
        "url": f"https://github.com/{github}.git",
        "ref": ref,
    }


def generate(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    marketplace = catalog["marketplace"]
    claude_plugins = []
    codex_plugins = []

    for plugin in catalog["plugins"]:
        category = CATEGORIES[plugin["category"]]
        common = {
            "name": plugin["name"],
            "description": plugin["description"],
        }
        claude_plugins.append(
            {
                **common,
                "source": source_for(plugin, "claude"),
                "category": category["claude"],
            }
        )
        codex_plugins.append(
            {
                **common,
                "source": source_for(plugin, "codex"),
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": category["codex"],
            }
        )

    claude: dict[str, Any] = {
        "name": marketplace["name"],
        "description": marketplace["description"],
        "owner": marketplace["owner"],
        "plugins": claude_plugins,
    }
    # Codex tolerates the key but its handling is unverified, so Claude only.
    renames = catalog.get("renames")
    if renames:
        claude["renames"] = renames

    return {
        "claude": claude,
        "codex": {
            "name": marketplace["name"],
            "interface": {"displayName": marketplace["displayName"]},
            "plugins": codex_plugins,
        },
    }


def encode(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def check(outputs: dict[str, dict[str, Any]]) -> bool:
    clean = True
    for harness, path in OUTPUT_PATHS.items():
        expected = encode(outputs[harness])
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError:
            actual = None
        if actual != expected:
            print(f"out of date: {path.relative_to(ROOT)}", file=sys.stderr)
            clean = False
    return clean


def write(outputs: dict[str, dict[str, Any]]) -> None:
    for harness, path in OUTPUT_PATHS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encode(outputs[harness]), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed manifests differ from generated output",
    )
    args = parser.parse_args()

    try:
        outputs = generate(load_catalog())
    except ValueError as error:
        parser.error(str(error))

    if args.check:
        return 0 if check(outputs) else 1
    write(outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
