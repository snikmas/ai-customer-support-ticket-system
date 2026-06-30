# logging setup
from src.core.config import LOG_LEVEL
import logging

def setup_logging() -> None:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

