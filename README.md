# Mythcommflagwrapper

A Python wrapper for [Comskip](https://github.com/erikkaashoek/Comskip) that integrates with MythTV's commercial flagging system. It identifies commercial segments in recordings and updates the MythTV database accordingly.

This project follows modern Python packaging practices and provides both CLI and programmatic interfaces.

The aim of this project is to offer a easy way to use [Comskip](https://github.com/erikkaashoek/Comskip). This needs to be built and installed first.

This is very much work in progress - which explains:

- [X] the lack of a proper releases
- [X] the lack of a CI/CD system

[![PyPI - Version](https://img.shields.io/pypi/v/mythcommflagwrapper.svg)](https://pypi.org/project/mythcommflagwrapper)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mythcommflagwrapper.svg)](https://pypi.org/project/mythcommflagwrapper)

-----

## Table of Contents

- [Mythcommflagwrapper](#mythcommflagwrapper)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Development](#development)
  - [License](#license)

## Installation

### Native Python

```console
poetry build
```

### Ubuntu Packages

#### Simple

```
debuild -g
apt install ./python3-mythcommflagwrapper_0.1.1-1ubuntu4_amd64.deb
```

#### I have a lot of time

Or if you have `pdebuild` and `pbuilder` setup, your gpg keys as well as `dput`, `mini-dinstall` and `/etc/apt/sources.list.d/mythcommflagwrapper.list` pointing somewhere locally, it's a breeze:

```
pdebuild
dput ../python3-mythcommflagwrapper*changes
sudo apt update
sudo apt install -y python3-mythcommflagwrapper
```

Information seems to be rather scattered with best practices - so here are some pointers:

* [New requirements for APT repository signing in 24.04](https://discourse.ubuntu.com/t/new-requirements-for-apt-repository-signing-in-24-04/42854)
* [LocalAptGetRepository](https://help.ubuntu.com/community/LocalAptGetRepository)
* [Creating and hosting your own .deb packages and apt repository](https://earthly.dev/blog/creating-and-hosting-your-own-deb-packages-and-apt-repo/)
* [In output from apt update, what do inrelease and release refer to?](https://unix.stackexchange.com/questions/498033/in-output-from-apt-update-what-do-inrelease-and-release-refer-to)

## Usage

Use:

`/usr/bin/mythcommflag-wrapper --jobid "%JOBID%"`

as the Commercial Detection Command on the "General Backend Settings -> Job Queue (Global)"
page in the MythTV Setup web (port 6544)

## Development

### Setup Development Environment

```console
# Clone the repository
git clone https://github.com/charrus/mythcommflag.git
cd mythcommflag

# Set up development environment using Poetry
poetry install
```

### Running Tests

```console
poetry run pytest
```

### Code Style

This project uses ruff for linting and formatting. Run:

```console
poetry run ruff check .
poetry run ruff format .
```

### Type Checking

```console
poetry run mypy src/
```

## License

`mythcommflagwrapper` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
