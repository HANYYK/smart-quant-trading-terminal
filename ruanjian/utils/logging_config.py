"""Central logging configuration."""
import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from flask import Flask


def setup_logging(app: Flask) -> None:
    """Configure console, app-file and error-file logging."""
    log_level = app.config.get("LOG_LEVEL", "INFO")
    log_file = app.config.get("LOG_FILE", "logs/app.log")
    log_dir = os.path.dirname(log_file) if log_file else "logs"

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    file_format = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)

    error_log = os.path.join(log_dir, "error.log") if log_dir else "error.log"
    error_handler = TimedRotatingFileHandler(
        error_log,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_format)
    root_logger.addHandler(error_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if app.config.get("SQLALCHEMY_ECHO") else logging.ERROR
    )

    app.logger.info("Logging initialized, level: %s", log_level)
