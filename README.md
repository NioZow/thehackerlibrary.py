# TheHackerLibrary.py

SDK for [TheHackerLibrary](https://github.com/niozow/thehackerlibrary).

Although this repository is public, it is not stable and contains bugs.

## Installation

```sh
git clone git@github.com:niozow/thehackerlibrary.py.git
cd emp
uv tool install .
```

Then normally you should have the script installed at `~/.local/bin/thehackerlibrary` :

```sh
$ thehackerlibrary
usage: thehackerlibrary [-h] {clean,healthcheck,role,import,export,scrape} ...
thehackerlibrary: error: the following arguments are required: action
```

### Uninstall

Simply run the following :

```sh
uv tool uninstall thehackerlibrary
```

### Development

```sh
uv venv
uv pip install -e .
uv run -m thehackerlibrary -h
```
