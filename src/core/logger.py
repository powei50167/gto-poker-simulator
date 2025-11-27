import json
import logging
from pathlib import Path


_LOGGER_CONFIGURED = {}


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


def get_logger(name: str = "gto_poker_simulator", log_type: str = "general") -> logging.Logger:
    """
    根據傳入的 log_type 回傳不同檔案的 logger。
    log_type 可指定為 "general" 或 "openai"。
    """
    # 使用 (name, log_type) 當作 key，避免重複設定處理器
    global _LOGGER_CONFIGURED
    key = (name, log_type)
    if key in _LOGGER_CONFIGURED:
        return _LOGGER_CONFIGURED[key]

    # 建立新的 logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 根據 log_type 決定要寫入的檔名
    # 假設 log 路徑與專案根目錄相同
    base_dir = Path(__file__).resolve().parents[2]
    log_filename = "openai.log" if log_type.lower() == "openai" else "simulator.log"
    log_path = base_dir / log_filename

    formatter = ExtraFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # 檔案處理器
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 主控台處理器（選用）
    # stream_handler = logging.StreamHandler()
    # stream_handler.setFormatter(formatter)
    # logger.addHandler(stream_handler)

    # 防止訊息往上層 logger 傳遞，避免重複紀錄
    logger.propagate = False

    # 記錄這個 logger 已經配置過
    _LOGGER_CONFIGURED[key] = logger
    return logger