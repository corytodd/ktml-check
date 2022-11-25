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
from enum import Flag, auto
from typing import List

try:
    from unidiff import PatchSet
except ModuleNotFoundError:
    print(
        "unidiff required now sorry, the requirements changed."
        "pip install -r requirements.txt"
    )

RE_PATCH = re.compile(
    r"\[?(patch|sru|ubuntu|pull)",
    re.IGNORECASE,
)


class Category(Flag):
    # Not a patch, could be a reply or just noise
    NotPatch = auto()
    # A cover letter
    PatchCoverLetter = auto()
    # A single patch or Nth patch in a series
    PatchN = auto()
    # An ack to a contextual patch
    PatchAck = auto()
    # A nak to a contextual patch
    PatchNak = auto()
    # Followup stating patch was applied, also contextual
    PatchApplied = auto()


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
        is_patch = self.__is_patch(message)
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
                return Category.PatchCoverLetter
            return Category.PatchN

        return Category.NotPatch

    def __is_patch(self, message):
        # Soft check on the subject
        if message.subject is None or not re.search(RE_PATCH, message.subject):
            return False

        # Soft check the message id for git-send-email
        if "git-send-email" in message.message_id:
            return True

        #
        # Replies re-use the subject and don't always use the RE: prefix
        # Inspect the body for git-diffs. This will handle single patches.
        is_patch = False
        try:
            patch = PatchSet(message.body)
            is_patch = any(patch)
        except:
            pass

        #
        # Cover letters are harder to detect. SRU patches at least have a
        # template with static bits we can look for. Of course these are
        # not perfect either. Require any two of these phrases.
        if not is_patch:
            sru_template = (
                "[Impact]",
                "[Fix]",
                "[Test]",
                "[Test Plan]",
                "[Where problems could occur]",
            )
            matches = len([s for s in sru_template if s in message.body])
            is_patch = matches >= 2

        # At this point, the subject is wrong, no patch is present, and they
        # did not use git-send-email. We can't help them.
        return is_patch

    def get_affected_kernels(self, message) -> List[str]:
        return []
