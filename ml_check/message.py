"""
@file message.py
@brief Email abstraction
@detail
The category field of Message is contextual. When a message is initially classified,
we use what we call local classification. This means only information from the message
itself is used for classification. However, sometimes in the context of an email thread, 
the message category could change. That's what we call global classification. That is 
handled from within the PatchSet class. For best results, messages should be collected
into PatchSets and consumed from there.

In other words, you probably don't want to be creating Message types directly.
"""

import calendar
import re
from datetime import datetime

from ml_check import config
from ml_check.classifier import Category, MessageClassifier
from ml_check.logging import logger

# Strict means that we want angle brackets as seen in Acked-by and SOB lines
# Use this when the content might not contain any email addresses.
RE_EMAIL_STRICT = r"<([^\s\\]+)\sat\s([^\s\\]+)>"

# Loose means we know this is a valid email
RE_EMAIL_LOOSE = re.compile(
    r"""
    # 1: any valid email user name including dots
    ([^\s\\]+)
    \sat\s
    # 2: any valid domain name
    ([^\s\\]+)
    (?:\s
        # 3: Optional, actual name of sender which may include spaces
        \((.+)\)
    )?
    $
""",
    re.IGNORECASE | re.VERBOSE,
)


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
                timestamp = datetime.strptime(date, format)
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


def demangle_email(raw):
    """Undo Mailman mangle of message body
    :param raw: str content to demangle
    """
    result = raw
    if raw:

        def replacer(m):
            result = ""
            if m:
                parts = m.groups()
                result = "@".join(parts[:2])
                result = f"<{result}>"
            return result

        result = re.sub(RE_EMAIL_STRICT, replacer, raw)
    return result


def demangle_from(raw):
    """Undo Mailman mangle of From header
    This function turns `account at domain (User Name)` into
        User Name <account@domain>
    If no (User Name) is specified, e.g. `account at domain` then
        account@domain
    :param raw: str content to demangle
    """
    result = raw
    if raw:
        m = RE_EMAIL_LOOSE.match(raw)
        if m and len(m.groups()) == 3:
            account = m.group(1)
            domain = m.group(2)
            username = m.group(3)
            # Mailman may replace a missing username with the email address
            # Don't use a username in these cases.
            if username and not RE_EMAIL_LOOSE.match(username):
                result = f"{username} <{account}@{domain}>"
            else:
                result = f"{account}@{domain}"
    return result


class Message:
    """Simplified email representation"""

    def __init__(
        self,
        subject: str,
        message_id: str,
        in_reply_to: str,
        references: set,
        timestamp: datetime,
        body: str,
        sender: str,
        category: Category,
    ):
        self.subject = subject
        self.message_id = message_id
        self.in_reply_to = in_reply_to
        self.references = references
        self.timestamp = timestamp
        self.body = body
        self.sender = sender
        self.category = category

    @property
    def thread_url(self):
        year, month = self.timestamp.year, self.timestamp.month
        month_name = calendar.month_name[month]
        return config.THREAD_URL.format(year=year, month=month_name)

    @staticmethod
    def from_mail(mail, classifier=None):
        """Create a message from a mailbox.mboxMessage"""
        message_id = mail.get("Message-Id")
        in_reply_to = mail.get("In-Reply-To")
        subject = mail.get("Subject")
        timestamp = parse_mail_date(mail.get("Date"))
        references = parse_mail_references(mail.get("References"))

        body = demangle_email(mail.get_payload())
        sender = demangle_from(mail.get("From"))

        message = None
        if message_id is not None and subject is not None and timestamp is not None:
            subject = subject.replace("\n", " ").replace("\t", " ").replace("  ", " ")
            message = Message(
                subject=subject,
                message_id=message_id,
                in_reply_to=in_reply_to,
                references=references,
                timestamp=timestamp,
                body=body,
                sender=sender,
                category=Category.NotPatch,
            )
            if classifier:
                message.category = classifier.get_category(message)
        else:
            # Show some details about the message including a truncated body
            logger.debug(
                "message is malformed: message_id=%s, date=%s, body=%s...",
                message_id,
                mail.get("Date"),
                str(mail)[:32].strip(),
            )

        return message

    def generate_patch_name(self):
        """Generate a filename-safe name to use for this patch as if it were generated by git format-patch
        The message id is appended to the end of the generated name to protect against duplicate patch names
        """
        if not self.subject:
            return None
        unsafe_name = f"{self.subject}__{self.message_id}"
        patch_name = "".join(
            map(lambda c: "_" if not c.isalnum() else c, unsafe_name)
        ).strip("_")
        return patch_name

    def generate_patch(self):
        """Generate something resembling a .patch file"""
        template = """Date: {date}
From: {sender}
Subject: {subject}
Message-Id: {message_id}

{body}"""
        return template.format(
            date=self.timestamp,
            sender=self.sender,
            subject=self.subject,
            message_id=self.message_id,
            body=self.body,
        )

    @property
    def short_summary(self):
        """Machine readable summary in YYYY.DD URL subject format"""
        return f"[{self.timestamp.year}.{self.timestamp.month:02d}] {self.thread_url} {self.subject}"

    def clone_with(self, **kwargs):
        """Create a clone of this message replacing any fields present in kwargs"""
        return Message(
            subject=kwargs.get("subject", self.subject),
            message_id=kwargs.get("message_id", self.message_id),
            in_reply_to=kwargs.get("in_reply_to", self.in_reply_to),
            references=kwargs.get("references", self.references),
            timestamp=kwargs.get("timestamp", self.timestamp),
            body=kwargs.get("body", self.body),
            sender=kwargs.get("sender", self.sender),
            category=kwargs.get("category", self.category),
        )

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
