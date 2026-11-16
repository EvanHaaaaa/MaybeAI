import asyncio
import re
from typing import Optional, Callable, Dict, Any, List

class ChatMessage:
    def __init__(
        self,
        user: str,
        text: str,
        source: str = "web",
        is_donation: bool = False,
        donation_amount: str = "",
        donation_currency: str = ""
    ):
        self.user = user
        self.text = text
        self.source = source
        self.is_donation = is_donation
        self.donation_amount = donation_amount
        self.donation_currency = donation_currency
        self.timestamp = asyncio.get_event_loop().time()

class ChatReceiver:
    """
    Handles live chat ingestion from Twitch IRC or Web UI queue.
    """

    def __init__(self, twitch_channel: Optional[str] = None):
        self.twitch_channel = twitch_channel
        self.queue: asyncio.Queue[ChatMessage] = asyncio.Queue()
        self.is_running = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def put_message(
        self,
        user: str,
        text: str,
        source: str = "web",
        is_donation: bool = False,
        donation_amount: str = "",
        donation_currency: str = ""
    ):
        """
        Push message into the active queue.
        """
        msg = ChatMessage(
            user=user,
            text=text,
            source=source,
            is_donation=is_donation,
            donation_amount=donation_amount,
            donation_currency=donation_currency
        )
        await self.queue.put(msg)

    async def get_next_message(self) -> ChatMessage:
        return await self.queue.get()

    async def start_twitch_listener(self, channel: str, bot_nick: str = "justinfan12345", oauth: str = ""):
        """
        Connects to Twitch IRC anonymously or with OAuth and pushes messages to the queue.
        """
        if not channel:
            return

        self.twitch_channel = channel.lower().lstrip("#")
        self.is_running = True
        print(f"[Twitch] Connecting to IRC for channel: #{self.twitch_channel}...")

        while self.is_running:
            try:
                reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
                self._reader, self._writer = reader, writer

                # Anonymously join or auth
                pass_str = oauth if oauth else "SCHMOOPIIE"
                nick_str = bot_nick if bot_nick else f"justinfan{asyncio.get_event_loop().time():.0f}"

                writer.write(f"PASS {pass_str}\r\n".encode())
                writer.write(f"NICK {nick_str}\r\n".encode())
                writer.write(f"JOIN #{self.twitch_channel}\r\n".encode())
                await writer.drain()

                print(f"[Twitch] Joined #{self.twitch_channel} chat!")

                while self.is_running:
                    line_bytes = await reader.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="ignore").strip()

                    # Handle Ping-Pong
                    if line.startswith("PING"):
                        writer.write(b"PONG :tmi.twitch.tv\r\n")
                        await writer.drain()
                        continue

                    # Parse PRIVMSG
                    match = re.search(r":(\w+)!.*PRIVMSG #\w+ :(.*)", line)
                    if match:
                        user = match.group(1)
                        text = match.group(2)
                        await self.put_message(user=user, text=text, source="twitch")

            except Exception as e:
                print(f"[Twitch] Disconnected ({e}), reconnecting in 5s...")
                await asyncio.sleep(5)

    def stop(self):
        self.is_running = False
        if self._writer:
            self._writer.close()
