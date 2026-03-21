import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader
from newspaper import Article
from openai import OpenAI

from thehackerlibrary.config import LITELLM_API_KEY, LITELLM_BASE_URL, LITELLM_MODEL
from thehackerlibrary.logger import logger

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(_PROMPTS_DIR), autoescape=False)

_MAX_CONTENT_CHARS = 24_000


@dataclass
class AnalysisResult:
    tags: List[str] = field(default_factory=list)
    accepted: bool = True  # True = good quality, False = reject
    reason: str = ""
    fetch_failed: bool = False


def analyze(
    url: str,
    existing_tags: List[str],
    article_text: Optional[str] = None,
    article_title: Optional[str] = None,
) -> AnalysisResult:
    """Analyze a post: suggest tags and evaluate quality in a single LLM call.

    Args:
        url: URL of the article.
        existing_tags: All tag names currently in the database.
        article_text: Pre-fetched article body (skips download if provided).
        article_title: Pre-fetched article title (skips download if provided).

    Returns:
        AnalysisResult with tags, quality verdict, and reason.
        Sets fetch_failed=True if the article could not be downloaded.
        On LLM parse failure returns empty tags and accepted=True (fail open).
    """
    if article_text is None or article_title is None:
        article = Article(url)
        try:
            article.download()
            article.parse()
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return AnalysisResult(fetch_failed=True)
        article_title = article_title or article.title or url
        article_text = article_text or article.text or ""

    if not article_text:
        logger.warning(f"No text extracted for {url}, analysis may be inaccurate.")

    template = _jinja_env.get_template("analyze.md.j2")
    prompt = template.render(
        title=article_title,
        url=url,
        content=article_text[:_MAX_CONTENT_CHARS],
        existing_tags=sorted(existing_tags),
    )

    logger.info(f"Calling LLM to analyze: {article_title}")

    client = OpenAI(api_key=LITELLM_API_KEY, base_url=LITELLM_BASE_URL)
    response = client.chat.completions.create(
        model=LITELLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
        tags = [str(t).strip().lower() for t in data.get("tags", []) if str(t).strip()]
        accepted = bool(data.get("accepted", True))
        reason = str(data.get("reason", ""))
        return AnalysisResult(tags=tags, accepted=accepted, reason=reason)
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse LLM response for {url}: {e}\nRaw: {raw}")
        return AnalysisResult()
