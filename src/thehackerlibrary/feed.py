import re
import xml.etree.ElementTree as ET
from typing import List

import requests
from sqlalchemy.orm import Session

from thehackerlibrary.config import engine
from thehackerlibrary.errors import InvalidRssFeed
from thehackerlibrary.model import Resources
from thehackerlibrary.resources import add_resource, parse_pubdate


class InvalidFeedPost(Exception):
    pass


class Feed:
    def __init__(self, url: str):
        self.url = url
        self.feed = self._get_feed()
        self.namespace = self._get_namespace()
        self.ns = {"atom": self.namespace} if self.namespace else None

    def _get_feed(self):
        """Get a feed"""
        res = requests.get(self.url)
        if res.status_code != 200:
            raise InvalidRssFeed

        return ET.fromstring(res.text)

    def _get_namespace(self):
        """Extract namespace from the root tag"""
        match = re.match(r"\{(.+?)\}", self.feed.tag)
        return match.group(1) if match else None

    def get_posts(self) -> List[Resources]:
        resources = []

        entries = (
            self.feed.findall("atom:entry", self.ns)
            if self.namespace
            else self.feed.findall("entry")
        )

        with Session(engine) as sess:
            for entry in entries:
                title = entry.find("atom:title", self.ns).text
                date = parse_pubdate(entry.find("atom:published", self.ns).text)
                url = entry.find("atom:id", self.ns).text

                authors = [
                    name.text
                    for author in entry.findall("atom:author", self.ns)
                    if (name := author.find("atom:name", self.ns)) is not None
                    and name.text
                ]

                if not url:
                    raise InvalidFeedPost("Post does not have a URL.")

                if not title:
                    raise InvalidFeedPost("Post does not have a title.")

                resource, exists = add_resource(
                    url, "Post", title, date, authors if len(authors) > 0 else None
                )
                if not exists:
                    resources.append(resource)

        return resources


class RssFeed(Feed):
    def get_posts(self) -> List[Resources]:
        resources = []

        with Session(engine) as sess:
            for item in self.feed.findall(".//item"):
                title = item.find("title").text
                url = item.find("link").text
                date = parse_pubdate(item.find("pubDate").text).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

                if not url:
                    raise InvalidFeedPost("Post does not have a URL.")

                if not title:
                    raise InvalidFeedPost("Post does not have a title.")

                resource, exists = add_resource(url, "Post", title, date)
                if not exists:
                    resources.append(resource)

        return resources
