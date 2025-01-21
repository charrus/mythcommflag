# Mythcommflagwrapper

A simple library with CLI interface for exerimenting with python, current
packaging best practices.

The aim of this project is to offer a easy way to use [Comskip](https://github.com/erikkaashoek/Comskip). This needs to be built and installed first.

This is very much work in progress.

[![PyPI - Version](https://img.shields.io/pypi/v/mythcommflagwrapper.svg)](https://pypi.org/project/mythcommflagwrapper)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mythcommflagwrapper.svg)](https://pypi.org/project/mythcommflagwrapper)

-----

## Table of Contents

- [Mythcommflagwrapper](#mythcommflagwrapper)
  - [Table of Contents](#table-of-contents)
  - [Installation](#installation)
  - [License](#license)

## Installation

### Python

```console
pip install mythcommflagwrapper
```

### Ubuntu

```
debuild -i -b -us -uc
apt install ./python3-mythcommflagwrapper_0.1.1-1ubuntu4_amd64.deb

## Usage

Use:

`/usr/bin/mythcommflag-wrapper --jobid "%JOBID%"`

as the Commercial Detection Command on the "General Backend Settings -> Job Queue (Global)"
page in the MythTV Setup web (port 6544)

## License

`mythcommflagwrapper` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
