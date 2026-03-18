"""Abstract base class for all blockchain collectors."""
import logging
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    chain: str  # e.g. "ETH"
    native_symbol: str  # e.g. "ETH"

    @abstractmethod
    async def poll(self, db: AsyncSession) -> None:
        """
        Fetch latest transactions from the blockchain and persist whale transactions.
        Must be safe to call repeatedly — uses chain_cursors for incremental polling.
        """
        ...

    def log_poll_start(self) -> None:
        logger.debug("[%s] Starting poll", self.chain)

    def log_poll_done(self, saved: int, scanned: int) -> None:
        logger.info("[%s] Poll done: %d/%d whale transactions saved", self.chain, saved, scanned)
