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
import os
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

        self.job = None
        self.chanid = 0
        self.starttime = "0"

        self.db = MythDB()

        # This needs work - shouldn't there be two instantiators depending on
        # options provided?

        if opts.get("jobid"):
            self.jobid = opts.get("jobid")
            logger.info(f"jobid: {self.jobid}")
            self.job = Job(self.jobid)
            self.chanid = self.job.chanid
            self.starttime = self.starttime_dt.astimezone(
                tz=datetime.timezone.utc
            ).strftime("%Y%m%d%H%M%S")
            self.rec = Recorded((self.chanid, self.job.starttime), db=self.db)

        elif opts.get("chanid") and opts.get("starttime"):
            self.chanid = opts.get("chanid")
            self.starttime = opts.get("starttime")
            self.rec = Recorded((self.chanid, self.starttime), db=self.db)
        else:
            raise ValueError("jobid or starttime and chanid required")

        logger.info(f"starttime: {self.starttime}")
        logger.info(f"chanid:    {self.chanid}")

        if self.job:
            self.job.update(status=Job.STARTING)
        self.program = self.rec.getProgram()
        self.callsign = self.program.callsign

        dirs = list(self.db.getStorageGroup(groupname=self.rec.storagegroup))
        dirname = Path(dirs[0].dirname)
        self.filename = dirname / self.rec.basename

        logger.info(f"filename:  {self.filename}")

        logger.info(f"title:     {self.rec.title}")
        logger.info(f"subtitle:  {self.rec.subtitle}")
        logger.info(f"callsign:  {self.callsign}")

    # This could be done better with weakref finalizer objects
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

    def get_skiplist(self):
        """Get skiplist - depending on the callsign"""

        if "QUEST" in self.callsign:
            return []
        else:
            return self.call_comskip()

    def call_comskip(self):
        """Run comskip to generate a skiplist for the recording."""

        if self.job:
            self.job.update(comment="Scanning", status=Job.RUNNING)

        logger.info(f"filename:  {self.filename}")
        logger.info(f"starttime: {self.starttime}")
        logger.info(f"chanid:    {self.chanid}")

        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)

            comskip_args = [
                "comskip",
                "--ini=/usr/local/bin/cpruk.ini",
                f"--output={str(tmpdir)}",
                "--output-filename=cutlist",
                "--ts",
                str(self.filename),
            ]

            # To assist with running this via the GUI to fix false positives.
            logger.info(f"Running: {' '.join(comskip_args)}")

            comskip = subprocess.run(
                comskip_args,
                capture_output=True,
                encoding="utf-8",
            )

            for line in comskip.stdout.splitlines():
                logger.info(line)

            if comskip.returncode > 1:
                if self.job:
                    self.job.update(comment="Comskip failed", status=Job.ERRORED)
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

    def call_silence_detect(self):
        """Run ffmpeg and mp3splt to generate a skiplist for the recording."""

        if self.job:
            self.job.update(comment="Scanning", status=Job.RUNNING)

        mp3lines = []

        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            audio_file = tmpdir / "sound.mp2"

            # mp3splt insists on using cwd for the logfile
            oldcwd = os.getcwd()
            os.chdir(tmpdir)

            ffmpeg_args = [
                "ffmpeg",
                "-i",
                str(self.filename),
                "-acodec",
                "copy",
                str(audio_file),
            ]

            # To assist with running this manually to fix false positives.
            logger.info(f"Running: {' '.join(ffmpeg_args)}")

            ffmpeg = subprocess.run(
                ffmpeg_args,
                capture_output=True,
                encoding="utf-8",
            )

            for line in ffmpeg.stdout.splitlines():
                logger.info(line)

            if ffmpeg.returncode != 0:
                if self.job:
                    self.job.update(comment="ffmpeg failed", status=Job.ERRORED)
                raise Exception("ffmpeg failed")

            mp3splt_args = [
                "mp3splt",
                "-s",
                "-p",
                "th=-80,min=0.12",
                str(audio_file),
            ]

            # To assist with running this manually to fix false positives.
            logger.info(f"Running: {' '.join(mp3splt_args)}")

            mp3splt = subprocess.run(
                mp3splt_args,
                capture_output=True,
                encoding="utf-8",
            )

            for line in mp3splt.stdout.splitlines():
                logger.info(line)

            if mp3splt.returncode != 0:
                if self.job:
                    self.job.update(comment="mp3splt failed", status=Job.ERRORED)
                raise Exception("mp3splt failed")

            with open(tmpdir / "mp3splt.log") as cl:
                for line in cl.readlines():
                    mp3lines.append(line.strip())

            os.chdir(oldcwd)

        clre = re.compile(r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)")
        cutlist = []
        start = 0
        finish = 0
        filtered_mp3lines = [x for x in mp3lines if clre.match(x)]
        sorted_mp3lines = sorted(
            filtered_mp3lines, key=lambda val: float(val.split()[0])
        )
        for mp3line in sorted_mp3lines:
            m = clre.match(mp3line)
            duration = (float(m.group(1)), float(m.group(2)))

            if duration[0] - start < 400:
                finish = duration[1]
            else:
                cutlist.append(f"{int(start*25+1)}-{int(finish*25-25)}")
                start, finish = duration

        return cutlist

    def set_skiplist(self, cutlist=list):
        """Sets the skiplist for the recording, or clear if no breaks found."""

        skiplistargs = [
            "mythutil",
            f"--chanid={self.chanid}",
            f"--starttime={self.starttime}",
        ]
        if cutlist:
            skiplistargs += ["--setskiplist", ",".join(cutlist)]
        else:
            skiplistargs += ["--clearskiplist"]

        logger.info(f"Running: {' '.join(skiplistargs)}")

        mythutil = subprocess.run(
            skiplistargs,
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

    parser = argparse.ArgumentParser(description="Wrapper around comflag for MythTV")

    parser.add_argument("--jobid", type=str, required=False, help="The JobID")
    parser.add_argument("--chanid", type=str, required=False, help="The channel id")
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

    logger.info(f"Starting new run; options: {args}")

    if args.jobid:
        recording = Recording(jobid=args.jobid)
    else:
        recording = Recording(chanid=args.chanid, starttime=args.starttime)
    cutlist = recording.get_skiplist()
    recording.set_skiplist(cutlist)


if __name__ == "__main__":
    main()
