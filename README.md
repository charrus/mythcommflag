# Mythcommflagwrapper

A simple library with CLI interface for exerimenting with python, current
packaging best practices.

The aim of this project is to offer a easy way to use [Comskip](https://github.com/erikkaashoek/Comskip). This needs to be built and installed first.

Just copy the comskip.ini and src/mythcommflag.py to /usr/local/bin and use:

`/usr/local/bin/mythcommflag-wrapper.py --jobid "%JOBID%"`

as the Commercial Detection Command on the "General Backend Settings -> Job Queue (Global)"
page in the MythTV Setup web (port 6544)

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

```console
pip install mythcommflagwrapper
```

## License

`mythcommflagwrapper` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
