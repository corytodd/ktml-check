from collections import defaultdict

from ml_check.classifier import Category, SimpleClassifier
from tests.base_test import BaseTest


class TestClassifier(BaseTest):
    def test_single_nak(self):
        """An email thread with a single thread of replies and 1 nak"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/single_nak.mbox")

        self.assertEqual(len(messages), 4)
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        expect = {
            Category.NotPatch: 2,
            Category.PatchCoverLetter: 0,
            Category.PatchN: 1,
            Category.PatchAck: 0,
            Category.PatchNak: 1,
            Category.PatchApplied: 0,
        }
        for expect_cat, expect_count in expect.items():
            self.assertEqual(
                cat_count[expect_cat],
                expect_count,
                f"{expect_cat}={expect_count} but got {cat_count[expect_cat]}",
            )

    def test_single_ack(self):
        """An email thread with a single thread of replies and 1 ack"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/single_ack.mbox")

        self.assertEqual(len(messages), 6)
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        expect = {
            Category.NotPatch: 0,
            Category.PatchCoverLetter: 1,
            Category.PatchN: 4,
            Category.PatchAck: 1,
            Category.PatchNak: 0,
            Category.PatchApplied: 0,
        }
        for expect_cat, expect_count in expect.items():
            self.assertEqual(
                cat_count[expect_cat],
                expect_count,
                f"{expect_cat}={expect_count} but got {cat_count[expect_cat]}",
            )

    def test_applied(self):
        """An email thread with two acks and an applied"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/applied.mbox")
        self.assertEqual(len(messages), 4)
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        expect = {
            Category.NotPatch: 0,
            Category.PatchCoverLetter: 0,
            Category.PatchN: 1,
            Category.PatchAck: 2,
            Category.PatchNak: 0,
            Category.PatchApplied: 1,
        }
        for expect_cat, expect_count in expect.items():
            self.assertEqual(
                cat_count[expect_cat],
                expect_count,
                f"{expect_cat}={expect_count} but got {cat_count[expect_cat]}",
            )

    def test_not_patch_subject(self):
        """An email with subject not matching the patch pattern"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/not_a_patch.mbox")

        self.assertEqual(len(messages), 2)
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        expect = {
            Category.NotPatch: 2,
            Category.PatchCoverLetter: 0,
            Category.PatchN: 0,
            Category.PatchAck: 0,
            Category.PatchNak: 0,
            Category.PatchApplied: 0,
        }
        for expect_cat, expect_count in expect.items():
            self.assertEqual(
                cat_count[expect_cat],
                expect_count,
                f"{expect_cat}={expect_count} but got {cat_count[expect_cat]}",
            )

    def test_reply_without_re_prefix(self):
        """An patch series with 3 patches, 2 acks, 1 applied, and 1 reply
        This is actually the wrong answer but from a single message's perspective
        it is correct so we'll test for it. The only way to correctly classify this
        type of thread is to use the PatchSet which has full context of the thread.
        """
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/reply_without_re_prefix.mbox")

        self.assertEqual(len(messages), 8)
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        expect = {
            Category.NotPatch: 0,
            Category.PatchCoverLetter: 1,
            Category.PatchN: 3,
            Category.PatchAck: 3,
            Category.PatchNak: 0,
            Category.PatchApplied: 1,
        }
        for expect_cat, expect_count in expect.items():
            self.assertEqual(
                cat_count[expect_cat],
                expect_count,
                f"{expect_cat}={expect_count} but got {cat_count[expect_cat]}",
            )

    def test_get_affected_kernels(self):
        "Reminder to test get_affected_kernels once implemented"
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/applied.mbox")
        # Assert
        with self.assertRaises(NotImplementedError):
            _ = classifier.get_affected_kernels(messages[0])
