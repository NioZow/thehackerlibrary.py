# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TheHackerLibrary.py is a CLI tool for scraping, managing, and curating security-related blog posts and resources. It integrates with RSS/Atom feeds, YouTube playlists, and Twitter bookmarks, storing results in a PostgreSQL database.

## Development Setup

Uses `uv` as the package manager and requires Python 3.13+.

```bash
# Install in editable mode
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run the CLI
uv run -m thehackerlibrary -h
```

With NixOS/Nix Flakes, `direnv allow` sets up the environment automatically (PostgreSQL 17, Python 3.13, uv, pytest).

## Common Commands

```bash
thehackerlibrary scrape [--feed] [--twitter] [--youtube] [--post URL] [--reviewed]
thehackerlibrary ls [--accepted|--denied|--pending] [--no-tags] [-o json|csv|table|yaml]
thehackerlibrary update [--dry-run]         # Apply whitelist/blacklist rules to pending
thehackerlibrary import <directory>          # Import YAML into database
thehackerlibrary export <directory>          # Export database to YAML
thehackerlibrary healthcheck [-m]            # Validate resource URLs, mark dead links
thehackerlibrary clean                       # Remove orphaned tags/authors/topics/sections
```

## Architecture

**Data flow:** External sources → feed parsers/scrapers → `add_resource()` + author extraction → `check_whitelist()` → SQLAlchemy models → PostgreSQL

**Key modules:**

- `__main__.py` — CLI dispatcher; routes commands; `@output_data` decorator handles all output formatting
- `model.py` — SQLAlchemy ORM (Resources, Authors, Tags, Topics, Paths, Sections, User management)
- `resources.py` — Core business logic: `add_resource()`, `check_whitelist()`, author extraction from XPath/domain rules
- `config.py` — YAML config loader from `~/.config/thehackerlibrary/config.yml`
- `feed.py` — Atom (`Feed`) and RSS 2.0 (`RssFeed`) parsers
- `media/twitter.py` — Twitter OAuth2 PKCE flow + async bookmark scraping with `t.co` URL resolution
- `media/youtube.py` — YouTube Data API v3 playlist scraping with domain blacklist filtering
- `db/exporter.py` / `db/importer.py` — Bidirectional YAML ↔ database sync

**Whitelist/blacklist rules** (configured in YAML) are evaluated in `check_whitelist()` — returns `True` (accept), `False` (reject), or `None` (pending). Rules match on URL path prefixes and author names.

## Configuration

Config file: `~/.config/thehackerlibrary/config.yml` (see `examples/config.yml`)

Required: `database_url` (PostgreSQL), `feeds` (Atom URLs), `rss` (RSS URLs), `youtube.api_key`, `youtube.playlists`

Optional: `twitter` OAuth2 credentials, `whitelist`/`blacklist` path and author lists, `rules.author_by_domain` and `rules.author_by_xpath` for custom author extraction.

## Database

All primary keys are UUIDs. The schema is defined entirely in `model.py` via SQLAlchemy — `sqlalchemy_utils.create_database()` and `Base.metadata.create_all()` initialize it on first import.

To regenerate ORM models from an existing database (dev dependency):

```bash
sqlacodegen <database_url>
```
