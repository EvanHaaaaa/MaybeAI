from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, Optional


class BasePlatformAdapter(ABC):
    """
    Abstract base class for live chat platform ingestion adapters (YouTube Live, Discord, etc.).
    All adapters push normalized messages into a ChatReceiver (or async callback) and degrade
    gracefully when disabled or unconfigured.
    """

    platform_name: str = "unknown"

    def __init__(
        self,
        receiver: Optional[Any] = None,
        on_message: Optional[Callable[..., Awaitable[Any]]] = None,
        enabled: bool = False,
    ):
        self._receiver = receiver
        self._on_message = on_message
        self.enabled = bool(enabled)
        self.is_running: bool = False
        self.is_connected: bool = False
        self.last_error: Optional[str] = None
        self.messages_received: int = 0

    def set_receiver(self, receiver: Any) -> None:
        self._receiver = receiver

    async def _emit_message(
        self,
        user: str,
        text: str,
        source: Optional[str] = None,
        is_donation: bool = False,
        donation_amount: str = "",
        donation_currency: str = "",
        is_creator: Optional[bool] = None,
    ) -> None:
        if not text or not text.strip():
            return

        msg_source = source or self.platform_name
        self.messages_received += 1

        if self._receiver is not None:
            await self._receiver.put_message(
                user=user,
                text=text.strip(),
                source=msg_source,
                is_donation=is_donation,
                donation_amount=donation_amount,
                donation_currency=donation_currency,
                is_creator=is_creator,
            )
        elif self._on_message is not None:
            await self._on_message(
                user=user,
                text=text.strip(),
                source=msg_source,
                is_donation=is_donation,
                donation_amount=donation_amount,
                donation_currency=donation_currency,
                is_creator=is_creator,
            )

    @abstractmethod
    async def start(self) -> bool:
        """Starts the adapter background polling/listening loop. Returns True if started."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Stops the adapter cleanly and releases network resources."""
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns a JSON-serializable status dictionary for diagnostics and UI."""
        raise NotImplementedError
