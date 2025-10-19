import asyncio
import base64
import hashlib
import os
import re
from typing import List, Optional

import aiohttp
import requests
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session

from thehackerlibrary.config import (
    X_CLIENT_ID,
    X_CLIENT_SECRET,
    X_REDIRECT_URI,
)
from thehackerlibrary.logger import logger
from thehackerlibrary.model import Resources
from thehackerlibrary.resources import add_resource


async def resolve_url(session, url):
    async with session.get(url) as res:
        if res.status != 200:
            raise Exception(f"{url} returned status code: {res.status}")
        return str(res.url)


class Twitter:
    scopes = ["bookmark.read", "tweet.read", "users.read", "offline.access"]

    def __init__(self, token: str, id: Optional[str] = None):
        self.token = token
        self.user_id = (
            id
            or requests.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": "Bearer {}".format(self.token)},
            ).json()["data"]["id"]
        )

        if not id:
            logger.info(
                f"Your twitter id is {self.user_id} please save in the configuration file."
            )

    @classmethod
    def interactive_auth(cls):
        assert X_REDIRECT_URI is not None and X_REDIRECT_URI != "", (
            "Invalid X_REDIRECT_URI"
        )
        assert X_CLIENT_SECRET is not None and X_CLIENT_SECRET != "", (
            "Invalid X_CLIENT_SECRET"
        )
        assert X_CLIENT_ID is not None and X_CLIENT_ID != "", "Invalid X_CLIENT_ID"

        code_verifier = re.sub(
            "[^a-zA-Z0-9]+",
            "",
            base64.urlsafe_b64encode(os.urandom(30)).decode("utf-8"),
        )

        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("utf-8")).digest()
            )
            .decode("utf-8")
            .replace("=", "")
        )

        oauth = OAuth2Session(
            X_CLIENT_ID, redirect_uri=X_REDIRECT_URI, scope=cls.scopes
        )

        auth_url = "https://twitter.com/i/oauth2/authorize"
        authorization_url, state = oauth.authorization_url(
            auth_url, code_challenge=code_challenge, code_challenge_method="S256"
        )

        print("Visit the following URL:", authorization_url)

        authorization_response = input(
            "Paste in the full URL after you've authorized your App:\n"
        )

        token = oauth.fetch_token(
            token_url="https://api.twitter.com/2/oauth2/token",
            authorization_response=authorization_response,
            auth=HTTPBasicAuth(X_CLIENT_ID, X_CLIENT_SECRET),
            client_id=X_CLIENT_ID,
            include_client_id=True,
            code_verifier=code_verifier,
        )["access_token"]

        print(f"Your token is {token} you can save it in the .env as X_TOKEN.")
        return cls(token)

    async def get_posts_from_bookmarks(self) -> List[Resources]:
        """Scrape bookmarks and return posts from those"""
        res = requests.get(
            f"https://api.twitter.com/2/users/{self.user_id}/bookmarks",
            headers={"Authorization": f"Bearer {self.token}"},
        )

        if res.status_code != 200:
            raise Exception(f"Request returned an error: {res.status_code} {res.text}")

        data = res.json()

        # with open("data.json", "r") as f:
        #     import json
        #
        #     data = json.loads(f.read())

        resources = []

        post_urls = [
            url
            for tweet in data["data"]
            for url in re.findall(r"https?://t\.co/[a-zA-Z0-9]+", tweet["text"])
        ]

        async with aiohttp.ClientSession() as http_sess:
            tasks = [resolve_url(http_sess, url) for url in post_urls]
            for coro in asyncio.as_completed(tasks):
                try:
                    url = await coro
                    resource, exists = add_resource(url, type="Post")
                    if not exists:
                        resources.append(resource)

                except Exception as e:
                    logger.warning(f"Error: {e}")

        return resources
