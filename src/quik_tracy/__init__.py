import logging

from rich.logging import RichHandler
from rich.traceback import install

install(show_locals=True)

LOG_LEVEL = logging.DEBUG
logging.basicConfig(level=LOG_LEVEL, format="%(message)s", handlers=[RichHandler(rich_tracebacks=True)])
logger = logging.getLogger(__name__)
logger.parent = logging.getLogger("rich")
