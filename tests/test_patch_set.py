from ml_check.classifier import Category, SimpleClassifier
from ml_check.patch_set import PatchSet
from tests.base_test import BaseTest


class TestPatchSet(BaseTest):
    def test_empty_patch_set(self):
        """A patchset can technically be empty"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/empty.mbox", classifier)

        # Execute
        patch_set = PatchSet(messages)

        # Assert
        self.assertEqual(len(patch_set), 0)

    def test_all_messages(self):
        """Test that all messagse are stored and length (message count) is accurate"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/applied.mbox", classifier)

        # Execute
        patch_set = PatchSet(messages)

        # Assert
        self.assertEqual(len(patch_set.all_messages), len(messages))
        self.assertEqual(len(patch_set), len(messages))

    def test_ack_applied(self):
        """Test a nominal case: 2 acks 1 applied"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/applied.mbox", classifier)

        # Execute
        patch_set = PatchSet(messages)

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
            actual = patch_set.count_of(expect_cat)
            self.assertEqual(
                actual, expect_count, f"{expect_cat}={expect_count} but got {actual}"
            )

    def test_epoch(self):
        """Test a nominal case for epoch detection"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/single_ack.mbox", classifier)
        patch_set = PatchSet(messages)

        # Execute
        epoch = patch_set.epoch_patch

        # Assert
        self.assertTrue(epoch is not None)
        self.assertEqual(
            epoch.message_id, "<20221121055412.3744-1-aaron.ma@canonical.com>"
        )

    def test_no_cover_letter(self):
        """Test a non-coverletter case for epoch detection"""
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages("tests/data/no_cover_letter.mbox", classifier)
        patch_set = PatchSet(messages)

        # Execute
        epoch = patch_set.epoch_patch

        # Assert
        self.assertTrue(epoch is not None)

    def test_sorting(self):
        """Test that two patch sets can be sorted"""
        # Setup
        classifier = SimpleClassifier()
        september = self.get_messages("tests/data/no_cover_letter.mbox", classifier)
        october = self.get_messages("tests/data/october.mbox", classifier)
        november = self.get_messages("tests/data/applied.mbox", classifier)
        september = PatchSet(september)
        october = PatchSet(october)
        november = PatchSet(november)

        # Assert
        self.assertLess(september, october)
        self.assertLess(october, november)
        self.assertGreater(october, september)

    def test_contextual_classify(self):
        """Some messages, when viewed in the context of an entire thread, may have
        a different category. For example, a reply that doesn't change the subject
        or prepend RE: may falsely get categorized as the same type of message it
        is in response to.
        @see test_classifier.TestClassifier.test_reply_without_re_prefix
        """
        # Setup
        classifier = SimpleClassifier()
        messages = self.get_messages(
            "tests/data/reply_without_re_prefix.mbox", classifier
        )
        patch_set = PatchSet(messages)

        # Execute
        patch_set = patch_set.reclassify(classifier)

        # Assert
        expect = {
            Category.NotPatch: 1,
            Category.PatchCoverLetter: 1,
            Category.PatchN: 3,
            Category.PatchAck: 2,
            Category.PatchNak: 0,
            Category.PatchApplied: 1,
        }
        for expect_cat, expect_count in expect.items():
            actual = patch_set.count_of(expect_cat)
            self.assertEqual(
                actual, expect_count, f"{expect_cat}={expect_count} but got {actual}"
            )
