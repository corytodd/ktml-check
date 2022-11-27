import glob
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from ml_check.classifier import SimpleClassifier
from ml_check.kteam_mbox import (
    KTeamMbox,
    PatchFilter,
    ReplyTypes,
    datetime_min_tz,
    periodic_mail_steps,
    safe_mbox,
)
from ml_check.patch_set import PatchSet
from tests.base_test import BaseTest


class TestKTeamMboxUtils(unittest.TestCase):
    def test_datetime_min(self):
        """Test that the datetime.min replacement actually includes tz info"""
        # Setup
        now_no_tz = datetime.now()
        now_tz = datetime(2022, 11, 10, tzinfo=timezone.utc)
        expect_tz = timezone.utc

        # Execute
        actual = datetime_min_tz(expect_tz)

        # Assert
        self.assertEqual(actual.tzinfo, expect_tz)
        self.assertLess(actual, now_tz)
        with self.assertRaises(TypeError):
            self.assertLess(actual, now_no_tz)

    def test_periodic_mail_steps(self):
        # Setup
        start = datetime(2016, 6, 1)
        end = datetime(2017, 7, 1)

        # Execute
        mail_steps = list(periodic_mail_steps(start, end))

        # Assert - first step matchs start
        self.assertEqual(mail_steps[0][0], 2016)
        self.assertEqual(mail_steps[0][1], 6)

        # Assert - last step matches end
        self.assertEqual(mail_steps[-1][0], 2017)
        self.assertEqual(mail_steps[-1][1], 7)

        # Assert - no steps have year not in (2016, 2017)
        self.assertTrue(all([m[0] in (2016, 2017) for m in mail_steps]))
        self.assertTrue(all([0 < m[1] <= 12 for m in mail_steps]))

    def test_safe_mbox_clone(self):
        """Check that the mbox is actually closed"""
        with TemporaryDirectory() as temp:
            test_mbox = os.path.join(temp, "new.mbox")
            with safe_mbox(test_mbox) as mbox:
                self.assertTrue(os.path.exists(test_mbox))
            with self.assertRaises(ValueError):
                _ = mbox.items()

    def test_safe_mbox_bad_path(self):
        """Check that the mbox is actually closed"""
        with self.assertRaises(TypeError):
            with safe_mbox(None) as _:
                pass

    def test_safe_mbox_no_permission_path(self):
        """Check that permission errors are handled"""
        with TemporaryDirectory() as temp:
            os.chmod(temp, 0o400)
            test_mbox = os.path.join(temp, "new.mbox")
            with self.assertRaises(PermissionError):
                with safe_mbox(test_mbox) as _:
                    pass
        # Make sure the permission change didn't break cleanup
        self.assertFalse(os.path.exists(temp))


class TestKTeamMbox(unittest.TestCase):
    def mocked_requests_get(*args, **kwargs):
        class MockData:
            def __init__(self, data, status_code):
                self.data = data
                self.status_code = status_code

            @property
            def content(self):
                return self.data

        actual_url = Path(args[0])
        actual_file = actual_url.parts[-1]
        mocked_file = os.path.join("tests", "data", "txt.gz", actual_file)
        if not os.path.exists(mocked_file):
            return MockData(None, 404)
        with open(mocked_file, "rb") as f:
            data = f.read()
        return MockData(data, 200)

    def test_clear_cache(self):
        """Ensure that the cache directory is wiped"""
        # Setup
        with TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {"ML_CHECK_CACHE_DIR": temp}):
                classifier = SimpleClassifier()
                kteam = KTeamMbox(classifier)

                # Execute
                kteam.clear_cache()

                # Assert
                in_cache = glob.glob(f"{temp}/*")
                self.assertEqual(len(in_cache), 0)

    def test_make_cache(self):
        """Ensure that the cache directory is wiped"""
        # Setup
        with TemporaryDirectory() as temp:
            nested_dir = os.path.join(temp, "nested")
            with mock.patch.dict(os.environ, {"ML_CHECK_CACHE_DIR": nested_dir}):
                classifier = SimpleClassifier()

                # Execute
                kteam = KTeamMbox(classifier)

                # Assert
                self.assertTrue(os.path.exists(nested_dir))

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_fetch_mail_by_month(self, _):
        """Test that all months for two years are correctly requested"""
        # Setup
        with TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {"ML_CHECK_CACHE_DIR": temp}):
                classifier = SimpleClassifier()
                kteam = KTeamMbox(classifier)
                # Don't We mock back to January 2021
                since = datetime(2021, 1, 1)
                end = datetime(2022, 12, 1)

                # Execute
                kteam.fetch_mail(since, end)

                # Assert
                mail_cache_glob = os.path.join(temp, "*.mail_cache")
                downloaded = glob.glob(mail_cache_glob)
                self.assertEqual(len(downloaded), 24)

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_fetch_mail_bad_year(self, _):
        """Test that all months for two years are correctly requested"""
        # Setup
        with TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {"ML_CHECK_CACHE_DIR": temp}):
                classifier = SimpleClassifier()
                kteam = KTeamMbox(classifier)
                # Don't We mock back to January 2021
                since = datetime(1809, 1, 1)
                end = datetime(1901, 12, 1)

                # Execute
                kteam.fetch_mail(since, end)

                # Assert
                mail_cache_glob = os.path.join(temp, "*.mail_cache")
                downloaded = glob.glob(mail_cache_glob)
                self.assertEqual(len(downloaded), 0)


class TestPatchFilter(BaseTest):
    def test_patch_filter_empty(self):
        """Empty patch sets should always be rejected"""
        # Setup
        classifier = SimpleClassifier()
        patch_filter = PatchFilter(ReplyTypes.All)
        patch_set = PatchSet([], classifier)

        # Execute
        keep = patch_filter.apply(patch_set)

        # Assert
        self.assertFalse(keep)

    def test_patch_filter_too_old(self):
        """Old patch sets should be rejected"""
        # Setup
        classifier = SimpleClassifier()
        after = datetime(2022, 11, 1, tzinfo=timezone.utc)
        patch_filter = PatchFilter(ReplyTypes.All, after=after)
        messages = self.get_messages("tests/data/october.mbox")
        patch_set = PatchSet(messages, classifier)

        # Execute
        keep = patch_filter.apply(patch_set)

        # Assert
        self.assertFalse(keep)

    def test_patch_filter_all(self):
        """All patches should be kept with all flag"""
        # Setup
        classifier = SimpleClassifier()
        patch_filter = PatchFilter(ReplyTypes.All)
        messages = self.get_messages("tests/data/october.mbox")
        patch_set = PatchSet(messages, classifier)

        # Execute
        keep = patch_filter.apply(patch_set)

        # Assert
        self.assertTrue(keep)

    def test_patch_filter_ack(self):
        """All ack'd patches should be kept"""
        # Setup
        classifier = SimpleClassifier()
        patch_filter = PatchFilter(ReplyTypes.Ack, reply_count=1)
        should_keep = self.get_messages("tests/data/single_ack.mbox")
        should_reject = self.get_messages("tests/data/applied.mbox")
        should_keep_set = PatchSet(should_keep, classifier)
        should_reject_set = PatchSet(should_reject, classifier)

        # Execute
        should_keep = patch_filter.apply(should_keep_set)
        should_reject = patch_filter.apply(should_reject_set)

        # Assert
        self.assertTrue(should_keep)
        self.assertFalse(should_reject)

    def test_patch_filter_nak(self):
        """All nak'd patches should be kept"""
        # Setup
        classifier = SimpleClassifier()
        patch_filter = PatchFilter(ReplyTypes.Nak)
        should_keep = self.get_messages("tests/data/single_nak.mbox")
        should_reject = self.get_messages("tests/data/applied.mbox")
        should_keep_set = PatchSet(should_keep, classifier)
        should_reject_set = PatchSet(should_reject, classifier)

        # Execute
        should_keep = patch_filter.apply(should_keep_set)
        should_reject = patch_filter.apply(should_reject_set)

        # Assert
        self.assertTrue(should_keep)
        self.assertFalse(should_reject)

    def test_patch_filter_applied(self):
        """All applied patches should be kept"""
        # Setup
        classifier = SimpleClassifier()
        patch_filter = PatchFilter(ReplyTypes.Applied)
        should_keep = self.get_messages("tests/data/applied.mbox")
        should_reject = self.get_messages("tests/data/single_ack.mbox")
        should_keep_set = PatchSet(should_keep, classifier)
        should_reject_set = PatchSet(should_reject, classifier)

        # Execute
        should_keep = patch_filter.apply(should_keep_set)
        should_reject = patch_filter.apply(should_reject_set)

        # Assert
        self.assertTrue(should_keep)
        self.assertFalse(should_reject)
