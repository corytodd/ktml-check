"""
@file kteam_mbox.py
@brief Remote kernel-team mailing list manager
"""

import calendar
import glob
import gzip
import mailbox
import os
import shutil
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

import networkx as nx
import requests

from ml_check import config
from ml_check.classifier import Category, SimpleClassifier
from ml_check.logging import logger
from ml_check.message import Message
from ml_check.patch_set import PatchSet


def periodic_mail_steps(start, end=datetime.utcnow()):
    """Returns list of (year, month) tuples from starting datetime to ending datetime, inclusive
    :param start: datetime inclusive start year and month
    :param end: datetime inclusive ending year and month
    :return: Iterable(int, int) where year is zero base and month is one base.
    """
    for year in range(start.year, end.year + 1):
        end_month = end.month + 1 if year == end.year else len(calendar.month_name)
        for month in range(start.month, end_month):
            yield (year, month)


class PatchFilter(Protocol):
    def __call__(self, patch_set: PatchSet) -> bool:
        ...

    """Filter accepts a patch set and return true if patch set should be returned
    """


class ReplyTypes(Enum):
    Default = "default"
    Ack = "ack"
    Nak = "nak"
    Applied = "applied"
    All = "all"


class CustomPatchFilter:
    def __init__(self, reply_type: ReplyTypes, reply_count: int):
        logger.debug(
            f"CustomPatchFilter: reply_type={reply_type}, reply_count={reply_count}"
        )
        self.reply_type = reply_type
        self.reply_count = reply_count

    def apply(self, patch_set: PatchSet) -> bool:
        if self.reply_type == ReplyTypes.Default:
            return DefaultPatchFilter(patch_set)
        # ignore non-patches
        if patch_set.epoch_patch is None:
            return False
        if self.reply_type == ReplyTypes.All:
            return True
        if self.reply_type == ReplyTypes.Ack:
            return patch_set.count_of(Category.PatchAck) == self.reply_count
        if self.reply_type == ReplyTypes.Nak:
            return patch_set.count_of(Category.PatchNak) > 0
        if self.reply_type == ReplyTypes.Applied:
            return patch_set.count_of(Category.PatchApplied) > 0
        return True


def DefaultPatchFilter(patch_set: PatchSet) -> bool:
    """Default filter returns unapplied patches with no naks and less than 2 acks"""
    accept = True

    # We someone missed the epoch patch
    if patch_set.epoch_patch is None:
        accept = False

    # Patch has been applied, skip it
    elif any(patch_set.applieds):
        accept = False

    # Patch has been nak'd, skip it
    elif any(patch_set.naks):
        accept = False

    # Patch has two or more ack's, skip it
    elif len(patch_set.acks) >= 2:
        accept = False

    return accept


@contextmanager
def safe_mbox(mbox_path):
    """Allow using with semantics for mbox files"""
    mbox = None
    try:
        mbox = mailbox.mbox(mbox_path)
        yield mbox
    finally:
        if mbox is not None:
            mbox.close()


class KTeamMbox:
    def __init__(self):
        self.cache_dir = os.path.expanduser(config.CACHE_DIRECTORY)
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)

    def clear_cache(self):
        """Deletes local cache file is present"""
        pattern = os.path.join(self.cache_dir, "*.mail_cache")
        for file in glob.glob(pattern):
            os.remove(file)
        if os.path.exists(config.STABLE_MBOX):
            os.remove(config.STABLE_MBOX)

    def fetch_mail(self, weeks_back, clear_cache=False):
        """Download mail archives from remote server
        :param weeks_back: int weeks back from current week to search for abandoned patches
        :param clear_cache: bool True to remove existing mail prior to fetching
        """
        now = datetime.utcnow()
        since = now - timedelta(weeks=weeks_back)

        if clear_cache:
            self.clear_cache()

        stable_mbox_path = os.path.join(self.cache_dir, config.STABLE_MBOX)
        with safe_mbox(stable_mbox_path) as stable_mbox:
            for year, month in periodic_mail_steps(since):
                month_name = calendar.month_name[month]
                cache_file = os.path.join(
                    self.cache_dir, config.MONTHLY_CACHE.format(year=year, month=month)
                )

                # Skip bygone YYYY.MM mail, those should not have any changes
                if os.path.exists(cache_file):
                    if year < now.year or month < now.month:
                        logger.debug("skipping %s.%s", year, month_name)
                        continue

                logger.info("downloading %s.%s...", year, month_name)
                remote_file = config.MONTHLY_URL.format(year=year, month=month_name)

                r = requests.get(remote_file)
                with open(cache_file, "wb") as f:
                    inflated = gzip.decompress(r.content)
                    f.write(inflated)

                # Do not add current year.month mail. The current month is considered
                # active
                if year != now.year or month != now.month:
                    with safe_mbox(cache_file) as next_mbox:
                        for mail in next_mbox:
                            stable_mbox.add(mail)

            # Make sure all the new messages are written to disk
            stable_mbox.flush()

            logger.debug("stable mailbox has %s messages", len(stable_mbox.keys()))

    @contextmanager
    def __build_active_mbox(self):
        """Builds a new mbox based on the stable mbox, adding only mail from
        the current (active) year.month."""
        # Overwrite active mailbox so we can rebuild it
        stable_mbox_path = os.path.join(self.cache_dir, config.STABLE_MBOX)
        active_mbox_path = os.path.join(self.cache_dir, config.ACTIVE_MBOX)
        shutil.copyfile(stable_mbox_path, active_mbox_path)

        # The active mailbox will have the current month's mail appended to it
        now = datetime.utcnow()
        this_year, this_month = now.year, now.month
        cache_file = os.path.join(
            self.cache_dir,
            config.MONTHLY_CACHE.format(year=this_year, month=this_month),
        )

        # Active mailbox will be the stable mail + the current month's mail
        active_mbox = mailbox.mbox(active_mbox_path)
        with safe_mbox(cache_file) as cached_mbox:
            for mail in cached_mbox:
                active_mbox.add(mail)

        active_mbox.flush()
        yield active_mbox
        active_mbox.close()

    def filter_patches(self, patch_filter: PatchFilter = DefaultPatchFilter):
        """Returns a list of patches and their email threads that are
        suspected of needing additional review.
        """
        classifier = SimpleClassifier()

        for thread in self.all_threads():

            patch_set = PatchSet(classifier, thread)

            if patch_filter(patch_set):
                yield patch_set

    def all_threads(self):
        """Returns all messagse from mailbox in thread form
        :return: list(Message) in chronological order
        """
        # Unfortunately mbox is not associative so no matter how we slice it,
        # we need to make our own associative mapping of message_id<>messages.
        # Do this first so we can build our thread map during a second iteration.
        message_map = {}
        with self.__build_active_mbox() as mbox:
            for mail in mbox:
                message = Message.from_mail(mail)
                if message is None:
                    continue
                message_map[message.message_id] = message

        # An email thread can be treated as an undirected graph.
        # We could use a DiGraph but that just makes segmentation harder so
        # let's not do that.
        threads = nx.Graph()
        for message in message_map.values():
            threads.add_node(message)
            if message.in_reply_to in message_map:
                threads.add_edge(message, message_map[message.in_reply_to])
            for ref in message.references:
                if ref in message_map:
                    threads.add_edge(message, message_map[ref])

        for thread in nx.connected_components(threads):
            # Convert to list for deterministic ordering
            messages = [m for m in thread]
            yield sorted(messages)

    @staticmethod
    def read_messages(mbox_path):
        """Helper for reading messages from an mbox file.
        Malformed messages may be returned as None
        """
        with safe_mbox(mbox_path) as mbox:
            for mail in mbox:
                yield Message.from_mail(mail)
