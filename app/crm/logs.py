"""
The log files (see LOGGING in hlcrm/settings.py).

  errors.log    WARNING and up: every error with its full traceback, and everything the app could not do
                (an import that failed, a file that was refused, an email that did not go out, low disk space ...)
  changes.log   one line for every history line the app writes: who, which record, what

Both rotate at about 5 MB and keep 10 older files (errors.log.1, errors.log.2, ...).
"""
from logging.handlers import RotatingFileHandler


class QuietRotatingFileHandler(RotatingFileHandler):
    """A rotating log file that never gets in the way of the app.

    On Windows a file cannot be renamed while another program has it open, and the web server, the scheduled
    `tick` command and `runserver` can all write to the same log. When a rollover is refused, this carries on
    writing to the same file and tries again at a later line, instead of printing an error for every line."""

    def __init__(self, filename, **kwargs):
        kwargs.setdefault("maxBytes", 5 * 1024 * 1024)
        kwargs.setdefault("backupCount", 10)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("delay", True)                    # the file is opened by the first line, so an empty folder stays empty
        super().__init__(filename, **kwargs)

    def doRollover(self):
        try:
            super().doRollover()
        except OSError:                                     # the file is in use by another program: keep writing here
            pass


NAMES = ("errors", "changes")            # the two log files Admin > System status offers


def path_of(name):
    """The file for 'errors' or 'changes', or None for any other name."""
    from django.conf import settings
    return settings.LOG_DIR / f"{name}.log" if name in NAMES else None


def tail(path, lines=50, chunk=256 * 1024):
    """The last `lines` lines of a log file (empty when there is no file yet). Reads only the end of a big file."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - chunk))
            data = handle.read()
    except OSError:
        return []
    found = data.decode("utf-8", errors="replace").splitlines()
    if size > chunk:
        found = found[1:]                                   # the first line was cut in half
    return found[-lines:]
