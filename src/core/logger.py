import logging
from pathlib import Path


_LOGGER_CONFIGURED = False


def get_logger(name: str = "gto_poker_simulator") -> logging.Logger:
    """Return a shared logger that writes to the project-level LOG file.

    The logger is configured once with both file and stdout handlers so that
    all modules can emit signals for easier debugging.
    """

    global _LOGGER_CONFIGURED

    if not _LOGGER_CONFIGURED:
        log_path = Path(__file__).resolve().parents[2] / "LOG"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_path, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        _LOGGER_CONFIGURED = True

    return logging.getLogger(name)
