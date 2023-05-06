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
downloaded and parsed every time this tool is run. This could be done better to save
some time.

Message threading depends on the Message-ID, In-Reply-To, and References headers.
With these three headers, we can sufficiently thread most messages.

By default, we look at the last 14 days of patches. Since a patch always precedes 
a response, we should never see a false positive due to this caching window.

The monthly txt.gz file is not generated immediately for each message. This means 
that if you run this tool, review a patch, then re-run this tool you probably will 
not see any change in the results. Try again later because I'm not sure exactly when 
the file is generated.
"""

import argparse
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Tuple

from ml_check import config
from ml_check.classifier import Category, SimpleClassifier
from ml_check.kteam_mbox import FilterMode, KTeamMbox, PatchFilter
from ml_check.logging import logger

ANSI_COLOR = re.compile(r"\033\[\d+m", re.VERBOSE)

VERSION = "1.0"


@dataclass
class Stats:
    total_patches: int
    total_applied: int
    median_age_days: int
    median_patches_in_patch: int
    top_submitter: Tuple[str, int]
    top_acker: Tuple[str, int]
    top_naker: Tuple[str, int]
    top_applier: Tuple[str, int]
    median_days_to_first_ack: int
    median_days_to_first_nak: int
    median_days_to_applied: int


def save_patch_set(out_directory, patch_set):
    """Write a patch set to disk as a patch files
    :param out_directory: str write results to this directory
    :param patch_set: PatchSet
    """
    patch_dir = os.path.join(out_directory, patch_set.epoch_patch.generate_patch_name())
    os.mkdir(patch_dir)

    # A newline delimited filter containing patch patches
    series_file_path = os.path.join(patch_dir, "series")
    cover_letter = os.path.join(patch_dir, "cover_letter")

    with open(series_file_path, "w") as series:
        if patch_set.epoch_patch:
            with open(cover_letter, "w") as f:
                f.write(patch_set.epoch_patch.generate_patch())
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
    return patch_dir


def clean_str(b):
    """Converts bytes to string, removing all ANSI escape codes"""
    s = b.decode("utf-8")
    s = ANSI_COLOR.sub("", s)
    return s


def analyze_patches(patch_dir, ubuntu_checkpatch):
    ubuntu_checkpatch = os.path.expanduser(ubuntu_checkpatch)
    results_file = os.path.join(patch_dir, "check-patch.txt")
    pattern = f"{patch_dir}/*.patch"
    with open(results_file, "w") as f:
        for patch_path in glob.glob(pattern):
            cmd = [ubuntu_checkpatch, patch_path]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = proc.communicate()
            if err:
                f.write(clean_str(err))
            f.write(clean_str(out))


def generate_stats(patch_sets):
    """Generate stats on patch_sets, return as dict"""
    # Most stats require an epoch patch so filter this once
    valid_patches = [p for p in patch_sets if p.epoch_patch]
    if not valid_patches:
        return None

    now = datetime.utcnow()
    now = now.replace(tzinfo=timezone.utc)

    # Collect patch age based on submission date
    submission_days_agos = [(now - p.epoch_patch.timestamp).days for p in patch_sets]
    patches_per_patch_set = [len(p) for p in valid_patches]
    applied_patch_sets = [p for p in valid_patches if p.applieds]

    # Count up the most frequent sender for each category
    top_submitters = Counter([p.epoch_patch.sender for p in valid_patches]).most_common(
        1
    )
    top_ackers = Counter([a.sender for p in patch_sets for a in p.acks]).most_common(1)
    top_nakers = Counter([a.sender for p in patch_sets for a in p.naks]).most_common(1)
    top_appliers = Counter(
        [a.sender for p in patch_sets for a in p.applieds]
    ).most_common(1)

    days_to_first_acks = []
    days_to_first_naks = []
    days_to_applieds = []
    for p in patch_sets:
        start = p.epoch_patch.timestamp
        if p.acks:
            end = p.acks[0].timestamp
            delta_days = (end - start).days
            days_to_first_acks.append(delta_days)
        if p.naks:
            end = p.naks[0].timestamp
            delta_days = (end - start).days
            days_to_first_naks.append(delta_days)
        if p.applieds:
            end = p.applieds[0].timestamp
            delta_days = (end - start).days
            days_to_applieds.append(delta_days)

    # Ensure all days_xxx counters have one element so
    # we can take the median
    for days_counter in (days_to_first_acks, days_to_first_naks, days_to_applieds):
        if not days_counter:
            days_counter.append(0)

    stats = Stats(
        total_patches=len(valid_patches),
        total_applied=len(applied_patch_sets),
        median_age_days=median(submission_days_agos),
        median_patches_in_patch=median(patches_per_patch_set),
        top_submitter=next(iter(top_submitters), ("", 0)),
        top_acker=next(iter(top_ackers), ("", 0)),
        top_naker=next(iter(top_nakers), ("", 0)),
        top_applier=next(iter(top_appliers), ("", 0)),
        median_days_to_first_ack=median(days_to_first_acks),
        median_days_to_first_nak=median(days_to_first_naks),
        median_days_to_applied=median(days_to_applieds),
    )

    return stats.__dict__


def run(patch_filter, patch_output, clear_cache, show_stats, ubuntu_checkpatch_path):
    """Run mailing list checker
    :param patch_filter: PatchFilter to apply to message list
    :param patch_output: str if specified, emit .patches to this directory
    :param clear_cache: bool delete local cache (will force download all new mail)
    :param show_stats: bool print patch stats to stdout
    :param ubuntu_checkpatch_path: str path to ubuntu_check_patch
    """

    classifier = SimpleClassifier()
    kteam = KTeamMbox(classifier)
    kteam.fetch_mail(patch_filter.since, clear_cache=clear_cache)

    # Ensure patch output directory exists and is clean
    if patch_output:
        patch_output = os.path.expanduser(patch_output)
        if os.path.exists(patch_output):
            shutil.rmtree(patch_output)
        os.mkdir(patch_output)

    # Write filtered patches to disk
    patch_sets = list(kteam.filter_patches(patch_filter))
    for patch_set in sorted(patch_sets):
        if patch_output:
            patch_dir = save_patch_set(patch_output, patch_set)
            if ubuntu_checkpatch_path:
                analyze_patches(patch_dir, ubuntu_checkpatch_path)

    if show_stats:
        stats = generate_stats(patch_sets)
        if stats:
            print(json.dumps(stats, indent=4))

    return 0


def main():
    app_description = f"""Kernel Team mailing-list checker v{VERSION}"""
    app_epilog = (
        """Checks for patches requiring review on the public kernel mailing list"""
    )
    parser = argparse.ArgumentParser(
        description=app_description,
        epilog=app_epilog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-d",
        "--days-back",
        default=config.DEFAULT_DAYS_BACK,
        type=int,
        help="How many days back to search",
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear local ktml-check cache"
    )
    parser.add_argument(
        "-p",
        "--patch-output",
        default="out",
        help="Dump patches to a file named $COVER_LETTER_SUBJECT/$PATCH_SUBJECT.patch in this directory. "
        + "Any patch existing in this location will be deleted.",
    )
    parser.add_argument(
        "--mode",
        type=FilterMode,
        choices=list(FilterMode),
        default=FilterMode.NeedsAcks,
        help="Which patches to show",
    )
    parser.add_argument(
        "--required-acks", type=int, default=2, help="Override the required ACK count"
    )
    parser.add_argument(
        "-s", "--show-stats", action="store_true", help="Print stats to stdout"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print more debug information"
    )
    parser.add_argument(
        "-c",
        "--ubuntu-checkpatch-path",
        default=os.getenv("ML_UBUNTU_CHECKPATCH"),
        help="Path to ubuntu-check-patch",
    )
    parser.add_argument(
        "-i",
        "--ignore-acker",
        action="append",
        help="Ignore patches with acks from this email address (ACK mode only)",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.debug(args)

    since = datetime.now(tz=timezone.utc) - timedelta(days=args.days_back)
    patch_filter = PatchFilter(args.mode, args.required_acks, args.ignore_acker, since)

    ret = 1
    try:
        ret = run(
            patch_filter,
            args.patch_output,
            args.clear_cache,
            args.show_stats,
            args.ubuntu_checkpatch_path,
        )
    except BaseException as ex:
        logger.exception(ex)
    sys.exit(ret)
