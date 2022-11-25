# ml-check

Check the kernel-team mailing list for patches that need some lovin' or scoldin'.

Everyone has their own way of monitoring the mailing list. The goal of this tool 
is to provide a solution that works independently of any particular MUA. 

This tool pulls patches from kernel-team mailing list and writes them as patch sets
to your local directory. The patches are valid can be directly applied to your 
target git tree. There are still some rough edges when dealing with replies and 
certain types of cover letters.

By default, we look for any patch that needs acks and has not been nak'd or applied. For each patchset, a folder matching the name of the first
patch is created and all patches will be dumped here. Also included is a 
file called series which enumerates the path to each patch in order.

## Setup

    pip install -r requirements.txt

    pre-commit install

## Usage

    ml-check.py [-h] [-d DAYS_BACK] [--clear-cache] [-p PATCH_OUTPUT] [--all] [--naks] [--applied] [--acks ACKS] [-v]
