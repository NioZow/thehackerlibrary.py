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
                    data = yaml.safe_load(f)
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

        try:
            self.import_rejected_resources()
            self.import_pending_resources()
        except Exception as e:
            logger.warning(f"Failed to load some resources: {e}")

    @import_wrapper("authors")
    def import_authors(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for author_data in data:
                # check if author already exists
                existing = sess.query(Authors).filter_by(id=author_data["id"]).first()
                if not existing:
                    author = Authors(id=author_data["id"], name=author_data["name"])
                    sess.add(author)

            sess.commit()

    @import_wrapper("tags")
    def import_tags(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for tag_data in data:
                # check if tag already exists
                existing = sess.query(Tags).filter_by(id=tag_data["id"]).first()
                if not existing:
                    tag = Tags(id=tag_data["id"], name=tag_data["name"])
                    sess.add(tag)

            sess.commit()

    def _import_resources(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for resource_data in data:
                # check if resource already exists
                existing = (
                    sess.query(Resources).filter_by(id=resource_data["id"]).first()
                )

                # TODO: overwrite
                if not existing:
                    resource = Resources(
                        id=resource_data["id"],
                        type=resource_data["type"],
                        title=resource_data["title"],
                        url=resource_data["url"],
                        date=datetime.strptime(resource_data["date"], "%Y-%m-%d")
                        if resource_data.get("date")
                        else None,
                        accepted=resource_data["accepted"],
                        time=resource_data["time"],
                    )

                    sess.add(resource)

                    # flush to get the resource ID for relationships
                    sess.flush()

                    # add authors
                    for author_id in resource_data.get("authors", []):
                        author = sess.query(Authors).filter_by(id=author_id).first()
                        if author:
                            resource.authors.append(author)

                    # add tags
                    for tag_id in resource_data.get("tags", []):
                        tag = sess.query(Tags).filter_by(id=tag_id).first()
                        if tag:
                            resource.tags.append(tag)

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
                # check if path already exists
                existing = sess.query(Paths).filter_by(id=path_data["id"]).first()
                if not existing:
                    path = Paths(id=path_data["id"], name=path_data["name"])
                    sess.add(path)

            sess.commit()

    @import_wrapper("topics")
    def import_topics(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for topic_data in data:
                # check if topic already exists
                existing = sess.query(Topics).filter_by(id=topic_data["id"]).first()
                if not existing:
                    topic = Topics(
                        id=topic_data["id"],
                        tag_id=topic_data["tag_id"],
                        path_id=topic_data["path_id"],
                    )
                    sess.add(topic)
            sess.commit()

    @import_wrapper("sections")
    def import_sections(self, data: List[Dict] = []):
        with Session(engine) as sess:
            for section_data in data:
                # check if topic already exists
                existing = sess.query(Sections).filter_by(id=section_data["id"]).first()
                if not existing:
                    section = Sections(
                        id=section_data["id"],
                        tag_id=section_data["tag_id"],
                        topic_id=section_data["topic_id"],
                        priority=section_data["priority"],
                    )
                    sess.add(section)
            sess.commit()
