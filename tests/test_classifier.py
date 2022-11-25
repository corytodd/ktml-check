import os
import unittest
from collections import defaultdict

from ml_check.classifier import Category, SimpleClassifier
from ml_check.kteam_mbox import KTeamMbox


class BaseTest(unittest.TestCase):
    def get_messages(self, mbox_path):
        """Returns messages from mbox file"""
        self.assertTrue(os.path.exists(mbox_path))
        for message in KTeamMbox.read_messages(mbox_path):
            yield message


class TestClassifier(BaseTest):
    def test_single_nak(self):
        """An email thread with a single thread of replies and 1 nak"""
        # Setup
        messages = [m for m in self.get_messages("tests/data/single_nak.mbox")]
        self.assertEqual(len(messages), 4)
        classifier = SimpleClassifier()
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        self.assertEqual(cat_count[Category.PatchCoverLetter], 0)
        self.assertEqual(cat_count[Category.PatchN], 1)
        self.assertEqual(cat_count[Category.PatchNak], 1)
        self.assertEqual(cat_count[Category.PatchAck], 0)
        self.assertEqual(cat_count[Category.NotPatch], 2)

    def test_single_ack(self):
        """An email thread with a single thread of replies and 1 ack"""
        # Setup
        messages = [m for m in self.get_messages("tests/data/single_ack.mbox")]
        self.assertEqual(len(messages), 6)
        classifier = SimpleClassifier()
        cat_count = defaultdict(int)

        # Execute
        for m in messages:
            category = classifier.get_category(m)
            cat_count[category] += 1

        # Assert
        self.assertEqual(cat_count[Category.PatchCoverLetter], 1)
        self.assertEqual(cat_count[Category.PatchN], 4)
        self.assertEqual(cat_count[Category.PatchNak], 0)
        self.assertEqual(cat_count[Category.PatchAck], 1)
        self.assertEqual(cat_count[Category.NotPatch], 0)
