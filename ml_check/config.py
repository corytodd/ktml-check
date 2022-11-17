# ACLs prevent direct access to the mbox file on the archive server. Fortunately, the
# periodic text file can be parsed as if it were an mbox file so hooray for that.
MONTHLY_URL = "https://lists.ubuntu.com/archives/kernel-team/{year}-{month}.txt.gz"

# As far as I can tell, the link to individual messages is a counter that we cannot
# see from within the .txt.gz mbox data. The best we can do is link to thread view.
# There are no divs on the page that we can link to.
THREAD_URL = "https://lists.ubuntu.com/archives/kernel-team/{year}-{month}/thread.html"


CACHE_DIRECTORY = "~/.cache/ml-check"

# Compatible with ISO 8601 sorting
MONTHLY_CACHE = "{year:04d}-{month:02d}.mail_cache"
STABLE_MBOX = "stable.mbox"
ACTIVE_MBOX = "active.mbox"
