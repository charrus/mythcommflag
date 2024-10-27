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
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Union

from MythTV import Job, MythDB, Recorded, Channel  # type: ignore

LOGFILE = "/var/log/mythtv/mythcommflag.log"


logger = logging.getLogger(__title__)


# From: https://github.com/MythTV/mythtv/blob/master/mythtv/libs/libmythbase/programtypes.h#L128
class Commercials(Enum):
    COMM_DETECT_COMMFREE = -2
    COMM_DETECT_UNINIT = -1
    COMM_DETECT_OFF = 0x00000000


class BaseRecording:
    def __init__(self):
        """Base class for recordings"""

        self._chanid: int
        self._starttime: datetime
        self._filename: Path = Path("")

    def _get_recording(self):
        self._db = MythDB()
        self._recorded = Recorded((self._chanid, self._starttime), db=self._db)

        logger.debug(f"starttime: {self._starttime}")
        logger.debug(f"chanid:    {self._chanid}")

        self._program = self._recorded.getProgram()
        self._recordedfile = self._recorded.getRecordedFile()
        self._channel = Channel(self._chanid)

        dirs = list(self._db.getStorageGroup(groupname=self._recorded.storagegroup))
        dirname = Path(dirs[0].dirname)
        self._filename = dirname / self._recorded.basename
        self._callsign = self._program.callsign
        self._fps = self._recordedfile.fps

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
        return self._recorded.title

    @property
    def subtitle(self) -> str:
        """The subtitle of the recording"""
        return self._recorded.subtitle

    @property
    def filename(self) -> str:
        """The full pathname to the recording"""
        return str(self._filename)

    def get_skiplist(self) -> List[str]:
        """Get skiplist - skip if channel has commercial detection off or commercial free."""

        if self._channel.commmethod in [
            Commercials.COMM_DETECT_COMMFREE,
            Commercials.COMM_DETECT_OFF,
        ]:
            return []
        else:
            return self.call_comskip()

    def call_comskip(self) -> List[str]:
        """Run comskip to generate a skiplist for the recording."""

        skiplist: List[str] = []
        skiplist_re = re.compile(r"([0-9.]+)\s+([0-9.]+)\s+\d")

        with TemporaryDirectory() as tmpdir:
            comskip_cmd = [
                "comskip",
                "--ini=/usr/local/bin/comskip.ini",
                f"--output={tmpdir}",
            ]

            if self._filename.suffix == ".ts":
                comskip_cmd.append("--ts")

            comskip_cmd.append(self.filename)

            comskip = self._run(comskip_cmd)

            if comskip.returncode > 1:
                raise Exception("comskip failed")
            elif comskip.returncode == 1:
                return []

            edl_file = Path(tmpdir) / f"{self._filename.stem}.edl"

            # EDL format:
            # start   end     type
            # start: seconds
            # end: seconds
            # type: 0 = Cut, 1 = Mute, 2 = Scene, 3 = Commercials
            #
            # 0.00    54.80   3
            # 718.00  969.80  3
            # 1640.04 1891.80 3
            # 2546.64 2798.80 3

            with edl_file.open() as f:
                for line in f:
                    m = skiplist_re.match(line)
                    if m:
                        # Frame number = (time * fps) + 1
                        start = int(float(m.group(1)) * self._fps) + 1
                        end = int(float(m.group(2)) * self._fps + 1)
                        skiplist.append(f"{start}-{end}")

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
            skiplistargs.extend(["--setskiplist", ",".join(skiplist)])
        else:
            skiplistargs.append("--clearskiplist")

        mythutil = self._run(skiplistargs)

        if mythutil.returncode != 0:
            raise Exception("mythutil failed")

        self._recorded.update(commflagged=True)


class RecordingJob(BaseRecording):
    def __init__(self, jobid: str):
        """Recoding from a job."""

        super().__init__()

        self._jobid = jobid
        self._job = Job(self._jobid)
        self._chanid = self._job.chanid
        self._starttime = self._job.starttime

        self._job.update(status=Job.STARTING)

        super()._get_recording()

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

    def get_skiplist(self) -> List[str]:
        self._job.update(comment="Scanning", status=Job.RUNNING)
        try:
            skiplist = super().get_skiplist()
        except Exception:
            self._job.update(comment="commskip failed", status=Job.ERRORED)
            raise

        return skiplist

    def set_skiplist(self, skiplist=List[str]):
        try:
            super().set_skiplist(skiplist)
        except Exception:
            self._job.update(comment="mythutil failed", status=Job.ERRORED)
            raise

        self._job.update(
            comment=f"{len(skiplist)} break(s) found.", status=Job.FINISHED
        )


class Recording(BaseRecording):
    def __init__(self, chanid: int, starttime: str):
        """Recording with chanid and starttime in YYMMDDhhmmss format."""

        super().__init__()

        self._chanid = chanid
        self._starttime = datetime.strptime(starttime, "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )

        super()._get_recording()


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

    logger.info(f"filename:  {recording.filename}")
    logger.info(f"title:     {recording.title}")
    logger.info(f"subtitle:  {recording.subtitle}")
    logger.info(f"callsign:  {recording.callsign}")

    logger.info(f"{len(skiplist)} break(s) found.")


if __name__ == "__main__":
    main()
