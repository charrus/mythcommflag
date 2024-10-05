#!/usr/bin/env python3

import argparse
import datetime
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from MythTV import Job, MythDB, Recorded

LOGFILE = "/var/log/mythtv/mythcommflag.log"

logger = logging.getLogger(Path(__file__).name)


@dataclass
class Recording:
    jobid: str

    def setup_recording(self):
        self.db = MythDB()
        self.job = Job(self.jobid)
        self.job.update(status=Job.STARTING)

        self.rec = Recorded((self.job.chanid, self.job.starttime), db=self.db)

        self.chanid = self.rec.chanid

        self.starttime = self.rec.starttime.astimezone(
            tz=datetime.timezone.utc
        ).strftime("%Y%m%d%H%M%S")

        dirs = list(self.db.getStorageGroup(groupname=self.rec.storagegroup))
        dirname = Path(dirs[0].dirname)
        self.filename = dirname / self.rec.basename

        self.job.update(comment="Scanning", status=Job.RUNNING)

        logger.info(f"filename:  {self.filename}")
        logger.info(f"starttime: {self.starttime}")
        logger.info(f"chanid:    {self.chanid}")

    def get_cutlist(self):

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            comskip = subprocess.run(
                [
                    "/usr/local/bin/comskip",
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

            if comskip.returncode > 1:
                self.job.update(comment="Comskip failed", status=Job.ERRORED)
                raise Exception("comskip failed")
            elif comskip.returncode == 1:
                self.job.update(comment="No breaks found", status=Job.FINISHED)
                return []

            clre = re.compile(r"(\d+)\s+(\d+)")
            cutlist = []

            with open(tmpdir / "cutlist.txt") as cl:
                for line in cl.readlines():
                    m = clre.match(line)
                    if m:
                        cutlist.append(f"{m.group(1)}-{m.group(2)}")

            return cutlist

    def setskiplist(self, cutlist=list):
        """Sets the skiplist for the recording"""

        logger.info(f"Calling: mythutil --setskiplist {','.join(cutlist)}")
        logger.info(
            f"         --chanid={self.chanid} --starttime={self.starttime}"
        )

        mythutil = subprocess.run(
            [
                "mythutil",
                "--setskiplist",
                ",".join(cutlist),
                f"--chanid={self.chanid}",
                f"--starttime={self.starttime}",
            ],
            capture_output=True,
            encoding="utf-8",
        )

        for line in mythutil.stdout.splitlines():
            logger.info(line)

            if mythutil.returncode != 0:
                self.job.update(comment="Comskip failed", status=Job.ERRORED)
                raise Exception("mythutil failed")

        self.rec.update(commflagged=True)

        self.job.update(
            comment=f"{len(cutlist)} break(s) found.", status=Job.FINISHED
        )


def main():
    """Get arguments from the command line, grab the job information for the
    recording and generate a cutlist for mythutil with comskip."""

    parser = argparse.ArgumentParser(
        description="Wrapper around comflag for MythTV"
    )

    parser.add_argument("--jobid", type=str, required=True, help="The JobID")
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
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    logger.info("Starting new run; options:")
    logger.info(f"jobid {args.jobid}")

    recording = Recording(jobid=args.jobid)
    recording.setup_recording()
    cutlist = recording.get_cutlist()
    if cutlist:
        recording.setskiplist(cutlist)


if __name__ == "__main__":
    main()
