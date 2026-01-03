from pathlib import Path

import yaml
from sqlalchemy import create_engine

from thehackerlibrary.logger import logger

DATA_DIRECTORY = Path("~/.local/share/thehackerlibrary/").expanduser()
LOG_FILE = DATA_DIRECTORY / "thehackerlibrary.log"
CONFIG_DIRECTORY = Path("~/.config/thehackerlibrary").expanduser()
CONFIG_PATH = CONFIG_DIRECTORY / "config.yml"

try:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
except FileNotFoundError as e:
    logger.fatal_error(f"File {CONFIG_PATH} does not exist: {e}.")
except yaml.YAMLError as e:
    logger.fatal_error(f"Failed to parse config of {CONFIG_PATH}: {e}.")

engine = create_engine(f"{config['database_url']}")

RSS_FEEDS = config["rss"]
FEEDS = config["feeds"]

REVIEW_PATH = DATA_DIRECTORY / "review.yml"

YOUTUBE_API_KEY = config["youtube"]["api_key"]
YOUTUBE_PLAYLISTS = config["youtube"]["playlists"]

X_CLIENT_ID = config.get("twitter", {}).get("client_id")
X_CLIENT_SECRET = config.get("twitter", {}).get("client_secret")
X_REDIRECT_URI = config.get("twitter", {}).get("redirect_uri")
X_ACCESS_TOKEN = config.get("twitter", {}).get("access_token")
X_REFRESH_TOKEN = config.get("twitter", {}).get("refresh_token")
X_ID = config.get("twitter", {}).get("id")

WHITELIST_AUTHORS = config.get("whitelist", {}).get("authors", [])
BLACKLIST_AUTHORS = config.get("blacklist", {}).get("authors", [])
WHITELIST_PATHS = config.get("whitelist", {}).get("paths", [])
BLACKLIST_PATHS = config.get("blacklist", {}).get("paths", [])

RULES_AUTHOR_BY_DOMAIN = config.get("rules", {}).get("author_by_domain", [])
RULES_AUTHOR_BY_XPATH = config.get("rules", {}).get("author_by_xpath", [])


def write_config(conf):
    with open(CONFIG_PATH, "w") as f:
        f.write(yaml.safe_dump(conf))
