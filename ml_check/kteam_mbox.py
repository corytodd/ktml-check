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
from datetime import datetime, timedelta

import networkx as nx
import requests

from ml_check import config
from ml_check.logging import logger
from ml_check.message import Message


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
        stable_mbox = mailbox.mbox(stable_mbox_path)

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
                next_mbox = mailbox.mbox(cache_file)
                for mail in next_mbox:
                    stable_mbox.add(mail)

        # Make sure all the new messages are written to disk
        stable_mbox.flush()
        logger.debug("stable mailbox has %s messages", len(stable_mbox.keys()))

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
        for mail in mailbox.mbox(cache_file):
            active_mbox.add(mail)

        active_mbox.flush()
        return active_mbox

    def needing_review(self):
        """Returns a list of patches and their email threads that are
        suspected of needing additional review.
        """

        # Unfortunately mbox is not associative so no matter how we slice it,
        # we need to make our own associative mapping of message_id<>messages.
        # Do this first so we can build our thread map during a second iteration.
        message_map = {}
        for mail in self.__build_active_mbox():
            message = Message.from_mail(mail)
            if message is None:
                continue
            message_map[message.message_id] = message

        # An email thread can be treated as an undirected graph.
        # We could use a DiGraph but that just makes segmentation harder so
        # let's not do that.
        threads = nx.Graph()
        for message in message_map.values():
            if message.in_reply_to in message_map:
                threads.add_edge(message, message_map[message.in_reply_to])
            for ref in message.references:
                if ref in message_map:
                    threads.add_edge(message, message_map[ref])

        for thread in nx.connected_components(threads):
            # Filter out non-patches, applied patches, naked patches, 2+ACKs
            root_message = next(filter(lambda t: t.in_reply_to is None, thread), None)
            if not root_message or not root_message.is_patch():
                continue
            if any([t for t in thread if t.is_applied()]):
                continue
            if any([t for t in thread if t.is_nak()]):
                continue
            acks = [t for t in thread if t.is_ack()]
            if len(acks) >= 2:
                continue

            thread = threads.subgraph(thread)
            yield root_message, thread
