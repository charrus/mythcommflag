#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="mythcommflagwrapper",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "MythTV",
    ],
    scripts=[
        'src/mythcommflagwrapper/scripts/mythcommflag-wrapper',
    ],
    data_files=[
        ('etc/mythcommflagwrapper', ['comskip.ini']),
    ],
)
