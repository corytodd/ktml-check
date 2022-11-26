"""
@file patch_set.py
@brief Encapsulates a complete patch set including responses
"""
from __future__ import annotations

from functools import cached_property
from typing import List, Optional

from ml_check.classifier import Category, MessageClassifier
from ml_check.message import Message


class PatchSet:
    """One or more patches with their associated mailing list responses"""

    def __init__(self, thread: List[Message], classifier: MessageClassifier):
        self.thread = thread
        self.__reclassify(classifier)

    @staticmethod
    def filter_thread(thread: List[Message], categories: Category) -> List[Message]:
        """Return sorted result containing only elements of specified category"""
        matches = filter(
            lambda m: m.category in categories,
            thread,
        )
        matches = list(filter(lambda m: m is not None, matches))
        return sorted(matches)

    @property
    def all_messages(self):
        """Returns all messages from the thread for this patch set"""
        return self.thread

    @cached_property
    def not_patches(self) -> List[Message]:
        """All non-patch responses for this patch set in chronological order"""
        return self.filter_thread(self.thread, Category.NotPatch)

    @cached_property
    def cover_letters(self) -> List[Message]:
        """All non-patch responses for this patch set in chronological order"""
        return self.filter_thread(self.thread, Category.PatchCoverLetter)

    @cached_property
    def epoch_patch(self) -> Optional[Message]:
        """Epoch (first patch) for this thread is either the cover letter
        or first patch in the series.
        """
        epoch = next(
            iter(self.filter_thread(self.thread, Category.PatchCoverLetter)),
            None,
        )
        if not epoch and self.patches:
            epoch = self.patches[0]
        return epoch

    @cached_property
    def patches(self) -> List[Message]:
        """All patches in this thread in chronological order"""
        patches = self.filter_thread(self.thread, Category.PatchN)
        return sorted(patches)

    @cached_property
    def acks(self) -> List[Message]:
        """All ACK's for this patch set in chronological order"""
        return self.filter_thread(self.thread, Category.PatchAck)

    @cached_property
    def naks(self) -> List[Message]:
        """All NAK's for this patch set in chronological order"""
        return self.filter_thread(self.thread, Category.PatchNak)

    @cached_property
    def applieds(self) -> List[Message]:
        """All APPLIED responses for this patch set in chronological order"""
        return self.filter_thread(self.thread, Category.PatchApplied)

    def count_of(self, category: Category):
        """Returns the count of replies for this category"""
        count = 0
        if Category.NotPatch in category:
            count += len(self.not_patches)
        if Category.PatchCoverLetter in category:
            count += len(self.cover_letters)
        if Category.PatchN in category:
            count += len(self.patches)
        if Category.PatchAck in category:
            count += len(self.acks)
        if Category.PatchNak in category:
            count += len(self.naks)
        if Category.PatchApplied in category:
            count += len(self.applieds)
        return count

    def __reclassify(self, classifier: MessageClassifier) -> PatchSet:
        """Reclassify (mutate) all messages"""

        #
        # First pass for local classification
        for m in self.all_messages:
            m.category = classifier.get_category(m)

        #
        # Without a root message we can't do anything useful
        epoch = self.epoch_patch
        if not epoch:
            return

        # NotPatches can be trusted
        # We are enforcing that all non-patches
        # can at most be 1 reply away from epoch
        # Everything else is a NotPatch
        # CoverLetter/Epoch
        # | Patch 1
        #   | ACK
        #     | NotPatch
        # | Patch 2
        #   | Nak
        #     | NotPatch
        # | Patch N
        #   | APPLIED
        #     | NotPatch
        # | ACK
        # | NAK
        # | APPLIED
        for message in self.all_messages:
            new_category = message.category
            # Do not modify the epoch, skip
            if message == epoch:
                pass
            # NotPatch, re-check to make sure this is still accurate
            elif message.category == Category.NotPatch:
                new_category = classifier.get_category(message)
            # Assume cover letter is correct
            elif message.category == Category.PatchCoverLetter:
                pass
            # A patch should only ever be in response to the epoch
            elif message.category == Category.PatchN:
                if message.in_reply_to and message.in_reply_to != epoch.message_id:
                    new_category = Category.NotPatch
            # The message being reviewed must be a patch
            elif message.category in (
                Category.PatchAck,
                Category.PatchNak,
                Category.PatchApplied,
            ):
                if message.in_reply_to:
                    in_reply_to = next(
                        iter(
                            [
                                m
                                for m in self.all_messages
                                if m.message_id == message.in_reply_to
                            ]
                        ),
                        None,
                    )
                    if in_reply_to and in_reply_to.category not in (
                        Category.PatchCoverLetter,
                        Category.PatchN,
                    ):
                        new_category = Category.NotPatch

            message.category = new_category

    def __lt__(self, other):
        """Sort by natural ordering of message"""
        return self.epoch_patch < other.epoch_patch

    def __gt__(self, other):
        """Sort by natural ordering of message"""
        return self.epoch_patch > other.epoch_patch

    def __len__(self):
        """Returns count of messagse in entire thread"""
        return len(self.thread)
