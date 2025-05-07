#!/usr/bin/env python3
# -*- coding: utf-8-unix -*-

"""Wrapper around comskip for use by MythTV."""

import argparse
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Union

from MythTV import (  # type: ignore
    Channel,
    Job,
    MythDB,
    Program,
    Recorded,
    RecordedFile,
    exceptions,
)

from .const import (
    COMM_DETECT_COMMFREE,
    COMM_DETECT_OFF,
    COMM_DETECT_UNINIT,
    COMMSKIP_INI,
)

LOGFILE = "/var/log/mythtv/mythcommflag.log"


logger = logging.getLogger("mythcommflagwrapper")

"""Classes for running comskip."""


class BaseRecording:
    """Base class for recordings."""

    def __init__(self, **kwargs) -> None:
        """Initialize base recording attributes."""
        self._chanid: int
        self._starttime: datetime
        self._filename: Path = Path("")
        self._db: MythDB
        self._recorded: Recorded
        self._program: Program
        self._recordedfile: RecordedFile
        self._channel: Channel
        self._commmethod: int
        self._callsign: str
        self._ini_file = kwargs.get("comskipini", COMMSKIP_INI)

    def _get_recording(self):
        self._db = MythDB()
        self._recorded = Recorded((self._chanid, self._starttime), db=self._db)

        self._program = self._recorded.getProgram()
        self._recordedfile = self._recorded.getRecordedFile()
        # Old recordings may not have the original channel
        try:
            self._channel = Channel(self._chanid)
        except exceptions.MythError:
            self._commmethod = COMM_DETECT_UNINIT
        else:
            self._commmethod = self._channel.commmethod

        dirs = list(self._db.getStorageGroup(groupname=self._recorded.storagegroup))
        dirname = Path(dirs[0].dirname)
        self._filename = dirname / self._recorded.basename
        self._callsign = self._program.callsign

    # Method to run arbitary commands, log the command and the output
    def _run(self, args: List[str]) -> subprocess.CompletedProcess[str]:
        """Run a command and log its output.

        Args:
            args: Command and arguments to execute

        Returns:
            CompletedProcess instance with command results

        Raises:
            subprocess.SubprocessError: If command execution fails
        """
        logger.info("Running: %s", " ".join(args))

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                encoding="utf-8",
                check=False,
            )
        except subprocess.SubprocessError as e:
            logger.error("Command execution failed: %s", e)
            raise

        for line in proc.stdout.splitlines():
            logger.info(line)

        return proc

    @property
    def callsign(self) -> str:
        """The callsign of the recording, for example ITV2."""
        return self._callsign

    @property
    def title(self) -> str:
        """The title of the recording."""
        return self._recorded.title

    @property
    def subtitle(self) -> str:
        """The subtitle of the recording."""
        return self._recorded.subtitle

    @property
    def filename(self) -> str:
        """The full pathname to the recording."""
        return str(self._filename)

    def get_skiplist(self) -> List[str]:
        """Get skiplist.

        Skip if channel has commercial detection off or commercial free.
        """
        if self._commmethod in [
            COMM_DETECT_COMMFREE,
            COMM_DETECT_OFF,
        ]:
            return []
        else:
            return self.call_comskip()

    def call_comskip(self) -> List[str]:
        """Run comskip to generate a skiplist for the recording.

        Returns:
            List of skiplist entries

        Raises:
            ComskipError: If comskip execution fails
        """
        skiplist: List[str] = []

        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            comskip_cmd = self._build_comskip_command(tmp_path)

            try:
                comskip = self._run(comskip_cmd)

                if comskip.returncode == 1:  # No breaks detected
                    return []
                elif comskip.returncode != 0:
                    raise ComskipError(f"comskip failed: {comskip.stderr}")

                skiplist = self._parse_cutlist_file(tmp_path)

            except (subprocess.SubprocessError, ComskipError) as e:
                logger.error("Comskip processing failed: %s", e)
                raise

        return skiplist

    def _build_comskip_command(self, output_dir: Path) -> List[str]:
        """Build comskip command with appropriate arguments."""
        cmd = [
            "comskip",
            f"--ini={self._ini_file}",
            f"--output={output_dir}",
        ]

        if self._filename.suffix == ".ts":
            cmd.append("--ts")

        cmd.append(self.filename)
        return cmd

    def _parse_cutlist_file(self, comskipdir: Path) -> List[str]:
        """Parse cutlist file and return skiplist."""
        skiplist: List[str] = []
        cutlist_file = Path(comskipdir) / Path(self._filename.name).with_suffix(".txt")

        # FILE PROCESSING COMPLETE  47970 FRAMES AT  2500
        # -------------------
        # 1       3589
        # 18702   25873
        # 47662   47970

        skiplist_re = re.compile(r"(\d+)\s+(\d+)")

        with cutlist_file.open() as cutlist_lines:
            for line in cutlist_lines:
                if m := skiplist_re.match(line):
                    skiplist.append(f"{m.group(1)}-{m.group(2)}")

        return skiplist

    def set_skiplist(self, skiplist: List[str] = ()) -> None:
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
            logger.error(f"mythutil failed: {mythutil.stderr}")
            raise Exception("mythutil failed")

        self._recorded.update(commflagged=True)


class RecordingJob(BaseRecording):
    """RecordingJob.

    Recording from a job.
    """

    def __init__(self, jobid: str, **kwargs):
        """Recoding from a job."""
        super().__init__(**kwargs)

        self._jobid = jobid
        self._job = Job(self._jobid)
        self._chanid = self._job.chanid
        self._starttime = self._job.starttime

        self._job.update(status=Job.STARTING)

        super()._get_recording()

    # This could be done better with weakref finalizer objects
    def __del__(self):
        """Destructor.

        This is to ensure that the job is marked as finished so that the
        job queue isn't blocked on this phantom job thats finished.
        """
        if self._job and self._job.status not in [
            Job.ERRORED,
            Job.FINISHED,
        ]:
            self._job.update(comment="Destructor called", status=Job.ERRORED)
            logger.error(
                f"Destructor called with unexpected status: {self._job.status}"
            )

    def get_skiplist(self) -> List[str]:
        """Get skiplist.

        Run comskip and get the skiplist from the generated EDL file.
        """
        self._job.update(comment="Scanning", status=Job.RUNNING)
        try:
            skiplist = super().get_skiplist()
        except Exception:
            self._job.update(comment="commskip failed", status=Job.ERRORED)
            raise

        return skiplist

    def set_skiplist(self, skiplist=List[str]):
        """Set skiplist.

        Add the skiplist to the recording.
        """
        try:
            super().set_skiplist(skiplist)
        except Exception:
            self._job.update(comment="mythutil failed", status=Job.ERRORED)
            raise

        self._job.update(
            comment=f"{len(skiplist)} break(s) found.", status=Job.FINISHED
        )


class Recording(BaseRecording):
    """Recording.

    Recording with chanid and starttime in YYMMDDhhmmss format.
    """

    def __init__(self, chanid: int, starttime: str, **kwargs):
        """Recording with chanid and starttime in YYMMDDhhmmss format."""
        super().__init__(**kwargs)

        self._chanid = chanid
        self._starttime = datetime.strptime(starttime, "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )

        super()._get_recording()


class ComskipError(Exception):
    """Raised when comskip processing fails."""

    pass


def setup_logging(level: str) -> None:
    """Configure logging with proper formatting and handling."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    logging.basicConfig(
        filename=LOGFILE,
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Main entry point for mythcommflagwrapper."""
    parser = argparse.ArgumentParser(description="Wrapper around comflag for MythTV")

    parser.add_argument("--jobid", type=str, required=False, help="The Job ID")
    parser.add_argument("--chanid", type=str, required=False, help="The Channel id")
    parser.add_argument(
        "--comskipini",
        type=str,
        required=False,
        help="Override comskip.ini",
        default=COMMSKIP_INI,
    )
    parser.add_argument(
        "--starttime",
        type=str,
        required=False,
        help="The start time in UTC as YYMMDDhhmmss",
    )
    parser.add_argument("--loglevel", type=str, required=False, default="info")

    args = parser.parse_args()

    try:
        setup_logging(args.loglevel)

        if not args.jobid and not (args.starttime and args.chanid):
            logger.error("Expected either --jobid or --chanid and --starttime")
            raise RuntimeError("Expected either --jobid or --chanid and --starttime")

        logger.debug(f"Starting new run; options: {args}")

        recording: Union[RecordingJob, Recording]
        if args.jobid:
            logger.info(f"jobid:  {args.jobid}")
            recording = RecordingJob(args.jobid, comskipini=args.comskipini)
        else:
            logger.info(f"chanid:  {args.chanid}")
            logger.info(f"starttime:  {args.starttime}")
            recording = Recording(
                args.chanid, args.starttime, comskipini=args.comskipini
            )

        logger.info(f"filename:  {recording.filename}")
        logger.info(f"title:     {recording.title}")
        logger.info(f"subtitle:  {recording.subtitle}")
        logger.info(f"callsign:  {recording.callsign}")

        skiplist = recording.get_skiplist()
        recording.set_skiplist(skiplist)

        logger.info(f"{len(skiplist)} break(s) found.")
    except Exception as e:
        logger.error("Fatal error: %s", e)
        raise


if __name__ == "__main__":
    main()
