# msmorgan agent plugins

This repository is the central `msmorgan` marketplace for agent plugins. Each
plugin keeps its canonical implementation in its own source repository while
Claude Code and Codex use native catalogs here for discovery and installation.

The migration is intentionally incremental. A plugin moves into this catalog
when its singleton marketplace is retired.

## Catalog maintenance

[`catalog.json`](catalog.json) is the sole source of truth for marketplace
metadata. Do not edit the generated Claude or Codex manifests directly.

After changing the catalog, regenerate both manifests:

```sh
python3 scripts/generate_manifests.py
```

To verify that committed manifests are current without modifying them:

```sh
python3 scripts/generate_manifests.py --check
```

CI runs this check on every push and pull request, so hand-edited or stale
generated manifests cannot land unnoticed. CI also runs each harness's own
validator, which enforces rules the generator cannot see.

### Renaming or removing a plugin

Removing a plugin from `plugins`, or changing its `name`, breaks anyone who
already installed it: the harness reports `plugin-not-found`. Record the change
in the top-level `renames` map so existing users migrate automatically. Map the
former name to its current name, or to `null` if the plugin is gone:

```json
"renames": {
  "old-name": "new-name",
  "retired-plugin": null
}
```

Treat the map as append-only history. Keep old entries after you expect
everyone to have migrated, and record a later rename as a second entry rather
than editing the first — chains resolve through both. The generator rejects a
map that cycles, dead-ends, or reuses a live plugin name as a key.

This is emitted into the Claude manifest only. Codex accepts the field without
complaint, but its handling there is unverified, so it is not written.

## Plugins

| Plugin | Purpose |
| --- | --- |
| `jj-sensei` | Teach your agents Jujutsu. |
| `baton` | Relay unfinished work between agents. |
| `mtg-rules` | Judge-grade Magic: The Gathering rules answers, grounded in the Comprehensive Rules with verified citations. |
| `comment-gardener` | Conservative pruning and polishing for code comments and docstrings. |
| `jj-kata` | Safe Jujutsu workspace coordination for parallel agents, with optional file-backed Kanban. |
| `idris2-guide` | Make your agents productive and rigorous in Idris 2. |
| `test-appraiser` | Find tests that create false assurance. |

## Install with Claude Code

Register the marketplace once:

```sh
claude plugin marketplace add msmorgan/marketplace
```

Install jj-sensei:

```sh
claude plugin install jj-sensei@msmorgan
```

## Install with Codex

Register the marketplace once:

```sh
codex plugin marketplace add msmorgan/marketplace
```

Install jj-sensei:

```sh
codex plugin add jj-sensei@msmorgan
```

Start a new session after installing or updating a plugin so its skills and
tools are loaded.

## Use with Antigravity CLI (`agy`)

Agy 1.1 does not expose a command for registering arbitrary third-party
marketplaces. Install through the Claude marketplace, then import the installed
plugin:

```sh
agy plugin import claude
```

Run the same command again after updating the plugin through Claude.

## Publishing plugin changes

Each plugin repository remains the source of truth for its implementation. To
publish a change:

1. Update and validate the plugin in its own repository.
2. Bump the plugin manifest version as required by the harness.
3. Push the plugin repository.

No marketplace change is needed for an ordinary plugin release. Consumers can
refresh with:

```sh
claude plugin marketplace update msmorgan
claude plugin update jj-sensei@msmorgan

codex plugin marketplace upgrade msmorgan
codex plugin add jj-sensei@msmorgan

agy plugin import claude
```

Only edit `catalog.json` when adding or removing a plugin, renaming one, or
changing catalog metadata. Regenerate both harness manifests before publishing,
and record any rename or removal in `renames`.
