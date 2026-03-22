from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Dict, List

import yaml
from sqlalchemy.orm import Session
from sqlalchemy_utils import create_database, database_exists

from thehackerlibrary.config import engine
from thehackerlibrary.logger import logger
from thehackerlibrary.model import (
    Authors,
    Base,
    Paths,
    Resources,
    Sections,
    Tags,
    Topics,
)


def import_wrapper(table: str):
    """Decorator factory to easily import data from yaml files"""

    def decorator(func):
        @wraps(func)
        def wrapper(self, data: List[Dict] = []):
            if len(data) == 0:
                with open(self.outdir / f"{table}.yml", "r") as f:
                    data = yaml.safe_load(f) or []
            return func(self, data)

        return wrapper

    return decorator


class Importer:
    def __init__(self, outdir: Path):
        self.outdir = outdir

    def import_all(self):
        # create the db
        if not database_exists(engine.url):
            create_database(engine.url)

        # create tables
        Base.metadata.create_all(engine)

        self.import_authors()
        self.import_tags()
        self.import_accepted_resources()
        self.import_paths()
        self.import_topics()
        self.import_sections()

        for method, filename in [
            (self.import_rejected_resources, "resources_rejected.yml"),
            (self.import_pending_resources, "resources_pending.yml"),
        ]:
            try:
                method()
            except FileNotFoundError:
                logger.warning(f"{filename} not found, skipping.")
            except Exception:
                raise

    @import_wrapper("authors")
    def import_authors(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for author_data in data:
                existing = sess.query(Authors).filter_by(id=author_data["id"]).first()
                if existing:
                    existing.name = author_data["name"]
                else:
                    sess.add(Authors(id=author_data["id"], name=author_data["name"]))

            sess.commit()

    @import_wrapper("tags")
    def import_tags(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for tag_data in data:
                existing = sess.query(Tags).filter_by(id=tag_data["id"]).first()
                if existing:
                    existing.name = tag_data["name"]
                else:
                    sess.add(Tags(id=tag_data["id"], name=tag_data["name"]))

            sess.commit()

    def _import_resources(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for resource_data in data:
                # Look up by URL first (unique), then fall back to ID.
                # This handles mismatches where the YAML and DB diverged on
                # either key independently.
                existing = (
                    sess.query(Resources).filter_by(url=resource_data["url"]).first()
                    or sess.query(Resources).filter_by(id=resource_data["id"]).first()
                )

                date = (
                    datetime.strptime(resource_data["date"], "%Y-%m-%d")
                    if resource_data.get("date")
                    else None
                )

                if existing:
                    existing.type = resource_data["type"]
                    existing.title = resource_data["title"]
                    existing.url = resource_data["url"]
                    existing.date = date
                    existing.accepted = resource_data["accepted"]
                    existing.time = resource_data["time"]
                    resource = existing
                else:
                    resource = Resources(
                        id=resource_data["id"],
                        type=resource_data["type"],
                        title=resource_data["title"],
                        url=resource_data["url"],
                        date=date,
                        accepted=resource_data["accepted"],
                        time=resource_data["time"],
                    )
                    sess.add(resource)

                sess.flush()

                # sync authors
                new_authors = [
                    sess.query(Authors).filter_by(id=aid).first()
                    for aid in resource_data.get("authors", [])
                ]
                resource.authors = [a for a in new_authors if a is not None]

                # sync tags
                new_tags = [
                    sess.query(Tags).filter_by(id=tid).first()
                    for tid in resource_data.get("tags", [])
                ]
                resource.tags = [t for t in new_tags if t is not None]

            sess.commit()

    @import_wrapper("resources")
    def import_accepted_resources(self, data: List[Dict] = []):
        return self._import_resources(data)

    @import_wrapper("resources_pending")
    def import_pending_resources(self, data: List[Dict] = []):
        return self._import_resources(data)

    @import_wrapper("resources_rejected")
    def import_rejected_resources(self, data: List[Dict] = []):
        return self._import_resources(data)

    @import_wrapper("paths")
    def import_paths(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for path_data in data:
                existing = sess.query(Paths).filter_by(id=path_data["id"]).first()
                if existing:
                    existing.name = path_data["name"]
                else:
                    sess.add(Paths(id=path_data["id"], name=path_data["name"]))

            sess.commit()

    @import_wrapper("topics")
    def import_topics(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for topic_data in data:
                existing = sess.query(Topics).filter_by(id=topic_data["id"]).first()
                if existing:
                    existing.tag_id = topic_data["tag_id"]
                    existing.path_id = topic_data["path_id"]
                else:
                    sess.add(Topics(
                        id=topic_data["id"],
                        tag_id=topic_data["tag_id"],
                        path_id=topic_data["path_id"],
                    ))
            sess.commit()

    @import_wrapper("sections")
    def import_sections(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for section_data in data:
                existing = sess.query(Sections).filter_by(id=section_data["id"]).first()
                if existing:
                    existing.tag_id = section_data["tag_id"]
                    existing.topic_id = section_data["topic_id"]
                    existing.priority = section_data["priority"]
                else:
                    sess.add(Sections(
                        id=section_data["id"],
                        tag_id=section_data["tag_id"],
                        topic_id=section_data["topic_id"],
                        priority=section_data["priority"],
                    ))
            sess.commit()
