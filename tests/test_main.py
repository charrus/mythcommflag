#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Tests for mythcommflagwrapper main functionality."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock MythTV module and its components before importing our code
mock_mythtv = MagicMock()

# Setup Job class with STARTING constant
mock_job_class = MagicMock()
mock_job_class.STARTING = 1
mock_mythtv.Job = mock_job_class

mock_mythtv.MythDB = MagicMock()
mock_mythtv.Recorded = MagicMock()
mock_mythtv.Channel = MagicMock()
mock_mythtv.exceptions = MagicMock()
mock_mythtv.exceptions.MythError = Exception
sys.modules["MythTV"] = mock_mythtv

# Now import our code
from mythcommflagwrapper.__main__ import (  # noqa: E402
    BaseRecording,
    Recording,
    RecordingJob,
)
from mythcommflagwrapper.const import (  # noqa: E402
    COMM_DETECT_COMMFREE,
    COMM_DETECT_OFF,
    COMM_DETECT_UNINIT,
)


class TestBaseRecording(unittest.TestCase):
    """Test BaseRecording class."""

    def setUp(self):
        """Set up test case."""
        # Reset mocks before each test
        mock_mythtv.reset_mock()

        self.recording = BaseRecording()
        self.recording._chanid = 1001
        self.recording._starttime = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.recording._commmethod = COMM_DETECT_UNINIT

    def test_get_recording_success(self):
        """Test successful _get_recording method."""
        # Setup mocks
        mock_db = MagicMock()
        mock_recorded = MagicMock()

        # Configure mock returns
        mock_mythtv.MythDB.return_value = mock_db
        mock_mythtv.Recorded.return_value = mock_recorded

        # Configure Channel mock
        mock_channel = MagicMock()
        mock_channel.commmethod = 1
        mock_mythtv.Channel.side_effect = None  # Clear any previous side effect
        mock_mythtv.Channel.return_value = mock_channel

        # Configure recorded mock
        mock_recorded.storagegroup = "Default"
        mock_recorded.basename = "test.mpg"
        mock_recorded.title = "Test Show"
        mock_recorded.subtitle = "Test Episode"
        mock_recorded.getProgram.return_value = MagicMock(callsign="TestChannel")

        # Configure storage group
        storage_group = MagicMock()
        storage_group.dirname = "/var/lib/mythtv"
        mock_db.getStorageGroup.return_value = [storage_group]

        # Call method
        self.recording._get_recording()

        # Verify calls
        mock_mythtv.MythDB.assert_called_once()
        mock_mythtv.Recorded.assert_called_once_with(
            (self.recording._chanid, self.recording._starttime), db=mock_db
        )
        mock_mythtv.Channel.assert_called_once_with(self.recording._chanid)
        mock_db.getStorageGroup.assert_called_once_with(groupname="Default")

        # Verify attributes
        self.assertEqual(self.recording._filename, Path("/var/lib/mythtv/test.mpg"))
        self.assertEqual(self.recording._commmethod, 1)
        self.assertEqual(self.recording.title, "Test Show")
        self.assertEqual(self.recording.subtitle, "Test Episode")
        self.assertEqual(self.recording.callsign, "TestChannel")

    def test_get_recording_no_channel(self):
        """Test _get_recording when channel doesn't exist."""
        # Setup mocks
        mock_db = MagicMock()
        mock_recorded = MagicMock()

        # Configure mock returns
        mock_mythtv.MythDB.return_value = mock_db
        mock_mythtv.Recorded.return_value = mock_recorded
        mock_mythtv.Channel.side_effect = mock_mythtv.exceptions.MythError()

        # Configure recorded mock
        mock_recorded.storagegroup = "Default"
        mock_recorded.basename = "test.mpg"
        mock_recorded.getProgram.return_value = MagicMock(callsign="TestChannel")

        # Configure storage group
        storage_group = MagicMock()
        storage_group.dirname = "/var/lib/mythtv"
        mock_db.getStorageGroup.return_value = [storage_group]

        # Call method
        self.recording._get_recording()

        # Verify commmethod is set to UNINIT
        self.assertEqual(self.recording._commmethod, COMM_DETECT_UNINIT)

    def test_get_skiplist_commfree(self):
        """Test get_skiplist with commercial free channel."""
        self.recording._commmethod = COMM_DETECT_COMMFREE
        self.assertEqual(self.recording.get_skiplist(), [])

    def test_get_skiplist_off(self):
        """Test get_skiplist with commercial detection off."""
        self.recording._commmethod = COMM_DETECT_OFF
        self.assertEqual(self.recording.get_skiplist(), [])


class TestRecording(unittest.TestCase):
    """Test Recording class."""

    @patch("mythcommflagwrapper.__main__.BaseRecording._get_recording")
    def test_init(self, mock_get_recording):
        """Test initialization."""
        recording = Recording(1001, "20250101083714")
        self.assertEqual(recording._chanid, 1001)
        self.assertEqual(
            recording._starttime, datetime(2025, 1, 1, 8, 37, 14, tzinfo=timezone.utc)
        )
        mock_get_recording.assert_called_once()


class TestRecordingJob(unittest.TestCase):
    """Test RecordingJob class."""

    def setUp(self):
        """Set up test case."""
        # Reset mocks before each test
        mock_mythtv.reset_mock()

    @patch("mythcommflagwrapper.__main__.BaseRecording._get_recording")
    def test_init(self, mock_get_recording):
        """Test initialization."""
        # Setup mock
        mock_job = MagicMock()
        mock_mythtv.Job.return_value = mock_job
        mock_job.chanid = 1001
        mock_job.starttime = datetime(2025, 1, 1, tzinfo=timezone.utc)

        # Create instance
        recording = RecordingJob("12345")

        # Verify
        self.assertEqual(recording._jobid, "12345")
        self.assertEqual(recording._chanid, 1001)
        self.assertEqual(
            recording._starttime, datetime(2025, 1, 1, tzinfo=timezone.utc)
        )
        mock_job.update.assert_called_once_with(status=mock_mythtv.Job.STARTING)
        mock_get_recording.assert_called_once()


if __name__ == "__main__":
    unittest.main()
