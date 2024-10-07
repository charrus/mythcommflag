#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# ---------------------------
# Name: mythcommflagwrapper.py
# Python Script
# Author: Charlie Rusbridger
# Purpose
# This python script is intended as a wrapper arroud comskip as an
# alterntative to the built in advert detection.
# ---------------------------
__title__ = "MyCommFlagWrapper"
__author__ = "Charlie Rusbridger"
__version__ = "v0.1.0"

import argparse
import datetime
import logging
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from MythTV import Job, MythDB, Recorded

LOGFILE = "/var/log/mythtv/mythcommflag.log"

logger = logging.getLogger(__title__)


class Recording:
    def __init__(self, **opts):
        """Setup the DB connections and the recording. Convert starttime into
        UTC if coming from a job, and get the filename of the recording."""

        self.db = MythDB()

        # This needs work - shouldn't there be two instantiators depending on
        # options provided?

        if opts.get("jobid"):
            self.job = Job(opts.get("jobid"))
            self.chanid = self.job.chanid
            self.starttime = self.job.starttime.astimezone(
                tz=datetime.timezone.utc
            ).strftime("%Y%m%d%H%M%S")
            self.job.update(status=Job.STARTING)
        elif opts.get("chanid") and opts.get("starttime"):
            self.chanid = opts.get("chanid")
            self.starttime = opts.get("starttime")
        else:
            raise ValueError("Need either jobid or starttime and chanid")

        self.rec = Recorded((self.job.chanid, self.job.starttime), db=self.db)

        dirs = list(self.db.getStorageGroup(groupname=self.rec.storagegroup))
        dirname = Path(dirs[0].dirname)
        self.filename = dirname / self.rec.basename

    def __del__(self):
        """This is to ensure that the job is marked as finished so that the
        job queue isn't blocked on this phantom job thats finished."""

        if self.job and self.job.status not in (
            Job.STARTING,
            Job.RUNNING,
            Job.ERRORED,
            Job.FINISHED,
        ):
            self.job.update(comment="Destructor called", status=Job.FINISHED)
            logger.error("Destructor called with unexpected status")

    def call_comskip(self):
        """Run comskip to generate a skiplist for the recordin."""

        if self.job:
            self.job.update(comment="Scanning", status=Job.RUNNING)

        logger.info(f"filename:  {self.filename}")
        logger.info(f"starttime: {self.starttime}")
        logger.info(f"chanid:    {self.chanid}")

        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            comskip = subprocess.run(
                [
                    "comskip",
                    "--ini=/usr/local/bin/cpruk.ini",
                    f"--output={str(tmpdir)}",
                    "--output-filename=cutlist",
                    "--ts",
                    str(self.filename),
                ],
                capture_output=True,
                encoding="utf-8",
            )

            for line in comskip.stdout.splitlines():
                logger.info(line)
            for line in comskip.stderr.splitlines():
                logger.error(line)

            if comskip.returncode > 1:
                if self.job:
                    self.job.update(
                        comment="Comskip failed", status=Job.ERRORED
                    )
                raise Exception("comskip failed")
            elif comskip.returncode == 1:
                return []

            clre = re.compile(r"(\d+)\s+(\d+)")
            cutlist = []

            with open(tmpdir / "cutlist.txt") as cl:
                for line in cl.readlines():
                    m = clre.match(line)
                    if m:
                        cutlist.append(f"{m.group(1)}-{m.group(2)}")

            return cutlist

    def set_skiplist(self, cutlist=list):
        """Sets the skiplist for the recording, or clear if no breaks found."""

        cutlistargs = [
            "mythutil",
            f"--chanid={self.chanid}",
            f"--starttime={self.starttime}",
        ]
        if cutlist:
            cutlistargs += ["--setskiplist", ",".join(cutlist)]
        else:
            cutlistargs += ["--clearskiplist"]

        logger.info(f"Running: {' '.join(cutlistargs)}")

        mythutil = subprocess.run(
            cutlistargs,
            capture_output=True,
            encoding="utf-8",
        )

        for line in mythutil.stdout.splitlines():
            logger.info(line)
        for line in mythutil.stderr.splitlines():
            logger.error(line)

        if mythutil.returncode != 0:
            if self.job:
                self.job.update(comment="mythutil failed", status=Job.ERRORED)
            raise Exception("mythutil failed")

        self.rec.update(commflagged=True)

        if self.job:
            self.job.update(
                comment=f"{len(cutlist)} break(s) found.", status=Job.FINISHED
            )
        logger.info(f"{len(cutlist)} break(s) found.")


def main():
    """Get arguments from the command line, grab the job information for the
    recording and generate a cutlist for mythutil with comskip."""

    parser = argparse.ArgumentParser(
        description="Wrapper around comflag for MythTV"
    )

    parser.add_argument("--jobid", type=str, required=False, help="The JobID")
    parser.add_argument(
        "--chanid", type=str, required=False, help="The channel id"
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

    logger.info(f"Starting new run; options: {args}")

    recording = Recording(jobid=args.jobid)
    cutlist = recording.call_comskip()
    recording.set_skiplist(cutlist)


if __name__ == "__main__":
    main()
