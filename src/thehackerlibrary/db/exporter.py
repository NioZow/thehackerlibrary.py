import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Optional, cast

import yaml
from sqlalchemy.orm import Session

from thehackerlibrary.config import engine
from thehackerlibrary.model import Authors, Paths, Resources, Sections, Tags, Topics


def export_wrapper(table: str):
    """Decorator factory to easily import data from yaml files"""

    def decorator(func):
        @wraps(func)
        def wrapper(self):
            # execute the function and get its output
            data = func(self)
            with open(self.outdir / f"{table}.yml", "w") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

            return data

        return wrapper

    return decorator


class Exporter:
    def __init__(self, outdir: Path):
        self.outdir = outdir

    def export_all(self):
        # create the directory if it does not exist
        if not self.outdir.is_dir():
            os.makedirs(str(self.outdir), exist_ok=True)

        self.export_authors()
        self.export_tags()
        self.export_pending_resources()
        self.export_accepted_resources()
        self.export_rejected_resources()
        self.export_paths()
        self.export_topics()
        self.export_sections()

    @export_wrapper("authors")
    def export_authors(self):
        with Session(engine) as sess:
            return sorted(
                [
                    {"name": author.name, "id": author.id}
                    for author in sess.query(Authors).all()
                ],
                key=lambda a: a["name"],
            )

    @export_wrapper("tags")
    def export_tags(self):
        with Session(engine) as sess:
            return sorted(
                [{"name": tag.name, "id": tag.id} for tag in sess.query(Tags).all()],
                key=lambda a: a["name"],
            )

    def _export_resources(self, accepted: Optional[bool] = True):
        with Session(engine) as sess:
            return sorted(
                [
                    {
                        "id": resource.id,
                        "type": resource.type,
                        "title": resource.title,
                        "url": resource.url,
                        "time": resource.time,
                        "accepted": resource.accepted,
                        "authors": [author.id for author in resource.authors],
                        "tags": [tag.id for tag in resource.tags],
                        "date": resource.date.strftime("%Y-%m-%d")
                        if isinstance(resource.date, datetime)
                        else datetime.fromtimestamp(resource.date / 1000).strftime(
                            "%Y-%m-%d"
                        )
                        if isinstance(resource.date, (int, float))
                        else None,
                    }
                    for resource in sess.query(Resources)
                    .filter(Resources.accepted == accepted)
                    .all()
                ],
                key=lambda a: cast(int, a["title"]),
            )

    @export_wrapper("resources")
    def export_accepted_resources(self):
        return self._export_resources(accepted=True)

    @export_wrapper("resources_rejected")
    def export_rejected_resources(self):
        return self._export_resources(accepted=False)

    @export_wrapper("resources_pending")
    def export_pending_resources(self):
        return self._export_resources(accepted=None)

    @export_wrapper("paths")
    def export_paths(self):
        with Session(engine) as sess:
            return sorted(
                [
                    {"name": path.name, "id": path.id}
                    for path in sess.query(Paths).all()
                ],
                key=lambda a: a["name"],
            )

    @export_wrapper("topics")
    def export_topics(self):
        with Session(engine) as sess:
            return sorted(
                [
                    {"tag_id": topic.tag_id, "id": topic.id, "path_id": topic.path_id}
                    for topic in sess.query(Topics).all()
                ],
                key=lambda a: a["id"],
            )

    @export_wrapper("sections")
    def export_sections(self):
        with Session(engine) as sess:
            return sorted(
                [
                    {
                        "tag_id": section.tag_id,
                        "id": section.id,
                        "topic_id": section.topic_id,
                        "priority": section.priority,
                    }
                    for section in sess.query(Sections).all()
                ],
                key=lambda a: a["id"],
            )
