# BX_log.py
# Central logging gate for BevelX.
#
# Goal:
# - default logs stay readable
# - deep geometry/debug spam is opt-in
# - audit can report summaries without dumping everything

from __future__ import print_function

LEVEL_OFF = 0
LEVEL_ERROR = 10
LEVEL_WARN = 20
LEVEL_INFO = 30
LEVEL_DEBUG = 40
LEVEL_TRACE = 50

_LEVELS = {
    "OFF": LEVEL_OFF,
    "ERROR": LEVEL_ERROR,
    "WARN": LEVEL_WARN,
    "WARNING": LEVEL_WARN,
    "INFO": LEVEL_INFO,
    "DEBUG": LEVEL_DEBUG,
    "TRACE": LEVEL_TRACE,
}

_DEFAULT_CHANNELS = {
    "settings": True,
    "summary": True,
    "audit": True,
    "audit_clean": False,
    "topology": True,

    "selection": False,
    "reload": False,
    "rails": False,
    "boundary": False,
    "miter": False,
    "support": False,
    "caps": False,
    "transaction": False,
    "transaction_dump": False,
    "append": False
}

_state = {
    "level": LEVEL_INFO,
    "channels": dict(_DEFAULT_CHANNELS)
}


def configure(settings=None):
    """
    Configure logger from BevelX settings.

    Supported settings:
        log_level: OFF / ERROR / WARN / INFO / DEBUG / TRACE
        log_channels: dict of channel bools
        log_<channel>: bool
    """

    if settings is None:
        return

    level_name = str(settings.get("log_level", "INFO")).upper()
    _state["level"] = _LEVELS.get(level_name, LEVEL_INFO)

    channels = dict(_DEFAULT_CHANNELS)

    setting_channels = settings.get("log_channels", None)
    if isinstance(setting_channels, dict):
        for key, value in setting_channels.items():
            channels[str(key)] = bool(value)

    for key in list(channels.keys()):
        settings_key = "log_{0}".format(key)
        if settings_key in settings:
            channels[key] = bool(settings[settings_key])

    _state["channels"] = channels


def is_enabled(level_name="INFO", channel="summary"):
    level = _LEVELS.get(str(level_name).upper(), LEVEL_INFO)

    if _state["level"] == LEVEL_OFF:
        return False

    if level > _state["level"]:
        return False

    if channel is not None:
        return bool(_state["channels"].get(channel, False))

    return True


def log(message, level="INFO", channel="summary"):
    if not is_enabled(level, channel):
        return

    print("[BevelX] {0}".format(message))


def error(message, channel="summary"):
    log(message, level="ERROR", channel=channel)


def warn(message, channel="summary"):
    log(message, level="WARN", channel=channel)


def info(message, channel="summary"):
    log(message, level="INFO", channel=channel)


def debug(message, channel="summary"):
    log(message, level="DEBUG", channel=channel)


def trace(message, channel="summary"):
    log(message, level="TRACE", channel=channel)


def audit(message, level="INFO"):
    log(message, level=level, channel="audit")


def audit_clean(message):
    log(message, level="INFO", channel="audit_clean")