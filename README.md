# Manaforge

[![Tests](https://github.com/RyMeep128/Manaforge/actions/workflows/tests.yml/badge.svg)](https://github.com/RyMeep128/Manaforge/actions/workflows/tests.yml)

Manaforge is a local-first Magic desktop workspace for building decks, consulting
rules, sharing decks through private libraries, and preparing proxies for print.
The desktop tools use Python/PyQt6; gameplay uses Unity with Java/XMage.
Manaforge is in alpha development.

## Install and launch

Use **Manaforge-Setup.exe** for the Windows installer, or extract the entire
**Manaforge-Windows.zip** for portable use. Both include Python and dependencies.
See [installation and updates](docs/installation-and-updates.md) for build
artifacts, setup, artwork modes, updates, diagnostics, and recovery.

For source development, run **Launch Manaforge.cmd** or `python run_manaforge.py`
in the configured environment. The Windows launcher reuses the environment
created by `Mtg_Projects/mtg_proxy/Setup Print Proxy Prep.cmd`.
CI targets Python 3.12 and 3.13. Windows is the packaged target.

## Workspaces

| Workspace | Guide |
| --- | --- |
| Deck Editor | [Build and organize decks](Mtg_Projects/mtg_editor/README.md), [deck setup](docs/deck-setup.md), [discovery](docs/deck-builder-discovery.md) |
| Rules & Rulings | [Local card data and search](docs/local-card-search.md) |
| Print Studio | [Print guide](Mtg_Projects/mtg_proxy/README.md), [printer setup](docs/printing-roadmap.md) |
| Browse Online | [Private library setup and use](docs/self-hosted-library.md) |
| Play | [Unity gameplay and development status](docs/play.md) |
| Card Database | [Settings workspace](docs/card-database-workspace.md) |

Source Play has one **Start Game** button for Unity, with format, deck, and
mana-payment selectors. A built Windows Unity player and pinned XMage runtime
are required. Installed builds retain the Play release gate; source availability
is not a claim of complete gameplay acceptance.

Your decks, artwork, and preferences remain local. Runtime data defaults to
`%LOCALAPPDATA%/PrintProxyPrep`; set `PRINT_PROXY_PREP_DATA_DIR` for isolated data.
Normal use requires no library account or library server.

## Development

Work on `main` in the canonical workspace and follow [AGENTS.md](AGENTS.md) and
[the development workflow](docs/development-workflow.md). Run test suites through
GitHub Actions. **Build Manaforge.cmd** builds the unified Windows application;
[Unity build tooling](Mtg_Projects/mtg_play_unity/README.md) covers the game player.
Application versions remain prereleases; commits and builds do not create releases.

Start with the [documentation index](docs/README.md), [current roadmap](docs/roadmap.md),
and [shared component boundaries](docs/shared-components.md). Help → Send Feedback
supports reports and local drafts; maintainer setup is in the
[feedback relay guide](feedback-relay/README.md).
