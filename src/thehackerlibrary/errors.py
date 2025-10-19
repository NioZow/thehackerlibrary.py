class TheHackerLibraryError(Exception):
    pass


class InvalidRssFeed(TheHackerLibraryError):
    pass


class InvalidUrl(TheHackerLibraryError):
    pass


class PostInaccesible(TheHackerLibraryError):
    pass
