from datetime import datetime
from typing import List, Optional

from newspaper import Article
from sqlalchemy.orm import Session

from thehackerlibrary.config import engine
from thehackerlibrary.model import Authors, Resources, Sections, Tags, Topics


def parse_pubdate(date_str):
    formats = [
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: {date_str}")


def add_resource(
    url: str,
    type: str,
    title: Optional[str] = None,
    date: Optional[datetime] = None,
    authors: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    accepted: Optional[bool] = None,
) -> tuple[Resources, bool]:
    """
    Add a post to the db for review.
    Returns the resource and a boolean telling wether the resource already existed in db (data will not be overwritten).
    """

    with Session(engine) as sess:
        resource = sess.query(Resources).filter_by(url=url).first()
        exists = bool(resource)

        if not resource:
            # download the article
            article = Article(url)
            article.download()
            article.parse()

            # get the title if not already specified
            if not title:
                title = article.title

            # get the date if not already specified
            if not date:
                if isinstance(article.publish_date, str):
                    date = parse_pubdate(article.publish_date)
                elif isinstance(article.publish_date, datetime):
                    date = article.publish_date

            # get the authors if not already specified
            if not authors:
                # only the first author is usually right
                authors = [article.authors[0]] if len(article.authors) > 0 else []

            resource = Resources(
                type=type,
                title=title,
                url=url,
                date=date,
                accepted=accepted,
            )

            sess.add(resource)

            for author_name in authors:
                author = sess.query(Authors).filter_by(name=author_name).first()
                if not author:
                    # create a new author if it does not exist
                    author = Authors(name=author_name)
                    sess.add(author)

                resource.authors.append(author)

            if tags:
                # add tags
                for tag_name in tags:
                    tag = sess.query(Tags).filter_by(name=tag_name).first()
                    if not tag:
                        # create new tag if it doesn't exist
                        tag = Tags(name=tag_name)
                        sess.add(tag)

                    resource.tags.append(tag)

            sess.commit()
            sess.expunge(resource)

        return resource, exists


def remove_orphaned_tags() -> int:
    """
    Remove all tags that are not linked to any resource.
    Returns the number of tags deleted.
    """
    with Session(engine) as sess:
        # Find tags with no resources
        orphaned_tags = sess.query(Tags).filter(~Tags.resources.any()).all()

        count = len(orphaned_tags)
        for tag in orphaned_tags:
            sess.delete(tag)

        sess.commit()
        return count


def remove_orphaned_authors() -> int:
    """
    Remove all authors that are not linked to any resource.
    Returns the number of authors deleted.
    """
    with Session(engine) as sess:
        # Find authors with no resources
        orphaned_authors = sess.query(Authors).filter(~Authors.resources.any()).all()

        count = len(orphaned_authors)
        for author in orphaned_authors:
            sess.delete(author)

        sess.commit()
        return count


def remove_orphaned_topics() -> int:
    """
    Remove all topics that have null tag_id or are not linked to any sections.
    Returns the number of topics deleted.
    """
    with Session(engine) as sess:
        # Find topics with null tag_id or no sections
        orphaned_topics = (
            sess.query(Topics)
            .filter((Topics.tag_id == None) | (~Topics.sections.any()))
            .all()
        )

        count = len(orphaned_topics)
        for topic in orphaned_topics:
            sess.delete(topic)

        sess.commit()
        return count


def remove_orphaned_sections() -> int:
    """
    Remove all sections that have null tag_id.
    Returns the number of sections deleted.
    """
    with Session(engine) as sess:
        # Find sections with null tag_id
        orphaned_sections = sess.query(Sections).filter(Sections.tag_id == None).all()

        count = len(orphaned_sections)
        for section in orphaned_sections:
            sess.delete(section)

        sess.commit()
        return count
