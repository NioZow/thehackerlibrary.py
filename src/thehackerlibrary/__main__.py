import argparse
import asyncio
import csv
import json
import sys
from functools import wraps
from pathlib import Path

import aiohttp
import yaml
from sqlalchemy.orm import Session
from tabulate import tabulate

from thehackerlibrary.config import (
    FEEDS,
    HEALTHCHECK_BYPASS_DOMAINS,
    RSS_FEEDS,
    X_ID,
    X_REFRESH_TOKEN,
    YOUTUBE_PLAYLISTS,
    engine,
)
from thehackerlibrary.db import Exporter, Importer
from thehackerlibrary.feed import Feed, RssFeed
from thehackerlibrary.logger import logger
from thehackerlibrary.media.twitter import Twitter
from thehackerlibrary.media.youtube import get_posts_from_playlist
from thehackerlibrary.model import Resources, User
from thehackerlibrary.ai.analyzer import AnalysisResult, analyze
from thehackerlibrary.resources import (
    add_resource,
    remove_orphaned_authors,
    remove_orphaned_sections,
    remove_orphaned_tags,
    remove_orphaned_topics,
    update_accepted_resources,
)


def output_data(func):
    """Decorator to easily output data as json, yaml, csv, table based on the user output argument"""

    @wraps(func)
    def wrapper(args):
        # execute the function and get its output
        data = func(args)

        try:
            # format the data
            if args.output == "table":
                print(tabulate(data, headers="keys", tablefmt="pretty"))
            elif args.output == "csv":
                writer = csv.DictWriter(sys.stdout, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            elif args.output in ("yml", "yaml"):
                print(yaml.dump(data, sort_keys=False))
            elif args.output == "json":
                print(json.dumps(data, indent=2))
            else:
                raise Exception("unkown output format")
        except (TypeError, ValueError) as e:
            logger.fatal_error(f"Error serializing to JSON: {e}")
        except AttributeError:
            logger.fatal_error("Internal error: output argument not supported.")
        except Exception as e:
            logger.fatal_error(f"Error: {e}")

        return data

    return wrapper


class Dispatcher:
    @staticmethod
    def dispatch(args):
        try:
            if args.action == "import":
                # special handling because can't name it import
                import_data(args)
            elif args.action == "analyze":
                # special handling because the function is named analyze_cmd
                analyze_cmd(args)
            elif (func := globals().get(args.action)) is not None:
                func(args)
            else:
                logger.error(
                    f"Command {args.action} has not yet been developped. Stacktrace: "
                )
        except Exception as e:
            logger.error("Unexpected error.")
            raise e


def export(args):
    Exporter(args.output_directory).export_all()


def import_data(args):
    Importer(args.output_directory).import_all()


def _apply_analysis(url: str, result: AnalysisResult) -> None:
    """Persist tags and/or quality verdict from an AnalysisResult to the database."""
    from urllib.parse import urlparse

    from thehackerlibrary.model import Tags

    if result.fetch_failed:
        if urlparse(url).netloc in HEALTHCHECK_BYPASS_DOMAINS:
            logger.info(f"Skipping rejection for bypassed domain: {url}")
        else:
            with Session(engine) as sess:
                resource = sess.query(Resources).filter_by(url=url).first()
                if resource:
                    resource.accepted = False
                    sess.commit()
            logger.warning(f"Rejected '{url}': could not fetch the post.")
        return

    with Session(engine) as sess:
        resource = sess.query(Resources).filter_by(url=url).first()
        if not resource:
            return

        for tag_name in result.tags:
            tag_obj = sess.query(Tags).filter_by(name=tag_name).first()
            if not tag_obj:
                tag_obj = Tags(name=tag_name)
                sess.add(tag_obj)
                logger.info(f"Created new tag: {tag_name}")
            if tag_obj not in resource.tags:
                resource.tags.append(tag_obj)

        if not result.accepted:
            resource.accepted = False
            logger.warning(
                f"Rejected '{resource.title}' ({url}): {result.reason}"
            )

        sess.commit()


@output_data
def scrape(args):
    from thehackerlibrary.model import Tags

    resources = []
    if args.feed:
        for feed_url in FEEDS:
            feed = Feed(feed_url)
            resources += feed.get_posts()

        for feed_url in RSS_FEEDS:
            feed = RssFeed(feed_url)
            resources += feed.get_posts()

    if args.youtube:
        for playlist_id in YOUTUBE_PLAYLISTS:
            resources += get_posts_from_playlist(playlist_id)

    if args.twitter:
        twitter = (
            Twitter.from_refresh_token(X_REFRESH_TOKEN, X_ID)
            if X_REFRESH_TOKEN is not None
            else Twitter.interactive_auth()
        )

        resources += asyncio.run(twitter.get_posts_from_bookmarks())

    if args.post:
        resource, exists = add_resource(args.post, "Post", accepted=args.reviewed)
        if not exists:
            resources.append(resource)

    if resources:
        all_tags = []
        with Session(engine) as sess:
            all_tags = [t.name for t in sess.query(Tags).all()]

        for resource in resources:
            result = analyze(resource.url, all_tags)
            _apply_analysis(resource.url, result)
            if result.tags:
                logger.info(
                    f"Auto-tagged '{resource.title}' with: {', '.join(result.tags)}"
                )

    return [
        {
            "title": resource.title,
            "date": resource.date,
            "url": resource.url,
        }
        for resource in resources
    ]


def role(args):
    if args.subaction == "set":
        with Session(engine) as session:
            try:
                user = session.query(User).filter(User.email == args.user).first()
                user.role = args.role
                session.commit()
            except Exception as e:
                logger.error(f"Error: {e}")


def healthcheck(args):
    async def get_up(session, url) -> tuple[str, bool]:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=not args.disable_ssl_verification,
            ) as res:
                return (
                    url,
                    res.status == 200 or res.headers.get("server") == "cloudflare",
                )
        except (TimeoutError, aiohttp.ClientConnectorError):
            return (url, False)
        except Exception as e:
            # Unknown error — assume up to avoid false positives
            logger.warning(f"Error for {url}: {e}")
            return (url, True)

    async def healthcheck_async(args):
        from urllib.parse import urlparse

        with Session(engine) as db_sess:
            async with aiohttp.ClientSession() as http_sess:
                if args.post:
                    urls = [args.post]
                else:
                    query = _build_filter_query(
                        args,
                        db_sess.query(Resources),
                        default_accepted=True,  # default: accepted posts only
                    )
                    urls = [
                        r.url for r in query.all()
                        if urlparse(r.url).netloc not in HEALTHCHECK_BYPASS_DOMAINS
                    ]

                tasks = [get_up(http_sess, url) for url in urls]

                for coro in asyncio.as_completed(tasks):
                    try:
                        url, up = await coro
                        if not up:
                            logger.warning(f"{url} is not up.")

                            if args.mark_as_rejected:
                                resource = (
                                    db_sess.query(Resources)
                                    .filter(Resources.url == url)
                                    .first()
                                )
                                resource.accepted = False
                                db_sess.commit()
                    except FileExistsError as e:
                        logger.error(f"Error: {e}")

    asyncio.run(healthcheck_async(args))


def clean(args):
    logger.info(f"Removed {remove_orphaned_sections()} orphaned sections.")
    logger.info(f"Removed {remove_orphaned_topics()} orphaned topics.")
    logger.info(f"Removed {remove_orphaned_tags()} orphaned tags.")
    logger.info(f"Removed {remove_orphaned_authors()} orphaned authors.")


_SENTINEL = object()


def _build_filter_query(args, base_query, default_accepted=_SENTINEL):
    """Apply common status/author/since filters to a SQLAlchemy query.

    Args:
        default_accepted: Accepted value to filter by when no status flag is given.
                          Use Ellipsis (...) to skip default status filtering.
    """
    from datetime import datetime

    from thehackerlibrary.model import Authors

    if args.accepted:
        base_query = base_query.filter(Resources.accepted == True)
    elif args.denied:
        base_query = base_query.filter(Resources.accepted == False)
    elif args.pending:
        base_query = base_query.filter(Resources.accepted == None)
    elif default_accepted is not _SENTINEL:
        base_query = base_query.filter(Resources.accepted == default_accepted)

    if args.author:
        base_query = base_query.filter(
            Resources.authors.any(Authors.name == args.author)
        )

    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            logger.fatal_error("--since date must be in YYYY-MM-DD format.")
        base_query = base_query.filter(Resources.date >= since_date)

    return base_query


def analyze_cmd(args):
    """Tag posts and evaluate their quality in a single LLM call."""
    from thehackerlibrary.model import Tags
    from tqdm import tqdm

    with Session(engine) as sess:
        all_tags = [t.name for t in sess.query(Tags).all()]

        if args.post:
            urls = [args.post]
        else:
            query = _build_filter_query(
                args,
                sess.query(Resources),
                default_accepted=None,  # default: pending posts
            )
            urls = [r.url for r in query.all()]

    tagged_count = 0
    rejected_count = 0
    for url in tqdm(urls, desc="Analyzing posts", unit="post"):
        result = analyze(url, all_tags)
        _apply_analysis(url, result)
        if result.tags:
            tagged_count += 1
        if not result.accepted:
            rejected_count += 1

    logger.info(f"Tagged {tagged_count} resource(s), rejected {rejected_count}.")


def update(args):
    update_accepted_resources(dry_run=args.dry_run)


@output_data
def ls(args):
    """List resources in the database with various filtering options."""
    with Session(engine) as sess:
        query = sess.query(Resources)

        if args.no_tags:
            query = query.filter(~Resources.tags.any())
        if args.accepted:
            query = query.filter(Resources.accepted == True)
        if args.denied:
            query = query.filter(Resources.accepted == False)
        if args.pending:
            query = query.filter(Resources.accepted == None)

        resources = query.all()

        return [
            {
                "id": resource.id,
                "title": resource.title,
                "url": resource.url,
                "date": resource.date.isoformat() if resource.date else None,
                "accepted": resource.accepted,
                "authors": ", ".join([author.name for author in resource.authors]),
                "tags": ", ".join([tag.name for tag in resource.tags]),
            }
            for resource in resources
        ]


def _add_filter_args(p, post_help, default_hint=""):
    """Attach shared filter arguments (--post, --accepted/--denied/--pending, --author, --since)."""
    p.add_argument("--post", "-p", metavar="URL", type=str, help=post_help)
    status = p.add_mutually_exclusive_group()
    status.add_argument(
        "--accepted",
        action="store_true",
        help="Process only accepted posts." + (f" {default_hint}" if default_hint else ""),
    )
    status.add_argument(
        "--denied",
        action="store_true",
        help="Process only denied/rejected posts.",
    )
    status.add_argument(
        "--pending",
        action="store_true",
        help="Process only pending posts (accepted field is NULL in the database).",
    )
    p.add_argument(
        "--author",
        metavar="NAME",
        type=str,
        help="Process only posts written by this exact author name.",
    )
    p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        type=str,
        help="Process only posts published on or after this date (inclusive).",
    )


def main():
    parser = argparse.ArgumentParser(description="TheHackerLibrary cli")
    subparsers = parser.add_subparsers(
        dest="action", help="command to perform", required=True
    )

    clean = subparsers.add_parser("clean", help="Remove orphans tags and authors.")

    update_resources_parser = subparsers.add_parser(
        "update",
        help="Update the accepted state of resources based on whitelist/blacklist.",
    )
    update_resources_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making actual changes to the database.",
    )

    healthcheck = subparsers.add_parser(
        "healthcheck",
        help="Check that resource URLs are still reachable.",
        description=(
            "Verifies that stored post URLs respond with HTTP 200. "
            "Domains listed under healthcheck.bypass_domains in the config are always skipped. "
            "Defaults to accepted posts. Use --pending to check unreviewed posts instead."
        ),
    )
    healthcheck.add_argument(
        "-m",
        "--mark-as-rejected",
        action="store_true",
        help="Automatically reject posts whose URL is no longer reachable.",
    )
    healthcheck.add_argument(
        "--disable-ssl-verification",
        action="store_true",
        help="Disable SSL certificate validation (workaround for misconfigured servers).",
    )
    _add_filter_args(
        healthcheck,
        post_help="Check a single specific URL instead of querying the database.",
        default_hint="By default, accepted posts are checked.",
    )

    resource_parser = subparsers.add_parser("role", help="Manage roles.")
    role_subparsers = resource_parser.add_subparsers(dest="subaction")
    add_role = role_subparsers.add_parser("set")
    add_role.add_argument("user", help="email of the user to add a role to")
    add_role.add_argument("role", help="role to set")

    import_parser = subparsers.add_parser(
        "import", help="import data from yaml to the db"
    )
    import_parser.add_argument(
        "output_directory",
        help="Directory to import the data from",
        type=Path,
    )

    export_parser = subparsers.add_parser(
        "export", help="export data from the db to yaml"
    )
    export_parser.add_argument(
        "output_directory",
        help="Directory to export the data to",
        type=Path,
    )

    scrape_parser = subparsers.add_parser(
        "scrape", help="scrape feeds, medias and more for new blog posts"
    )
    scrape_parser.add_argument("--feed", "-f", help="Scrape feeds", action="store_true")
    scrape_parser.add_argument(
        "--twitter",
        "-t",
        "-x",
        help="Scrape twitter my own bookmarks",
        action="store_true",
    )
    scrape_parser.add_argument(
        "--youtube",
        "-y",
        help="Scrape youtube playlists description for posts",
        action="store_true",
    )
    scrape_parser.add_argument("--post", "-p", help="Scrape a specific post.", type=str)
    scrape_parser.add_argument(
        "--reviewed",
        "-r",
        help="Mark the resources as reviewed.",
        action="store_true",
        default=None,
    )
    scrape_parser.add_argument(
        "--output",
        "-o",
        help="Output format (e.g. json, csv, table, yml)",
        default="table",
        choices=["json", "csv", "table", "yml", "yaml"],
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Tag posts and evaluate their quality using AI.",
        description=(
            "Uses the LLM (via LiteLLM) to assign tags and assess quality in a single call. "
            "Posts that lack technical depth are automatically rejected in the database "
            "and the reason is logged. "
            "Defaults to pending posts (accepted = NULL). "
            "Use --accepted to re-evaluate already-accepted posts, "
            "or --post to process a single URL directly."
        ),
    )
    _add_filter_args(
        analyze_parser,
        post_help="Analyze a single specific post by URL, bypassing the database query.",
    )

    list_parser = subparsers.add_parser("ls", help="List resources in the database.")
    list_parser.add_argument(
        "--no-tags", action="store_true", help="Show posts without any tags."
    )

    # Mutually exclusive group for accepted/denied/pending status
    status_group = list_parser.add_mutually_exclusive_group()
    status_group.add_argument(
        "--accepted", action="store_true", help="Show accepted posts."
    )
    status_group.add_argument(
        "--denied", action="store_true", help="Show denied posts."
    )
    status_group.add_argument(
        "--pending",
        action="store_true",
        help="Show posts that have not yet been accepted.",
    )

    list_parser.add_argument(
        "--output",
        "-o",
        help="Output format (e.g. json, csv, table, yml)",
        default="table",
        choices=["json", "csv", "table", "yml", "yaml"],
    )

    args = parser.parse_args()
    Dispatcher.dispatch(args)


if __name__ == "__main__":
    main()
