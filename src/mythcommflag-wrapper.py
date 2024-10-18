#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# ---------------------------
# Name: mythcommflagwrapper.py
# Python Script
# Author: Charlie Rusbridger
# Purpose:
# This python script is intended as a wrapper arroud comskip and mp3splt as an
# alterntative to the built in advert detection.
# ---------------------------
__title__ = "MyCommFlagWrapper"
__author__ = "Charlie Rusbridger"
__version__ = "v0.1.0"

import argparse
from datetime import datetime, timezone
import logging
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List

from MythTV import Job, MythDB, Recorded  # type: ignore

LOGFILE = "/var/log/mythtv/mythcommflag.log"

logger = logging.getLogger(__title__)


class Recording:
    def __init__(self, **opts):
        """Setup the DB connections and the recording."""

        self._job: Job = None
        self._chanid: int = 0
        self._starttime: datetime

        self._db = MythDB()

        # This needs work - shouldn't there be two instantiators depending on
        # options provided?

        if opts.get("jobid"):
            self._jobid = opts.get("jobid")
            self._job = Job(self._jobid)
            self._chanid = self._job.chanid
            self._starttime = self._job.starttime
        elif opts.get("chanid") and opts.get("starttime"):
            self._chanid = opts.get("chanid", 0)
            self._starttime = datetime.strptime(
                opts.get("starttime", ""), "%Y%m%d%H%M%S"
            ).replace(tzinfo=timezone.utc)
        else:
            raise ValueError("jobid or starttime and chanid required")

        self._rec = Recorded((self._chanid, self._starttime), db=self._db)

        logger.debug(f"starttime: {self._starttime}")
        logger.debug(f"chanid:    {self._chanid}")

        if self._job:
            self._job.update(status=Job.STARTING)

        self._program = self._rec.getProgram()
        self._callsign = self._program.callsign

        dirs = list(self._db.getStorageGroup(groupname=self._rec.storagegroup))
        dirname = Path(dirs[0].dirname)
        self._filename = str(dirname / self._rec.basename)

    # This could be done better with weakref finalizer objects
    def __del__(self):
        """This is to ensure that the job is marked as finished so that the
        job queue isn't blocked on this phantom job thats finished."""

        if self._job and self._job.status not in (
            Job.STARTING,
            Job.RUNNING,
            Job.ERRORED,
            Job.FINISHED,
        ):
            self._job.update(comment="Destructor called", status=Job.FINISHED)
            logger.error("Destructor called with unexpected status")

    # Method to run arbitary commands, log the command and the output
    def _run(self, args: List[str]):
        logger.info(f"Running: {' '.join(args)}")

        proc = subprocess.run(
            args,
            capture_output=True,
            encoding="utf-8",
        )

        for line in proc.stdout.splitlines():
            logger.info(line)

        return proc

    @property
    def callsign(self) -> str:
        """The callsign of the recording, for example ITV2"""
        return self._callsign

    @property
    def title(self) -> str:
        """The title of the recording"""
        return self._rec.title

    @property
    def subtitle(self) -> str:
        """The subtitle of the recording"""
        return self._rec.subtitle

    @property
    def filename(self) -> str:
        """The full pathname to the recording"""
        return self._filename

    def get_skiplist(self) -> List[str]:
        """Get skiplist - depending on the callsign"""

        if "QUEST" in self._callsign or "BBC" in self._callsign:
            return []
        else:
            return self.call_comskip()

    def call_comskip(self) -> List[str]:
        """Run comskip to generate a skiplist for the recording."""

        if self._job:
            self._job.update(comment="Scanning", status=Job.RUNNING)

        skiplist: List[str] = []
        skiplist_re = re.compile(r"(\d+)\s+(\d+)")

        with TemporaryDirectory() as tmpdir:
            comskip = self._run(
                [
                    "comskip",
                    "--ini=/usr/local/bin/cpruk.ini",
                    f"--output={tmpdir}",
                    "--output-filename=skiplist",
                    "--ts",
                    self._filename,
                ]
            )

            if comskip.returncode > 1:
                if self._job:
                    self._job.update(comment="Comskip failed", status=Job.ERRORED)
                raise Exception("comskip failed")
            elif comskip.returncode == 1:
                return []

            skiplist_file = Path(tmpdir) / "skiplist.txt"

            with skiplist_file.open() as f:
                for line in f:
                    m = skiplist_re.match(line)
                    if m:
                        skiplist.append(f"{m.group(1)}-{m.group(2)}")

        return skiplist

    def set_skiplist(self, skiplist=List[str]):
        """Sets the skiplist for the recording, or clear if no breaks found."""

        starttime = self._starttime.astimezone(tz=timezone.utc).strftime("%Y%m%d%H%M%S")

        skiplistargs = [
            "mythutil",
            f"--chanid={self._chanid}",
            f"--starttime={starttime}",
        ]
        if skiplist:
            skiplistargs += ["--setskiplist", ",".join(skiplist)]
        else:
            skiplistargs += ["--clearskiplist"]

        mythutil = self._run(skiplistargs)

        if mythutil.returncode != 0:
            if self._job:
                self._job.update(comment="mythutil failed", status=Job.ERRORED)
            raise Exception("mythutil failed")

        self._rec.update(commflagged=True)

        if self._job:
            self._job.update(
                comment=f"{len(skiplist)} break(s) found.", status=Job.FINISHED
            )


def main():
    """Get arguments from the command line, grab the job information for the
    recording and generate a skiplist for mythutil with comskip."""

    parser = argparse.ArgumentParser(description="Wrapper around comflag for MythTV")

    parser.add_argument("--jobid", type=str, required=False, help="The Job ID")
    parser.add_argument("--chanid", type=str, required=False, help="The Channel id")
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
        raise RuntimeError("Expected either --jobid or --chanid and --starttime")

    logger.debug(f"Starting new run; options: {args}")

    if args.jobid:
        recording = Recording(jobid=args.jobid)
    else:
        recording = Recording(chanid=args.chanid, starttime=args.starttime)

    logger.info(f"filename:  {recording.filename}")
    logger.info(f"title:     {recording.title}")
    logger.info(f"subtitle:  {recording.subtitle}")
    logger.info(f"callsign:  {recording.callsign}")

    skiplist = recording.get_skiplist()
    recording.set_skiplist(skiplist)
    logger.info(f"filename:  {recording.filename}")
    logger.info(f"title:     {recording.title}")
    logger.info(f"subtitle:  {recording.subtitle}")
    logger.info(f"callsign:  {recording.callsign}")
    logger.info(f"{len(skiplist)} break(s) found.")


if __name__ == "__main__":
    main()
