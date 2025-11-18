"""
Structured Logging Module

Provides JSON-formatted logging with:
- Request IDs for tracing
- Job IDs for analysis tracking
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Timestamps in ISO format
- OPSEC-safe address sanitization
- Contextual metadata
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

# Context variables for request/job tracking
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
job_id_ctx: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


def sanitize_address(address: str) -> str:
    """
    Sanitize a Solana wallet or token address for logging.
    Shows only first 4 and last 4 characters.
    """
    if not address or len(address) < 12:
        return "****"
    return f"{address[:4]}...{address[-4:]}"


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs JSON-structured logs"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add request_id if set
        request_id = request_id_ctx.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add job_id if set
        job_id = job_id_ctx.get()
        if job_id:
            log_data["job_id"] = job_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                log_data[key] = value

        return json.dumps(log_data)


def setup_logger(name: str = "gun_del_sol", level: int = logging.INFO, json_output: bool = True) -> logging.Logger:
    """
    Setup a structured logger instance

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON-formatted logs; otherwise use text

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers = []

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Set formatter
    if json_output:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Default logger instance
logger = setup_logger()


def set_request_id(request_id: str):
    """Set the request ID for the current context"""
    request_id_ctx.set(request_id)


def set_job_id(job_id: str):
    """Set the job ID for the current context"""
    job_id_ctx.set(job_id)


def clear_context():
    """Clear request and job IDs from context"""
    request_id_ctx.set(None)
    job_id_ctx.set(None)


# Convenience functions for logging
def log_info(message: str, **kwargs):
    """Log info message with optional metadata"""
    logger.info(message, extra=kwargs)


def log_warning(message: str, **kwargs):
    """Log warning message with optional metadata"""
    logger.warning(message, extra=kwargs)


def log_error(message: str, exc_info=None, **kwargs):
    """Log error message with optional metadata"""
    logger.error(message, exc_info=exc_info, extra=kwargs)


def log_debug(message: str, **kwargs):
    """Log debug message with optional metadata"""
    logger.debug(message, extra=kwargs)


# Analysis-specific logging functions
def log_analysis_start(job_id: str, token_address: str):
    """Log analysis job start"""
    set_job_id(job_id)
    log_info("Analysis job started", token_address=sanitize_address(token_address), status="started")


def log_analysis_complete(job_id: str, wallet_count: int, credits_used: int):
    """Log analysis job completion"""
    set_job_id(job_id)
    log_info("Analysis job completed", wallets_found=wallet_count, credits_used=credits_used, status="completed")


def log_analysis_failed(job_id: str, error: str):
    """Log analysis job failure"""
    set_job_id(job_id)
    log_error("Analysis job failed", error=error, status="failed")
