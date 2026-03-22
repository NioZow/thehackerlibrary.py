from datetime import datetime
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from lxml import html
from newspaper import Article
from sqlalchemy.orm import Session, make_transient

from thehackerlibrary.config import (
    BLACKLIST_AUTHORS,
    BLACKLIST_PATHS,
    RULES_AUTHOR_BY_DOMAIN,
    RULES_AUTHOR_BY_XPATH,
    WHITELIST_AUTHORS,
    WHITELIST_PATHS,
    engine,
)
from thehackerlibrary.logger import logger
from thehackerlibrary.model import Authors, Resources, Sections, Tags, Topics


# Query parameters that are meaningful identifiers (not tracking noise) per netloc.
# All other params are stripped; only listed params are kept.
_PRESERVE_PARAMS: dict[str, set[str]] = {
    "www.youtube.com": {"v"},
    "youtube.com": {"v"},
}


def normalize_url(url: str) -> str:
    """Strip tracking query parameters and fragment from a URL.

    For domains in _PRESERVE_PARAMS, only the listed parameters are kept.
    For all other domains, the entire query string is removed.
    """
    parsed = urlparse(url)
    preserve = _PRESERVE_PARAMS.get(parsed.netloc)
    if preserve:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k in preserve}
        new_query = urlencode(filtered, doseq=True)
        return parsed._replace(query=new_query, fragment="").geturl()
    return parsed._replace(query="", fragment="").geturl()


def get_author_from_xpath(html_content: str, domain: str) -> Optional[str]:
    for data in RULES_AUTHOR_BY_XPATH:
        if domain == data["domain"]:
            tree = html.fromstring(html_content)
            elements = tree.xpath(data["xpath"])
            if elements:
                return elements[0].text_content().strip()
    return None


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


def check_whitelist(url: str, authors: List[str]) -> Optional[bool]:
    """Check the whitelisted/blacklisted state of a resource

    Args:
        url: Url of the resource
        authors: Authors of the resource

    Returns:
        Whether the resource should be accepted.
        So True means it is whitelisted, False means it is blacklisted and None means it is not know.
    """
    for blacklisted_path in BLACKLIST_PATHS:
        if url.startswith(blacklisted_path):
            return False
    for whitelisted_path in WHITELIST_PATHS:
        if url.startswith(whitelisted_path):
            if len(authors) == 0:
                logger.error(
                    f"Resource {url} would have been accepted if it had authors."
                )
                return None
            return True

    # Author-based rules
    if any(author in WHITELIST_AUTHORS for author in authors):
        return True
    elif any(author in BLACKLIST_AUTHORS for author in authors):
        return False
    else:
        return None


def get_author_from_domain(domain: str) -> Optional[str]:
    for data in RULES_AUTHOR_BY_DOMAIN:
        if domain == data["domain"]:
            return data["author"]
    return None


def update_accepted_resources(
    dry_run: bool = False, use_xpath_for_authors: bool = True
) -> int:
    """
    Queries posts that have not yet been accepted (those whose accepted property is None)
    and runs the whitelist/blacklist on them to change their accepted state.

    Args:
        dry_run: If True, changes will be logged but not committed to the database.

    Returns:
        The number of resources whose accepted state was updated.
    """
    changes_count = 0
    # domains = set()
    with Session(engine) as sess:
        # Query for resources where 'accepted' is None
        unaccepted_resources = (
            sess.query(Resources).filter(Resources.accepted == None).all()
        )

        for resource in unaccepted_resources:
            authors = [author.name for author in resource.authors]

            # update authors based on domains
            domain = urlparse(resource.url).netloc
            # domains.add(domain)

            # Attempt to get authors from domain-based rules first
            if len(authors) == 0:
                if author_name := get_author_from_domain(domain):
                    # Check if author already exists in the database, create if not
                    author_obj = sess.query(Authors).filter_by(name=author_name).first()
                    if not author_obj:
                        author_obj = Authors(name=author_name)
                        sess.add(author_obj)
                        logger.info(f"Created new author: {author_name}.")

                    # Link author to the resource
                    resource.authors.append(author_obj)
                    logger.info(
                        f"Added author {author_name} to {resource.url} via domain rule."
                    )
                    authors = [author_name]  # Update authors list for whitelist check

                # If no author found yet and XPath extraction is enabled, try XPath rules
                elif use_xpath_for_authors:
                    # Check if the domain is configured for XPath author extraction
                    is_xpath_configured = any(
                        rule["domain"] == domain for rule in RULES_AUTHOR_BY_XPATH
                    )

                    if is_xpath_configured:
                        # If enabled and domain is configured, attempt to download and parse the article
                        article = Article(resource.url)
                        try:
                            article.download()
                            article.parse()
                            if author_name := get_author_from_xpath(
                                article.html, domain
                            ):
                                # Check if author already exists in the database, create if not
                                author_obj = (
                                    sess.query(Authors)
                                    .filter_by(name=author_name)
                                    .first()
                                )
                                if not author_obj:
                                    author_obj = Authors(name=author_name)
                                    sess.add(author_obj)
                                    logger.info(
                                        f"Created new author via XPath: {author_name}."
                                    )
                                # Link author to the resource
                                resource.authors.append(author_obj)
                                logger.info(
                                    f"Added author {author_name} to {resource.url} via XPath."
                                )
                                authors = [
                                    author_name
                                ]  # Update authors list for whitelist check
                        except Exception as e:
                            logger.warning(
                                f"Failed to download or parse article {resource.url} for XPath author extraction: {e}"
                            )

            new_accepted_state = check_whitelist(resource.url, authors)

            # update accepted state
            if resource.accepted != new_accepted_state:
                logger.info(
                    f"Resource '{resource.title}' by {', '.join([author.name for author in resource.authors])} published at {resource.url} changed state to: {new_accepted_state}."
                )
                resource.accepted = new_accepted_state
                changes_count += 1

        if not dry_run:
            sess.commit()
            logger.info(f"Committed {changes_count} changes to the database.")
        else:
            sess.rollback()
            logger.info(f"Dry run: {changes_count} changes would have been committed.")

        # print(domains)

    return changes_count


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

    url = normalize_url(url)

    with Session(engine) as sess:
        resource = sess.query(Resources).filter_by(url=url).first()
        exists = bool(resource)

        if not resource:
            # download the article
            article = Article(url)
            article.download()
            article.parse()

            domain = urlparse(url).netloc

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
                if author_from_domain := get_author_from_domain(domain):
                    authors = [author_from_domain]
                elif author_from_xpath := get_author_from_xpath(article.html, domain):
                    authors = [author_from_xpath]
                    logger.info(
                        f"Author found for {url} using XPath: {author_from_xpath}."
                    )
                else:
                    # only the first author is usually right
                    authors = [article.authors[0]] if len(article.authors) > 0 else []

            # automatically set as accepted if author or domain is whitelisted
            if accepted is None:
                accepted = check_whitelist(url, authors)

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
        else:
            logger.warning(
                f"Resource '{resource.title}' ({resource.id}) already existed."
            )

        # Eagerly load all attributes before detaching from session
        # Access them to ensure they're loaded into the object's __dict__
        _ = resource.id, resource.title, resource.url, resource.date, resource.accepted
        make_transient(resource)

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


def remove_url_duplicates() -> int:
    """
    Find resources that share the same URL after stripping query parameters,
    keep the best one (accepted > pending > denied; earliest date as tiebreaker),
    merging tags/authors from duplicates, and delete the rest.
    Returns the number of resources deleted.
    """
    from collections import defaultdict

    from sqlalchemy.orm import joinedload

    with Session(engine) as sess:
        # Eagerly load relationships to avoid autoflush during lazy access
        all_resources = (
            sess.query(Resources)
            .options(joinedload(Resources.authors), joinedload(Resources.tags))
            .all()
        )

        groups: dict[str, list] = defaultdict(list)
        for resource in all_resources:
            groups[normalize_url(resource.url)].append(resource)

        deleted_count = 0
        accepted_order = {True: 0, None: 1, False: 2}
        # Collect (resource, new_url) pairs — applied after deletes are flushed
        url_updates: list[tuple] = []

        for normalized_url, group in groups.items():
            if len(group) <= 1:
                r = group[0]
                if r.url != normalized_url:
                    url_updates.append((r, normalized_url))
                continue

            group.sort(
                key=lambda r: (
                    accepted_order.get(r.accepted, 1),
                    r.date or datetime.max,
                )
            )

            keeper = group[0]

            for dup in group[1:]:
                for author in dup.authors:
                    if author not in keeper.authors:
                        keeper.authors.append(author)
                for tag in dup.tags:
                    if tag not in keeper.tags:
                        keeper.tags.append(tag)
                logger.info(
                    f"Removing duplicate '{dup.title}' ({dup.url}) — keeping '{normalized_url}'."
                )
                sess.delete(dup)
                deleted_count += 1

            if keeper.url != normalized_url:
                url_updates.append((keeper, normalized_url))

        # Flush deletes before applying URL updates to avoid unique constraint
        # violations (the duplicate holding the clean URL must be gone first).
        sess.flush()

        for resource, new_url in url_updates:
            resource.url = new_url

        sess.commit()
        return deleted_count


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
