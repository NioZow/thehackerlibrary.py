"""
Scrape youtube description videos for links to blog post
cc @criticalthinkingpodcast
"""

import re
from typing import Any, Dict

import requests
from sqlalchemy.orm import Session

from thehackerlibrary.config import YOUTUBE_API_KEY, engine
from thehackerlibrary.logger import logger
from thehackerlibrary.resources import add_resource


def youtube_api_request(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    assert YOUTUBE_API_KEY != "", "Missing YOUTUBE_API_KEY env variable"
    params["key"] = YOUTUBE_API_KEY
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_posts_from_playlist(playlist_id: str):
    next_page_token = None
    resources = []

    url_regex = re.compile(r"(https?://\S+)")

    # list of domains to blacklist
    # Had to add a lot just to narrow down the results
    # Otherwise I have easily 500+ posts to check
    # Some might have lost some good read, well I accept it ^^
    blacklist_domains = [
        "ctbb.show",
        "nux.gg",
        "github.com",
        "criticalthinkingpodcast.io",
        "yeswehack.com",
        "portswigger-labs.net",
        "linkedin.com",
        "docs.google.com",
        "twitter.com",
        "x.com",
        "openai.com",
        "gumroad.com",
        "hackerone.com",
        "infosec.exchange",
        "nvd.nist.gov",
        "discord.com",
        "amazon.com",
        "pypi.org",
        "vercel.com",
        "tinyurl.com",
        "leanpub.com",
        "amzn.to",
        "bettercap.org",
        "symless.com",
        "bit.ly",
        "rss.com",
        "hacktricks.xyz",
        "nostarch.com",
        "youtube.com",  # too many results sry i prefer reading
    ]

    # Compile blacklist patterns
    blacklist_regex = [
        re.compile(
            r"https?://.*(?:"
            + "|".join([domain.replace(".", "\\.") for domain in blacklist_domains])
            + r")"
        ),
        re.compile(r"https?://[^/]+/?$"),
    ]

    with Session(engine) as sess:
        # get the videos of a playlists
        while True:
            # request the api
            params = {
                "part": "snippet,contentDetails,id",
                "playlistId": playlist_id,
                "maxResults": 50,
            }

            if next_page_token:
                params["pageToken"] = next_page_token

            data = youtube_api_request(
                "https://www.googleapis.com/youtube/v3/playlistItems", params=params
            )

            # iter through all videos of the playlist
            for item in data["items"]:
                vid_title = item["snippet"]["title"]

                # check the video is available
                if vid_title not in ("Private video", "Deleted video"):
                    description = item["snippet"]["description"]

                    # get all URLs from the description and blacklist some domains to narrow down the results
                    # otherwise there are too many
                    # filter out blacklisted URLs
                    urls = [
                        url
                        for url in url_regex.findall(description)
                        if not any(
                            blacklist.search(url) for blacklist in blacklist_regex
                        )
                    ]

                    for url in urls:
                        try:
                            resource, exists = add_resource(url, type="Post")
                            if not exists:
                                resources.append(resource)
                        except Exception as e:
                            logger.error(f"Failed to parse {url}: {e}")

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

    return resources
