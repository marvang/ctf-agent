import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)

# Create a logger named after the current module
logger = get_logger(__name__)