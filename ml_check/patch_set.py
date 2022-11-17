"""
@file patch_set.py
@brief Encapsulates a complete patch set including responses
"""

from functools import cached_property

from ml_check.classifier import Category


class PatchSet:
    def __init__(self, classifier, thread):
        self.classifier = classifier
        self.thread = thread

    @cached_property
    def epoch_patch(self):
        epoch = next(
            filter(
                lambda m: self.classifier.get_category(m) == Category.Patch0,
                self.thread,
            ),
            None,
        )
        return epoch

    @cached_property
    def patches(self):
        patches = [self.epoch_patch]
        patches += list(
            filter(
                lambda m: self.classifier.get_category(m) == Category.PatchN,
                self.thread,
            )
        )
        return sorted(patches)

    @cached_property
    def acks(self):
        return list(
            filter(
                lambda m: self.classifier.get_category(m) == Category.PatchAck,
                self.thread,
            )
        )

    @cached_property
    def naks(self):
        return list(
            filter(
                lambda m: self.classifier.get_category(m) == Category.PatchNak,
                self.thread,
            )
        )

    @cached_property
    def applieds(self):
        return list(
            filter(
                lambda m: self.classifier.get_category(m) == Category.PatchApplied,
                self.thread,
            )
        )

    def __lt__(self, other):
        return self.epoch_patch < other.epoch_patch

    def __gt__(self, other):
        return self.epoch_patch > other.epoch_patch
