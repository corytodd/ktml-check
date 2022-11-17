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
import logging
import os
import shutil
import sys

from ml_check.kteam_mbox import KTeamMbox
from ml_check.logging import logger


def main(weeks_back, patch_output, clear_cache):
    """Run mailing list checker
    :param weeks_back: int how many weeks back from today to scan
    :param patch_output: str if specified, emit .patches to this directory
    :param clear_cache: bool delete local cache (will force download all new mail)
    """
    kteam = KTeamMbox()
    kteam.fetch_mail(weeks_back, clear_cache)

    if patch_output:
        # Ensure patch output directory exists and is clean
        patch_output = os.path.expanduser(patch_output)
        if os.path.exists(patch_output):
            shutil.rmtree(patch_output)
        os.mkdir(patch_output)

    # Prints from oldest to newest
    needs_review = kteam.needing_review()
    for patch, thread in sorted(needs_review):
        print(patch.short_summary())

        if patch_output:
            # The cover letter subject determines the subdirectory name
            patch_dir = os.path.join(patch_output, patch.generate_patch_name())
            os.mkdir(patch_dir)

            # A patch may have multiple parts so filter out the other responses
            # and dump only the patches.
            for part in thread:

                if part.is_ack() or part.is_nak():
                    continue

                patch_file = os.path.join(
                    patch_dir, f"{part.generate_patch_name()}.patch"
                )
                with open(patch_file, "w") as f:
                    f.write(part.generate_patch())

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
        "-p",
        "--patch-output",
        help="Dump patches to a file named $COVER_LETTER_SUBJECT/$PATCH_SUBJECT.patch in this directory"
        + "Any patch existing in this location will be deleted.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print more debug information"
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    ret = 1
    try:
        ret = main(args.weeks_back, args.patch_output, args.clear_cache)
    except BaseException as ex:
        logger.exception(ex)
    sys.exit(ret)
