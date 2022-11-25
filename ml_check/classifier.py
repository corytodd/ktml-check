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
        is_cover_letter = self.__is_cover_letter(message)
        is_patch = self.__is_patch(message)
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
            if is_cover_letter:
                return Category.PatchCoverLetter
            return Category.PatchN

        return Category.NotPatch

    def __is_cover_letter(self, message):
        #
        # Cover letters are hard to detect. SRU patches at least have a
        # template with static bits we can look for. Of course these are
        # not perfect either. Require any two of these phrases.
        sru_template = (
            "[Impact]",
            "[Fix]",
            "[Test]",
            "[Test Plan]",
            "[Where problems could occur]",
        )
        matches = len([s for s in sru_template if s in message.body])
        is_cover_letter = matches >= 2

        return is_cover_letter

    def __is_patch(self, message):
        is_patch = False
        #
        # Skip subjects that do not conform
        if not self.__subject_looks_like_patch(message):
            is_patch = False

        #
        # It would be weird to send a non-patch with git-send-email
        if not is_patch:
            is_patch = self.__is_git_send_email(message)

        #
        # Replies re-use the subject and don't always use the RE: prefix
        # Inspect the body for git-diffs. This will handle single patches.
        if not is_patch:
            is_patch = self.__contains_patch(message)

        #
        # This might be a cover letter which has all the attributes
        # but would be lacking an actual patch.
        if not is_patch:
            is_patch = self.__is_cover_letter(message)

        # At this point, the subject is wrong, no patch is present, and they
        # did not use git-send-email. We can't help them.
        return is_patch

    def __is_git_send_email(self, message):
        # Soft check the message id for git-send-email
        return "git-send-email" in message.message_id

    def __subject_looks_like_patch(self, message):
        if message.subject is None:
            return False
        if not re.search(RE_PATCH, message.subject):
            return False
        return True

    def __contains_patch(self, message):
        #
        # Only messages with inline patches will be parsed
        try:
            patch = PatchSet(message.body)
            return any(patch)
        except:
            return False

    def get_affected_kernels(self, message) -> List[str]:
        return []
