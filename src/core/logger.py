import json
import logging
from pathlib import Path


_LOGGER_CONFIGURED = False


class ExtraFormatter(logging.Formatter):
    """Formatter that appends all extra fields to the log message.

    Standard logging fields are kept in the original format string, while any
    additional values provided through the ``extra`` parameter are serialized
    as JSON and appended to the end of the message.
    """

    _STANDARD_FIELDS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - short override
        base_message = super().format(record)
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._STANDARD_FIELDS and not key.startswith("_")
        }

        if not extra_fields:
            return base_message

        try:
            serialized_extra = json.dumps(extra_fields, ensure_ascii=False)
        except TypeError:
            serialized_extra = str(extra_fields)

        return f"{base_message} | extra={serialized_extra}"


def get_logger(name: str = "gto_poker_simulator") -> logging.Logger:
    """Return a shared logger that writes to the project-level LOG file.

    The logger is configured once with both file and stdout handlers so that
    all modules can emit signals for easier debugging.
    """

    global _LOGGER_CONFIGURED

    if not _LOGGER_CONFIGURED:
        log_path = Path(r"C:\Users\rain50167\Desktop\PROJECT\gto-poker-simulator") / "LOG"
        formatter = ExtraFormatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, stream_handler],
        )
        _LOGGER_CONFIGURED = True

    return logging.getLogger(name)
