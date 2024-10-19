# Mythcommflagwrapper

A simple library with CLI interface for exerimenting with python, current
packaging best practices.

The aim of this project is to offer a easy way to use [Comskip](https://github.com/erikkaashoek/Comskip). This needs to be built and installed first.

Just copy the comskip.ini and src/mythcommflag.py to /usr/local/bin and use:

`/usr/local/bin/mythcommflag-wrapper.py --jobid "%JOBID%"`

as the Commercial Detection Command on the "General Backend Settings -> Job Queue (Global)"
page in the MythTV Setup web (port 6544)

This is very much work in progress.
