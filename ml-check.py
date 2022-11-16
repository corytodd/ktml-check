#!/usr/bin/env python3
"""
This tool is used for checking the public kernel-team mailing list for patches that
have not been sufficiently reviewed. A best-effort attempt is made at characterizing
emails based on their subject line. For this reason, false positives and negatives 
will happen.

The basic idea is that we download and cache each year.month txt.gz log from the 
server. After the first run, only the txt.gz for the current year.month will be 
downloaded. All historical messages are stored in what we called a stable mailbox. 
This saves us from parsing them over and over again. The current month's mail is 
downloaded and parsed everytime this tool is run. This could be done better to save
some time.

Message threading depends on the Message-ID, In-Reply-To, and References headers.
With these three headers, we can sufficiently thread most messages.

By default, we look at the last 21 weeks of patches. Since a patch always preceeds 
a response, we should never see a false positive due to this caching window.

The monthly txt.gz file is not generated immediately for each message. This means 
that if you run this tool, review a patch, then re-run this tool you probably will 
not see any change in the results. Try again later because I'm not sure exactly when 
the file is generated.
"""

import argparse
import calendar
import datetime
import glob
import gzip
import logging
import mailbox
import os
import re
import shutil
import sys
from dataclasses import dataclass

import networkx as nx
import requests

# ACLs prevent direct access to the mbox file on the archive server. Fortunately, the
# periodic text file can be parsed as if it were an mbox file so hooray for that.
MONTHLY_URL = "https://lists.ubuntu.com/archives/kernel-team/{year}-{month}.txt.gz"

# As far as I can tell, the link to individual messages is a counter that we cannot
# see from within the .txt.gz mbox data. The best we can do is link to thread view.
# There are no divs on the page that we can link to.
THREAD_URL = "https://lists.ubuntu.com/archives/kernel-team/{year}-{month}/thread.html"

# Compatible with ISO 8601 sorting
MONTHLY_CACHE = "{year:04d}-{month:02d}.mail_cache"
STABLE_MBOX = "stable.mbox"
ACTIVE_MBOX = "active.mbox"
CACHE_DIRECTORY = "~/.cache/ml-check"
RE_PATCH = re.compile(
    r"\[patch|applied:|ack:|re:|nak:|ack\/cmnt:|nak\/cmnt:|ubuntu:|pull",
    re.IGNORECASE,
)


logger = logging.getLogger("ml-check")
logger.addHandler(logging.StreamHandler())


def parse_mail_date(date):
    """The date field in our mail text file doesn't stick to one standard so try a few formats.
    If we fail to parse the timestamp we give up and return None.
    :param data: str raw date
    :return datetime or None
    """
    formats = (
        # Fully RFC 2822 compliant timestamp
        "%a, %d %b %Y %H:%M:%S %z",
        # Missing the weekday field which is optional
        "%d %b %Y %H:%M:%S %z",
    )
    timestamp = None
    if date:
        # Python strptime doesn't like the tz offset format, strip it off
        if "(" in date:
            date, _, _ = date.rpartition(" ")
        for format in formats:
            try:
                timestamp = datetime.datetime.strptime(date, format)
                break
            except ValueError:
                pass
        if timestamp is None:
            logger.warning("failed to find a suitable parser for date: '%s'", date)
    return timestamp


def parse_mail_references(raw):
    """The in-reply-to header is not always set so we also pull the references
    header in order to build an email thread. If present, references is a space
    delimited string of message ids.
    :param raw: str references string
    :return: set(str) of message ids
    """
    references = set()
    if raw:
        for message_id in raw.split(" "):
            message_id = message_id.strip()
            if message_id:
                references.add(message_id)
    return references


def periodic_mail_steps(start, end=datetime.datetime.utcnow()):
    """Returns list of (year, month) tuples from starting datetime to ending datetime, inclusive
    :param start: datetime inclusive start year and month
    :param end: datetime inclusive ending year and month
    :return: Iterable(int, int) where year is zero base and month is one base.
    """
    for year in range(start.year, end.year + 1):
        end_month = end.month + 1 if year == end.year else len(calendar.month_name)
        for month in range(start.month, end_month):
            yield (year, month)


@dataclass
class Message:
    subject: str
    message_id: str
    in_reply_to: str
    references: set
    timestamp: datetime.datetime

    @property
    def thread_url(self):
        year, month = self.timestamp.year, self.timestamp.month
        month_name = calendar.month_name[month]
        return THREAD_URL.format(year=year, month=month_name)

    @staticmethod
    def from_mail(mail):
        """Create a message from a mailbox.mboxMessage"""
        message_id = mail.get("Message-Id")
        in_reply_to = mail.get("In-Reply-To")
        subject = mail.get("Subject")
        timestamp = parse_mail_date(mail.get("Date"))
        references = parse_mail_references(mail.get("References"))

        message = None
        if subject is not None and timestamp is not None:
            subject = subject.replace("\n", " ").replace("\t", " ").replace("  ", " ")
            message = Message(
                subject=subject,
                message_id=message_id,
                in_reply_to=in_reply_to,
                references=references,
                timestamp=timestamp,
            )
        else:
            # Show some details about the message including a truncated body
            logger.debug(
                "message is malformed: message_id=%s, date=%s, body=%s...",
                message_id,
                mail.get("Date"),
                str(mail)[:32].strip(),
            )

        return message

    def short_summary(self):
        """Machine readable summary in YYYY.DD URL subject format"""
        return f"[{self.timestamp.year}.{self.timestamp.month:02d}] {self.thread_url} {self.subject} "

    def is_ack(self):
        """Returns true if this email looks like an ACK"""
        return self.subject is not None and self.subject.lower().startswith("ack")

    def is_nak(self):
        """Returns true if this email looks like a NAK"""
        return self.subject is not None and (
            # Yup, NAC/NAK/NAC K seems to come in many flavors
            self.subject.lower().startswith("nak")
            or self.subject.lower().startswith("nac")
        )

    def is_patch(self):
        """Returns true if this email looks like a patch of some kind"""
        return self.subject is not None and len(re.findall(RE_PATCH, self.subject)) > 0

    def is_applied(self):
        """Returns true if this email looks like an APPLIED response"""
        return self.subject is not None and self.subject.lower().startswith("applied")

    def __hash__(self):
        """Implement for graph relationship"""
        return hash((self.subject, self.message_id, self.in_reply_to, self.timestamp))

    def __lt__(self, other):
        """Sort by timestamp"""
        return self.timestamp < other.timestamp

    def __gt__(self, other):
        """Sort by timestamp"""
        return self.timestamp > other.timestamp

    def __eq__(self, other):
        """Message ids determine equality"""
        return self.message_id == other.message_id


class KTeamMbox:
    def __init__(self):
        self.cache_dir = os.path.expanduser(CACHE_DIRECTORY)
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
        now = datetime.datetime.utcnow()
        since = now - datetime.timedelta(weeks=weeks_back)

        if clear_cache:
            self.clear_cache()

        stable_mbox_path = os.path.join(self.cache_dir, STABLE_MBOX)
        stable_mbox = mailbox.mbox(stable_mbox_path)

        this_year, this_month = now.year, now.month
        for year, month in periodic_mail_steps(since):
            month_name = calendar.month_name[month]
            cache_file = os.path.join(
                self.cache_dir, MONTHLY_CACHE.format(year=year, month=month)
            )

            # Skip bygone YYYY.MM mail, those should not have any changes
            if os.path.exists(cache_file):
                if year < this_year or month < this_month:
                    logger.debug("skipping %s.%s", year, month_name)
                    continue

            logger.info("downloading %s.%s...", year, month_name)
            remote_file = MONTHLY_URL.format(year=year, month=month_name)

            r = requests.get(remote_file)
            with open(cache_file, "wb") as f:
                inflated = gzip.decompress(r.content)
                f.write(inflated)

            # Do not add current year.month mail. The current month is considered
            # active
            if year != this_year or month != this_month:
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
        stable_mbox_path = os.path.join(self.cache_dir, STABLE_MBOX)
        active_mbox_path = os.path.join(self.cache_dir, ACTIVE_MBOX)
        shutil.copyfile(stable_mbox_path, active_mbox_path)

        # The activate mailbox will have the current month's mail appended to it
        now = datetime.datetime.utcnow()
        this_year, this_month = now.year, now.month
        cache_file = os.path.join(
            self.cache_dir, MONTHLY_CACHE.format(year=this_year, month=this_month)
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

        # Unfortunately mbox is not associative so no matter how slice it,
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


def main(weeks_back, clear_cache):
    kteam = KTeamMbox()
    kteam.fetch_mail(weeks_back, clear_cache)

    # Print from oldest to newest
    needs_review = kteam.needing_review()
    for patch, _ in sorted(needs_review):
        print(patch.short_summary())

    return 0


if __name__ == "__main__":
    app_description = """Kernel Team mailing-list checker"""
    app_epilog = (
        """Checks for patches requiring review on the public kernel mailing list"""
    )
    parser = argparse.ArgumentParser(
        description=app_description,
        epilog=app_epilog,
    )
    parser.add_argument(
        "-w", "--weeks-back", default=12, type=int, help="How many weeks back to search"
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear local ml-check cache"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print more debug information"
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    ret = 1
    try:
        ret = main(args.weeks_back, args.clear_cache)
    except BaseException as ex:
        logger.error(ex)
    sys.exit(ret)
