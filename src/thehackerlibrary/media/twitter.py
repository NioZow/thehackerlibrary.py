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
    X_LAST_BOOKMARK_ID,
    X_REDIRECT_URI,
    config,
    write_config,
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

        if id:
            self.user_id = id
        else:
            body = requests.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": "Bearer {}".format(self.token)},
            ).json()

            if data := body.get("data"):
                self.user_id = data["id"]
            else:
                print(f"failed to get data from body: {body}")
                raise Exception

        if not id:
            logger.info(
                f"Your twitter id is {self.user_id} please save in the configuration file."
            )
            config["twitter"]["id"] = self.user_id
            write_config(config)

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

        response = oauth.fetch_token(
            token_url="https://api.twitter.com/2/oauth2/token",
            authorization_response=authorization_response,
            auth=HTTPBasicAuth(X_CLIENT_ID, X_CLIENT_SECRET),
            client_id=X_CLIENT_ID,
            include_client_id=True,
            code_verifier=code_verifier,
        )

        print(
            f"Your access token is {response.get('access_token')} you can save it in the .env as 'token'."
        )
        print(
            f"Your refresh token is {response.get('refresh_token')} you can save it in the .env as 'refresh_token'."
        )
        config["twitter"]["access_token"] = response.get("access_token")
        config["twitter"]["refresh_token"] = response.get("refresh_token")
        write_config(config)

        return cls(response["access_token"])

    @classmethod
    def from_refresh_token(cls, refresh_token: str, user_id: Optional[str] = None):
        """Get new access token using refresh token"""
        response = requests.post(
            "https://api.twitter.com/2/oauth2/token",
            auth=HTTPBasicAuth(X_CLIENT_ID, X_CLIENT_SECRET),
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

        if response.status_code != 200:
            raise Exception(f"Token refresh failed: {response.text}")

        data = response.json()
        print(f"New access token: {data['access_token']}")
        print(f"New refresh token: {data['refresh_token']}")
        config["twitter"]["access_token"] = data["access_token"]
        config["twitter"]["refresh_token"] = data["refresh_token"]
        write_config(config)

        return cls(data["access_token"])

    async def get_posts_from_bookmarks(self) -> List[Resources]:
        """Scrape bookmarks and return posts from those.

        Fetches only bookmarks newer than the last run by comparing Snowflake tweet IDs.
        Paginates with small pages and stops early once we reach already-seen tweets,
        minimising billed resources.
        """
        last_bookmark_id = int(X_LAST_BOOKMARK_ID) if X_LAST_BOOKMARK_ID else None
        newest_id_seen: Optional[int] = None

        all_tweets = []
        pagination_token = None
        done = False

        while not done:
            params: dict = {"max_results": 10, "tweet.fields": "created_at"}
            if pagination_token:
                params["pagination_token"] = pagination_token

            res = requests.get(
                f"https://api.twitter.com/2/users/{self.user_id}/bookmarks",
                headers={"Authorization": f"Bearer {self.token}"},
                params=params,
            )

            if res.status_code != 200:
                raise Exception(
                    f"Request returned an error: {res.status_code} {res.text}"
                )

            data = res.json()
            tweets = data.get("data", [])

            for tweet in tweets:
                tweet_id = int(tweet["id"])

                if newest_id_seen is None:
                    newest_id_seen = tweet_id

                # Bookmarks are newest-first; stop once we reach already-processed tweets
                if last_bookmark_id and tweet_id <= last_bookmark_id:
                    done = True
                    break

                all_tweets.append(tweet)

            next_token = data.get("meta", {}).get("next_token")
            if not next_token:
                done = True
            else:
                pagination_token = next_token

        if not all_tweets:
            logger.info("No new bookmarks since last run.")
            return []

        logger.info(f"Fetched {len(all_tweets)} new bookmark(s) from the API.")

        post_urls = [
            url
            for tweet in all_tweets
            for url in re.findall(r"https?://t\.co/[a-zA-Z0-9]+", tweet["text"])
        ]

        resources = []

        async with aiohttp.ClientSession() as http_sess:
            tasks = [resolve_url(http_sess, url) for url in post_urls]
            for coro in asyncio.as_completed(tasks):
                try:
                    url = await coro
                    if "/photo/" not in url:
                        resource, exists = add_resource(url, type="Post")
                        if not exists:
                            resources.append(resource)
                            logger.info(f"Added Resource '{resource.title}'")
                        else:
                            logger.warning(
                                f"Resource '{resource.title}' ({resource.id}) already existed."
                            )
                except Exception as e:
                    logger.error(f"Resource error: {e}")

        # Persist the newest seen ID so the next run starts from here
        if newest_id_seen:
            config["twitter"]["last_bookmark_id"] = str(newest_id_seen)
            write_config(config)

        return resources
