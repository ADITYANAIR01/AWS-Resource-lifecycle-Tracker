import logging
import os


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if _is_debug() else logging.INFO)

    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if _is_debug() else logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def _is_debug() -> bool:
    return os.environ.get("FLASK_DEBUG", "false").lower() == "true"