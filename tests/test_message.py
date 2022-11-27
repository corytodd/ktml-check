import mailbox
import unittest
from datetime import datetime, timezone

from ml_check.classifier import Category, SimpleClassifier
from ml_check.message import (
    Message,
    demangle_email,
    parse_mail_date,
    parse_mail_references,
)


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
        (
            "Unrelated text\n\na c <a.c at b.com>",
            True,
            "Unrelated text\n\na c <a.c@b.com>",
        ),
        ("incomplete.loose", False, ""),
        ("incomplete.strict", True, "incomplete.strict"),
        ("this is loose\n\nmultiline", False, ""),
        ("this is strict\n\nmultiline", True, "this is strict\n\nmultiline"),
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


class TestMessage(unittest.TestCase):
    def test_thread_url(self):
        """Test correct thread url formatting"""
        # Setup
        message = Message(
            "test",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body",
            "a@b.com",
            Category.NotPatch,
        )

        # Execute
        actual = message.thread_url

        # Assert
        self.assertTrue("2022" in actual)
        self.assertTrue("January" in actual)

    data_patch_name = (
        # Subject, Message-id, Expected
        (None, "<123-a@b.com>", None),
        ("handle spaces", "<123-a@b.com>", "handle_spaces___123_a_b_com"),
        (
            "h@andle[special]!:chars",
            "<123-a@b.com>",
            "h_andle_special___chars___123_a_b_com",
        ),
    )

    def test_generate_patch_name(self):
        """Test correct thread url formatting, parameterized"""
        for subject, m_id, expect in self.data_patch_name:
            with self.subTest():
                # Setup
                message = Message(
                    subject,
                    m_id,
                    None,
                    set(),
                    datetime(2022, 1, 1),
                    "Hey, this is a body",
                    "a@b.com",
                    Category.NotPatch,
                )

                # Execute
                actual = message.generate_patch_name()

                # Assert
                self.assertEqual(actual, expect)

    def test_generate_patch(self):
        """Test correct patch formatting"""
        # Setup
        message = Message(
            "test",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body",
            "a@b.com",
            Category.NotPatch,
        )

        # Execute
        actual = message.generate_patch()

        # Assert
        self.assertTrue(f"Date: {message.timestamp}" in actual)
        self.assertTrue(f"From: {message.sender}" in actual)
        self.assertTrue(f"Subject: {message.subject}" in actual)
        self.assertTrue(f"Message-Id: {message.message_id}\n" in actual)
        self.assertTrue(f"{message.body}" in actual)

    def test_short_summary(self):
        """Test correct short summary formatting"""
        # Setup
        message = Message(
            "test",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body",
            "a@b.com",
            Category.NotPatch,
        )

        # Execute
        actual = message.short_summary

        # Assert
        self.assertTrue(actual is not None)

    def test_clone_with(self):
        """Test correct cloning"""
        # Setup
        message = Message(
            "test",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body",
            "a@b.com",
            Category.NotPatch,
        )

        replacements = {
            "subject": "new subject",
            "message_id": "<new message id>",
            "in_reply_to": "new in reply_to",
            "references": {"new reference1", "new reference2"},
            "timestamp": datetime(2001, 1, 27),
            "body": "new body",
            "sender": "new sender",
            "category": Category.PatchAck,
        }

        with self.subTest():
            for field, new_value in replacements.items():
                d = {field: new_value}
                new_message = message.clone_with(**d)
                self.assertEqual(new_message.__dict__[field], new_value)
                self.assertNotEqual(
                    message.__dict__[field], new_message.__dict__[field]
                )

    def test_hash(self):
        """Test correct hashing
        - subject, message id, in reply to, and timestamp
        """
        # Setup
        m1 = Message(
            "test 1",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body m1",
            "a@b.com",
            Category.PatchAck,
        )

        m2 = Message(
            "test 1",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body m2",
            "a@b.com",
            Category.NotPatch,
        )

        m3 = Message(
            "test 2",
            "<123-a@b.com>",
            None,
            set(),
            datetime(2022, 1, 1),
            "Hey, this is a body m2",
            "a@b.com",
            Category.NotPatch,
        )

        # Assert
        self.assertEqual(hash(m1), hash(m2))
        self.assertNotEqual(hash(m1), hash(m3))

    def test_from_empty_mail(self):
        """Test parsing a message from an empty mbox message"""
        # Setup
        mbox_message = mailbox.mboxMessage()

        # Execute
        message = Message.from_mail(mbox_message)

        # Assert
        self.assertTrue(message is None)

    def test_from_mail(self):
        """Test parsing a message from an mbox message"""
        # Setup
        raw = """From a.b at c.com  Tue Nov  1 08:30:27 2022
From: a.b at c.com (a b)
Date: Tue,  1 Nov 2022 09:30:27 +0000
Subject: [SRU][PATCH v2] UBUNTU: [Config] Enable mtune z16
Message-ID: <20221101083027.6095-1-a.b@b.com>

[Impact]
In order to make sure the amount of RF energy being absorbed by our
bodies is safe according to the FCC’s guidelines, products must undergo
and pass SAR testing.

[Fix]
Add ACPI SAR table control to pass the testing.

[Test]
the unit is 0.5dBm in following:
"""
        mbox_message = mailbox.mboxMessage(raw)
        classifier = SimpleClassifier()

        # Execute
        message = Message.from_mail(mbox_message, classifier)

        # Assert
        self.assertTrue(message is not None)
        self.assertEqual(message.sender, "a.b@c.com")
        self.assertEqual(
            message.subject, "[SRU][PATCH v2] UBUNTU: [Config] Enable mtune z16"
        )
        self.assertEqual(message.message_id, "<20221101083027.6095-1-a.b@b.com>")
        self.assertEqual(message.category, Category.PatchCoverLetter)
        self.assertEqual(
            message.timestamp, datetime(2022, 11, 1, 9, 30, 27, tzinfo=timezone.utc)
        )
