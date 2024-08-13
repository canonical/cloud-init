# This file is part of cloud-init. See LICENSE file for license information.
import collections
import functools
import logging
from typing import NamedTuple, Optional

from cloudinit import features, log

LOG = logging.getLogger(__name__)


class DeprecationLog(NamedTuple):
    log_level: int
    message: str


@functools.total_ordering
class Version(
    collections.namedtuple("Version", ["major", "minor", "patch", "rev"])
):
    """A class for comparing versions.

    Implemented as a named tuple with all ordering methods. Comparisons
    between X.Y.N and X.Y always treats the more specific number as larger.

    :param major: the most significant number in a version
    :param minor: next greatest significant number after major
    :param patch: next greatest significant number after minor
    :param rev: the least significant number in a version

    :raises TypeError: If invalid arguments are given.
    :raises ValueError: If invalid arguments are given.

    Examples:
        >>> Version(2, 9) == Version.from_str("2.9")
        True
        >>> Version(2, 9, 1) > Version.from_str("2.9.1")
        False
        >>> Version(3, 10) > Version.from_str("3.9.9.9")
        True
        >>> Version(3, 7) >= Version.from_str("3.7")
        True

    """

    def __new__(
        cls, major: int = -1, minor: int = -1, patch: int = -1, rev: int = -1
    ) -> "Version":
        """Default of -1 allows us to tiebreak in favor of the most specific
        number"""
        return super(Version, cls).__new__(cls, major, minor, patch, rev)

    @classmethod
    def from_str(cls, version: str) -> "Version":
        """Create a Version object from a string.

        :param version: A period-delimited version string, max 4 segments.

        :raises TypeError: Raised if invalid arguments are given.
        :raises ValueError: Raised if invalid arguments are given.

        :return: A Version object.
        """
        return cls(*(list(map(int, version.split(".")))))

    def __gt__(self, other):
        return 1 == self._compare_version(other)

    def __eq__(self, other):
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.rev == other.rev
        )

    def __iter__(self):
        """Iterate over the version (drop sentinels)"""
        for n in (self.major, self.minor, self.patch, self.rev):
            if n != -1:
                yield str(n)
            else:
                break

    def __str__(self):
        return ".".join(self)

    def __hash__(self):
        return hash(str(self))

    def _compare_version(self, other: "Version") -> int:
        """Compare this Version to another.

        :param other: A Version object.

        :return: -1 if self > other, 1 if self < other, else 0
        """
        if self == other:
            return 0
        if self.major > other.major:
            return 1
        if self.minor > other.minor:
            return 1
        if self.patch > other.patch:
            return 1
        if self.rev > other.rev:
            return 1
        return -1


def should_log_deprecation(version: str, boundary_version: str) -> bool:
    """Determine if a deprecation message should be logged.

    :param version: The version in which the thing was deprecated.
    :param boundary_version: The version at which deprecation level is logged.

    :return: True if the message should be logged, else False.
    """
    return boundary_version == "devel" or Version.from_str(
        version
    ) <= Version.from_str(boundary_version)


def log_with_downgradable_level(
    *,
    logger: logging.Logger,
    version: str,
    requested_level: int,
    msg: str,
    args,
):
    """Log a message at the requested level, if that is acceptable.

    If the log level is too high due to the version boundary, log at DEBUG
    level. Useful to add new warnings to previously unguarded code without
    disrupting stable downstreams.

    :param logger: Logger object to log with
    :param version: Version string of the version that this log was introduced
    :param level: Preferred level at which this message should be logged
    :param msg: Message, as passed to the logger.
    :param args: Message formatting args, ass passed to the logger

    :return: True if the message should be logged, else False.
    """
    if should_log_deprecation(version, features.DEPRECATION_INFO_BOUNDARY):
        logger.log(requested_level, msg, args)
    else:
        logger.debug(msg, args)


def deprecate(
    *,
    deprecated: str,
    deprecated_version: str,
    extra_message: Optional[str] = None,
    schedule: int = 5,
    skip_log: bool = False,
) -> DeprecationLog:
    """Mark a "thing" as deprecated. Deduplicated deprecations are
    logged.

    :param deprecated: Noun to be deprecated. Write this as the start
        of a sentence, with no period. Version and extra message will
        be appended.
    :param deprecated_version: The version in which the thing was
        deprecated
    :param extra_message: A remedy for the user's problem. A good
        message will be actionable and specific (i.e., don't use a
        generic "Use updated key." if the user used a deprecated key).
        End the string with a period.
    :param schedule: Manually set the deprecation schedule. Defaults to
        5 years. Leave a comment explaining your reason for deviation if
        setting this value.
    :param skip_log: Return log text rather than logging it. Useful for
        running prior to logging setup.
    :return: NamedTuple containing log level and log message
        DeprecationLog(level: int, message: str)

    Note: uses keyword-only arguments to improve legibility
    """
    if not hasattr(deprecate, "log"):
        setattr(deprecate, "log", set())
    message = extra_message or ""
    dedup = hash(deprecated + message + deprecated_version + str(schedule))
    version = Version.from_str(deprecated_version)
    version_removed = Version(version.major + schedule, version.minor)
    deprecate_msg = (
        f"{deprecated} is deprecated in "
        f"{deprecated_version} and scheduled to be removed in "
        f"{version_removed}. {message}"
    ).rstrip()
    if not should_log_deprecation(
        deprecated_version, features.DEPRECATION_INFO_BOUNDARY
    ):
        level = logging.INFO
    elif hasattr(LOG, "deprecated"):
        level = log.DEPRECATED
    else:
        level = logging.WARN
    log_cache = getattr(deprecate, "log")
    if not skip_log and dedup not in log_cache:
        log_cache.add(dedup)
        LOG.log(level, deprecate_msg)
    return DeprecationLog(level, deprecate_msg)


def deprecate_call(
    *, deprecated_version: str, extra_message: str, schedule: int = 5
):
    """Mark a "thing" as deprecated. Deduplicated deprecations are
    logged.

    :param deprecated_version: The version in which the thing was
        deprecated
    :param extra_message: A remedy for the user's problem. A good
        message will be actionable and specific (i.e., don't use a
        generic "Use updated key." if the user used a deprecated key).
        End the string with a period.
    :param schedule: Manually set the deprecation schedule. Defaults to
        5 years. Leave a comment explaining your reason for deviation if
        setting this value.

    Note: uses keyword-only arguments to improve legibility
    """

    def wrapper(func):
        @functools.wraps(func)
        def decorator(*args, **kwargs):
            # don't log message multiple times
            out = func(*args, **kwargs)
            deprecate(
                deprecated_version=deprecated_version,
                deprecated=func.__name__,
                extra_message=extra_message,
                schedule=schedule,
            )
            return out

        return decorator

    return wrapper
