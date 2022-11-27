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
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import networkx as nx
import requests
from dateutil.relativedelta import relativedelta

from ml_check import config
from ml_check.classifier import Category
from ml_check.logging import logger
from ml_check.message import Message
from ml_check.patch_set import PatchSet


def datetime_min_tz(tz):
    """Work around datetime.min not having a timezone"""
    result = datetime.min
    result = result.replace(tzinfo=tz)
    return result


def periodic_mail_steps(start, end=datetime.utcnow()):
    """Returns list of (year, month) tuples from starting datetime to ending datetime, inclusive
    :param start: datetime inclusive start year and month
    :param end: datetime inclusive ending year and month
    :return: Iterable(int, int) where year is zero base and month is one base.
    """
    start = datetime(start.year, start.month, start.day)
    end = datetime(end.year, end.month, end.day)
    current = start
    while current <= end:
        yield current.year, current.month
        current += relativedelta(months=1)


class ReplyTypes(Enum):
    Ack = "ack"
    Nak = "nak"
    Applied = "applied"
    All = "all"


class PatchFilter:
    def __init__(
        self,
        reply_type: ReplyTypes = ReplyTypes.Ack,
        reply_count: Optional[int] = 2,
        after: Optional[datetime] = None,
    ):
        self.after = datetime_min_tz(timezone.utc) if after is None else after
        self.reply_type = reply_type
        self.reply_count = reply_count
        logger.debug(
            "PatchFilter: reply_type=%s, reply_count=%s, after=%s",
            reply_type,
            reply_count,
            self.after,
        )

    def apply(self, patch_set: PatchSet) -> bool:
        # ignore non-patches
        if patch_set.epoch_patch is None:
            return False
        if patch_set.epoch_patch.timestamp < self.after:
            return False
        if self.reply_type == ReplyTypes.All:
            return True
        if self.reply_type == ReplyTypes.Ack:
            return patch_set.count_of(Category.PatchAck) == self.reply_count
        if self.reply_type == ReplyTypes.Nak:
            return patch_set.count_of(Category.PatchNak) > 0
        return patch_set.count_of(Category.PatchApplied) > 0


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
    """Remote mbox utilitiy"""

    def __init__(self, classifier):
        self.classifier = classifier
        cache_dir = os.getenv("ML_CHECK_CACHE_DIR", config.CACHE_DIRECTORY)
        self.cache_dir = os.path.expanduser(cache_dir)
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)
        with open(os.path.join(self.cache_dir, "last_run"), "w") as f:
            f.write(f"{datetime.now()}")

    def clear_cache(self):
        """Deletes local cache file is present"""
        pattern = os.path.join(self.cache_dir, "*")
        for file in glob.glob(pattern):
            os.remove(file)

    def fetch_mail(self, since=None, end=None, clear_cache=False):
        """Download mail archives from remote server
        :param since: datetime to search from for abandoned patches
        :param end: datetime to search to for abandoned patches, defaults to utc now
        :param clear_cache: bool True to remove existing mail prior to fetching
        """
        now = datetime.utcnow()
        if since is None:
            since = now - timedelta(weeks=config.DEFAULT_DAYS_BACK)
        if end is None:
            end = now

        if clear_cache:
            self.clear_cache()

        stable_mbox_path = os.path.join(self.cache_dir, config.STABLE_MBOX)
        with safe_mbox(stable_mbox_path) as stable_mbox:
            for year, month in periodic_mail_steps(since, end):
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
                if r.status_code != 200:
                    logger.warning("failed to download %s.%s", year, month_name)
                    continue

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
        active_mbox = None
        try:
            active_mbox = mailbox.mbox(active_mbox_path)
            with safe_mbox(cache_file) as cached_mbox:
                for mail in cached_mbox:
                    active_mbox.add(mail)

            active_mbox.flush()
            yield active_mbox
        finally:
            if active_mbox:
                active_mbox.close()

    def filter_patches(self, patch_filter: PatchFilter):
        """Returns a list of patches and their email threads that are
        suspected of needing additional review. The returned PatchSets
        will be globally classified.
        """
        for thread in self.__all_threads():
            patch_set = PatchSet(thread, self.classifier)
            if patch_filter.apply(patch_set):
                yield patch_set

    def __all_threads(self):
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

        # Each thread connects a set of connected components.
        # Emails outside of a thread will not be connected.
        for thread in nx.connected_components(threads):
            # Convert to list for deterministic ordering
            messages = [m for m in thread]
            yield sorted(messages)

    @staticmethod
    def read_messages(mbox_path, classifier=None):
        """Helper for reading messages from an mbox file.
        Malformed messages may be returned as None. Messages
        that are parsed will be locally classified if a
        classifier is provided.
        """
        with safe_mbox(mbox_path) as mbox:
            for mail in mbox:
                message = Message.from_mail(mail, classifier)
                yield message
