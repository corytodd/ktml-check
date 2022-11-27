import unittest
from datetime import datetime, timezone

from ml_check.message import demangle_email, parse_mail_date, parse_mail_references


class TestMessageUtils(unittest.TestCase):

    data_dates = (
        # Input, Expected
        # Expected will always use UTC
        (None, None),
        ("ov 2022 09:30:27 +0000", None),
        (
            "Tue,  1 Nov 2022 09:30:27 +0100",
            datetime(2022, 11, 1, 8, 30, 27, tzinfo=timezone.utc),
        ),
        (
            "1 Nov 2022 09:30:27 +0100",
            datetime(2022, 11, 1, 8, 30, 27, tzinfo=timezone.utc),
        ),
        (
            "1 Nov 2022 09:30:27 +0100 (+0100)",
            datetime(2022, 11, 1, 8, 30, 27, tzinfo=timezone.utc),
        ),
    )

    def test_parse_mail_date(self):
        """Date parsing, parameterized testing"""
        for data_in, expect in self.data_dates:
            with self.subTest():
                actual = parse_mail_date(data_in)
                self.assertEqual(actual, expect)

    data_mbox_references = (
        # Input, Expected
        (None, set()),
        ("", set()),
        ("             ", set()),
        ("    a@b.com  ", {"a@b.com"}),
        ("a@b.com", {"a@b.com"}),
        ("a@b.com b@b.com", {"a@b.com", "b@b.com"}),
        (" a@b.com  b@b.com  ", {"a@b.com", "b@b.com"}),
    )

    def test_parse_mail_references(self):
        """Mbox references parsing, parameterized testing"""
        for data_in, expect in self.data_mbox_references:
            with self.subTest():
                actual = parse_mail_references(data_in)
                self.assertEqual(actual, expect)

    data_mangled_email = (
        # Input, Strict mode, Expected
        (None, False, None),
        (None, True, None),
        ("a at b.com (a b)", False, "a@b.com"),
        ("a.c at b.com (a c)", False, "a.c@b.com"),
        ("a <a at b.com>", True, "a <a@b.com>"),
        ("a c <a.c at b.com>", True, "a c <a.c@b.com>"),
    )

    def test_demangle_email(self):
        """Demangle email, parameterized testing"""
        for data_in, strict, expect in self.data_mangled_email:
            with self.subTest():
                actual = demangle_email(data_in, strict)
                self.assertEqual(
                    actual,
                    expect,
                    f"demangle_email({data_in}, {strict}) {actual} != {expect}",
                )
