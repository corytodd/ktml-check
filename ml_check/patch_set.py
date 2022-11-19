"""
@file patch_set.py
@brief Encapsulates a complete patch set including responses
"""

from functools import cached_property
from typing import List, Optional, Set

from ml_check.classifier import Category, MessageClassifier
from ml_check.message import Message


class PatchSet:
    """One or more patches with their associated mailing list responses"""

    def __init__(self, classifier: MessageClassifier, thread: List[Message]):
        self.classifier = classifier
        self.thread = thread

    @staticmethod
    def filter_thread(
        classifier: MessageClassifier, thread: List[Message], categories: Category
    ) -> List[Message]:
        """Use classifier to filter thread and return sorted result containing only elements of specified category"""
        matches = filter(
            lambda m: classifier.get_category(m) in categories,
            thread,
        )
        matches = list(filter(lambda m: m is not None, matches))
        return sorted(matches)

    @property
    def all_messages(self):
        """Returns all messages from the thread for this patch set"""
        return self.thread

    @cached_property
    def epoch_patch(self) -> Optional[Message]:
        """Epoch (first patch) for this thread"""
        epoch = next(
            iter(self.filter_thread(self.classifier, self.thread, Category.Patch0)),
            None,
        )
        return epoch

    @cached_property
    def patches(self) -> List[Message]:
        """All patches in this thread in chronological order"""
        patches = self.filter_thread(
            self.classifier, self.thread, Category.Patch0 | Category.PatchN
        )
        return sorted(patches)

    @cached_property
    def acks(self) -> List[Message]:
        """All ACK's for this patch set in chronological order"""
        return self.filter_thread(self.classifier, self.thread, Category.PatchAck)

    @cached_property
    def naks(self) -> List[Message]:
        """All NAK's for this patch set in chronological order"""
        return self.filter_thread(self.classifier, self.thread, Category.PatchNak)

    @cached_property
    def applieds(self) -> List[Message]:
        """All APPLIED responses for this patch set in chronological ordser"""
        return self.filter_thread(self.classifier, self.thread, Category.PatchApplied)

    def count_of(self, category: Category):
        """Returns the count of replies for this category"""
        count = 0
        if Category.PatchAck in category:
            count += len(self.acks)
        if Category.PatchNak in category:
            count += len(self.naks)
        if Category.PatchApplied in category:
            count += len(self.applieds)
        return count

    def __lt__(self, other):
        """Sort by natural ordering of message"""
        return self.epoch_patch < other.epoch_patch

    def __gt__(self, other):
        """Sort by natural ordering of message"""
        return self.epoch_patch > other.epoch_patch
