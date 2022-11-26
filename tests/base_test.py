import os
import unittest

from ml_check.kteam_mbox import KTeamMbox


class BaseTest(unittest.TestCase):
    def get_messages(self, mbox_path, classifier=None):
        """Returns messages from mbox file"""
        self.assertTrue(os.path.exists(mbox_path))
        messages = []
        for message in KTeamMbox.read_messages(mbox_path, classifier):
            messages.append(message)
        return messages
