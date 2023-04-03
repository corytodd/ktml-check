# ml-check

Check the kernel-team mailing list for patches that need review.

Everyone has their own way of monitoring the mailing list. The goal of this tool 
is to provide a solution that works independently of any particular MUA. 

This tool pulls patches from the kernel-team mailing list and writes them as patch sets
to your local directory. The patches are well-formed and can be directly applied to your 
target git tree. There are still some rough edges when dealing with replies and certain 
types of cover letters.

By default, we look for any patch that needs acks and has not been nak'd or applied. 
For each patchset, a folder matching the name of the first patch is created and all 
patches will be dumped here. Also included is a file called series which enumerates 
the path to each patch in order.

## Setup

    python setup.py install
## Usage

    ml-check [-h] [-d DAYS_BACK] [--clear-cache] [-p PATCH_OUTPUT] [--mode MODE] [--ubuntu-checkpatch-path PATH] [-v]

## Env

    ML_CHECK_CACHE_DIR direct cache directory to this location

    ML_UBUNTU_CHECKPATCH path (including script name) to ubuntu-checkpatch

## Ubuntu Check Patch

You can use ubuntu-checkpatch directly from this tool. Tell ml-check where your copy of
[ubuntu-checkpath](https://github.com/juergh/tools/blob/master/ubuntu-checkpatch) can be 
found providing `--ubuntu-checkpatch-path`.

## Development

Setup pre-commit before you submit any fixes.

    pre-commit install

## Credits

@juergh for his ideas on writing patches to disk, command line options, and general feedback.
