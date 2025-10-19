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
X_TOKEN = config.get("twitter", {}).get("token")
X_ID = config.get("twitter", {}).get("id")
