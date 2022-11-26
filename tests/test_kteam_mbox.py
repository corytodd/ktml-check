import unittest
from datetime import datetime, timezone

from ml_check.kteam_mbox import datetime_min_tz, periodic_mail_steps


class TestKteamMbox(unittest.TestCase):
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
