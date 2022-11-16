# ml-check

Check the kernel-team mailing list for patches that need some lovin' or scoldin'.

## Setup

    pip install -r requirements.txt

    pre-commit install

## Usage

By default we look back 21 weeks from the current date to find abandoned patches. This is mostly 
for performance reasons since the email threading algorithm is fairly naive.

    ./ml-check.py