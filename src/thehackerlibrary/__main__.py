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


@output_data
def scrape(args):
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
        except TimeoutError:
            return (url, False)
        except Exception as e:
            # don't know what happened
            # log for later and return True in this case
            logger.warning(f"Error for {url}: {e}")
            return (url, True)

    async def healthcheck_async(args):
        with Session(engine) as db_sess:
            async with aiohttp.ClientSession() as http_sess:
                resources = (
                    db_sess.query(Resources).filter(Resources.accepted == True).all()
                )
                tasks = [get_up(http_sess, resource.url) for resource in resources]

                for coro in asyncio.as_completed(tasks):
                    try:
                        url, up = await coro
                        if not up:
                            logger.warning(f"{url} is not up.")

                            # post is not up, mark as rejected for further investigation
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
        "healthcheck", help="Perform healthchecking on db posts"
    )
    healthcheck.add_argument(
        "-m",
        "--mark-as-rejected",
        action="store_true",
        help="Mark matched posts as rejected.",
    )
    healthcheck.add_argument(
        "--disable-ssl-verification",
        help="Disable SSL Certificate validation (fix bug).",
        action="store_true",
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
