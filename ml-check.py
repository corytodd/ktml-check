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

By default, we look at the last 14 days of patches. Since a patch always preceeds 
a response, we should never see a false positive due to this caching window.

The monthly txt.gz file is not generated immediately for each message. This means 
that if you run this tool, review a patch, then re-run this tool you probably will 
not see any change in the results. Try again later because I'm not sure exactly when 
the file is generated.
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

from ml_check import config
from ml_check.classifier import Category, SimpleClassifier
from ml_check.kteam_mbox import KTeamMbox, PatchFilter, ReplyTypes
from ml_check.logging import logger


def save_patch_set(out_directory, patch_set):
    """Write a patch set to disk as a patch files
    :param out_directory: str write results to this directory
    :param patch_set: PatchSet
    """
    patch_dir = os.path.join(out_directory, patch_set.epoch_patch.generate_patch_name())
    os.mkdir(patch_dir)

    # A newline delimited filter containing patch patches
    series_file_path = os.path.join(patch_dir, "series")

    with open(series_file_path, "w") as series:
        for patch in patch_set.patches:
            patch_file = os.path.join(patch_dir, f"{patch.generate_patch_name()}.patch")
            with open(patch_file, "w") as f:
                f.write(patch.generate_patch())
            if patch.category == Category.PatchN:
                series.write(f"{patch_file}\n")

    # Generate a summary text file showing reply stats
    age_days = (datetime.now(timezone.utc) - patch_set.epoch_patch.timestamp).days
    patch_count = len(patch_set.patches)
    ack_count = len(patch_set.acks)
    nak_count = len(patch_set.naks)
    applied_count = len(patch_set.applieds)

    summary_file = os.path.join(patch_dir, "summary.txt")
    with open(summary_file, "w") as f:
        f.write(f"{patch_set.epoch_patch.subject}\n")
        f.write(f"rfc822msgid: {patch_set.epoch_patch.message_id}\n")
        f.write(f"owner: {patch_set.epoch_patch.sender}\n")
        f.write(f"link: {patch_set.epoch_patch.thread_url}\n")
        f.write(f"age: {age_days} days\n")
        f.write(f"size: {patch_count} patches\n")
        f.write(f"acks: {ack_count}\n")
        f.write(f"naks: {nak_count}\n")
        f.write(f"applied: {applied_count > 0}\n")


def main(days_back, patch_output, reply_type, reply_count, clear_cache):
    """Run mailing list checker
    :param days_back: int how many days back from today to scan
    :param patch_output: str if specified, emit .patches to this directory
    :param reply_type: str which types of replies to dump
    :param reply_count: int if reply_type == "ack" dump patches with this many of that type
    :param clear_cache: bool delete local cache (will force download all new mail)
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

    classifier = SimpleClassifier()
    kteam = KTeamMbox(classifier)
    kteam.fetch_mail(since, clear_cache)

    # Ensure patch output directory exists and is clean
    if patch_output:
        patch_output = os.path.expanduser(patch_output)
        if os.path.exists(patch_output):
            shutil.rmtree(patch_output)
        os.mkdir(patch_output)

    # Write filtered patches to disk
    patch_filter = PatchFilter(reply_type, reply_count, after=since)
    patch_sets = kteam.filter_patches(patch_filter)
    for patch_set in sorted(patch_sets):
        if patch_output:
            save_patch_set(patch_output, patch_set)

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
        "-w",
        "--weeks-back",
        default=None,
        type=int,
        help="(DEPRECATED) How many weeks back to search",
    )
    parser.add_argument(
        "-d",
        "--days-back",
        default=config.DEFAULT_DAYS_BACK,
        type=int,
        help="How many days back to search",
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear local ml-check cache"
    )
    parser.add_argument(
        "-p",
        "--patch-output",
        default="out",
        help="Dump patches to a file named $COVER_LETTER_SUBJECT/$PATCH_SUBJECT.patch in this directory. "
        + "Any patch existing in this location will be deleted.",
    )
    parser.add_argument(
        "--all", action="store_true", help="Dump all patches regardless of review state"
    )
    parser.add_argument(
        "--naks",
        action="store_true",
        help="Dump all patches that have at least one nak",
    )
    parser.add_argument(
        "--applied", action="store_true", help="Dump all patches that have been applied"
    )
    parser.add_argument(
        "--acks", type=int, default=None, help="Dump patches with this many ACKs"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print more debug information"
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.debug(args)

    days = args.days_back
    if args.weeks_back:
        print("WARNING: -w (--weeks-back) is deprecated use -d (--days) instead")
        days = 7 * args.weeks_back

    reply_type = ReplyTypes.Default
    reply_count = None
    if args.all:
        reply_type = ReplyTypes.All
    elif args.acks is not None:
        reply_type = ReplyTypes.Ack
        reply_count = args.acks
    elif args.naks:
        reply_type = ReplyTypes.Nak
    elif args.applied:
        reply_type = ReplyTypes.Applied

    ret = 1
    try:
        ret = main(
            days,
            args.patch_output,
            reply_type,
            reply_count,
            args.clear_cache,
        )
    except BaseException as ex:
        logger.exception(ex)
    sys.exit(ret)
