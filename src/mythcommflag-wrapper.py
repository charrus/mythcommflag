#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Wrapper around comskip for use by MythTV."""

import argparse
import logging
from typing import Union

from mythcommflagwrapper import Recording, RecordingJob

LOGFILE = "/var/log/mythtv/mythcommflag.log"


logger = logging.getLogger("mythcommflagwrapper")


def main():
    """Mythcommflagwrapper.

    Get arguments from the command line, grab the job information for the
    recording and generate a skiplist for mythutil with comskip.
    """
    parser = argparse.ArgumentParser(
        description="Wrapper around comflag for MythTV"
    )

    parser.add_argument("--jobid", type=str, required=False, help="The Job ID")
    parser.add_argument(
        "--chanid", type=str, required=False, help="The Channel id"
    )
    parser.add_argument(
        "--starttime",
        type=str,
        required=False,
        help="The start time in UTC as YYMMDDhhmmss",
    )
    parser.add_argument("--loglevel", type=str, required=False, default="info")

    args = parser.parse_args()

    # Set the log level
    loglevel = args.loglevel
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {loglevel}")
    logging.basicConfig(
        filename=LOGFILE,
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not args.jobid and not (args.starttime and args.chanid):
        logger.error("Expected either --jobid or --chanid and --starttime")
        raise RuntimeError(
            "Expected either --jobid or --chanid and --starttime"
        )

    logger.debug(f"Starting new run; options: {args}")

    recording: Union[RecordingJob, Recording]
    if args.jobid:
        recording = RecordingJob(args.jobid)
    else:
        recording = Recording(args.chanid, args.starttime)

    logger.info(f"filename:  {recording.filename}")
    logger.info(f"title:     {recording.title}")
    logger.info(f"subtitle:  {recording.subtitle}")
    logger.info(f"callsign:  {recording.callsign}")

    skiplist = recording.get_skiplist()
    recording.set_skiplist(skiplist)

    logger.info(f"{len(skiplist)} break(s) found.")


if __name__ == "__main__":
    main()
