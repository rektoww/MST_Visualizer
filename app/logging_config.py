import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging() -> None:
    logs_dir = Path(__file__).resolve().parents[1] / "logs"
    logs_dir.mkdir(exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logging.getLogger("PyQt6").setLevel(logging.WARNING)

    if any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        return

    handler = RotatingFileHandler(logs_dir / "app.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(handler)
