"""
@file classifier.py
@brief Email classification implementations
@details
Emails are difficult to characterize. There are rules but
not everyone follows them and mistakes can be made. A human
can usually figure out what is supposed to be a patch, the
context of an ACK/NAK/APPLIED, etc. Doing this programmatically
however, can be unrealiable in real life. These classes are 
attempts at making email classification more reliable.
"""

import re
from abc import abstractmethod
from enum import Enum
from typing import List

RE_PATCH = re.compile(
    r"\[?(patch|sru|ubuntu|pull)",
    re.IGNORECASE,
)


class Category(Enum):
    # Not a patch, just some noise on the mailing list
    NotPatch = 0
    # A cover letter or single patch
    Patch0 = 1
    # The first or subsequent patch after a cover letter
    PatchN = 2
    # An ack to a contextual patch
    PatchAck = 3
    # A nak to a contextual patch
    PatchNak = 4
    # Followup stating patch was applied, also contextual
    PatchApplied = 5


class MessageClassifier:
    """Base message classifier"""

    @abstractmethod
    def get_category(self, message) -> Category:
        """Returns the category for this email"""
        ...

    @abstractmethod
    def get_affected_kernels(self, message) -> List[str]:
        """Returns kernels affected by this patch as a list of handles"""
        ...


class SimpleClassifier(MessageClassifier):
    """A regex/pattern based approach"""

    def get_category(self, message) -> Category:
        subject = message.subject
        is_patch = subject is not None and re.match(RE_PATCH, subject)
        is_epoch = message.in_reply_to is None
        is_ack = subject is not None and subject.lower().startswith("ack")
        is_nak = subject is not None and (
            # Yup, NAC/NAK/NAC K seems to come in many flavors
            subject.lower().startswith("nak")
            or subject.lower().startswith("nac")
        )
        is_applied = subject is not None and subject.lower().startswith("applied")

        if is_applied:
            return Category.PatchApplied
        if is_nak:
            return Category.PatchNak
        if is_ack:
            return Category.PatchAck
        if is_patch:
            if is_epoch:
                return Category.Patch0
            return Category.PatchN

        return Category.NotPatch

    def get_affected_kernels(self, message) -> List[str]:
        return []
