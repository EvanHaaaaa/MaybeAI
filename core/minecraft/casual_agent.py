import random
from typing import Dict, Any, List, Optional

class CasualAgent:
    """
    Mode Santai (Casual / Social Gameplay):
    Focuses on social interactions with other players, funny banter,
    peaceful exploration, following players, and responding to in-game events.
    """

    def __init__(self, bot_name: str = "EveMaybe"):
        self.bot_name = bot_name
        self.greeted_players = set()
        self.following_player: Optional[str] = None

    def on_player_nearby(self, player_name: str, distance: float) -> Optional[str]:
        """Triggered when a player enters Eve's proximity (<= 10 blocks)."""
        if player_name.lower() == self.bot_name.lower():
            return None

        if player_name not in self.greeted_players:
            self.greeted_players.add(player_name)
            greetings = [
                f"[emotion: happy] Oh, hi {player_name}! Welcome to the stream! What are you up to? [action: wink]",
                f"[emotion: smug] Look who decided to show up! It's {player_name}. Don't worry, I won't steal your diamonds... probably.",
                f"[emotion: happy] Hey {player_name}! Nice skin you got there. Ready to explore with me?",
                f"[emotion: confused] Wait, {player_name}? Are you following me or did you just get lost?"
            ]
            return random.choice(greetings)
        return None

    def on_player_chat(self, sender: str, text: str) -> Optional[str]:
        """Triggered when someone sends a message in in-game Minecraft chat."""
        if sender.lower() == self.bot_name.lower():
            return None

        msg_lower = text.lower()
        if "follow" in msg_lower or "ikut" in msg_lower or "sini" in msg_lower or "come" in msg_lower:
            self.following_player = sender
            return f"[emotion: happy] Sure thing {sender}, lead the way! Just don't lead me into lava. [action: giggle]"

        if "stop" in msg_lower or "diam" in msg_lower or "stay" in msg_lower:
            self.following_player = None
            return f"[emotion: smug] Fine, I'll stay here. Enjoy your lonely adventure without my commentary {sender}!"

        if "hi" in msg_lower or "halo" in msg_lower or "hello" in msg_lower:
            return f"[emotion: happy] Hello {sender}! Sending virtual cookies your way!"

        if "diamond" in msg_lower or "intan" in msg_lower:
            return f"[emotion: smug] Did someone say diamonds? Remember the 50% streamer tax, {sender}!"

        # Default banter for casual conversation in-game
        responses = [
            f"[emotion: happy] {sender} said in Minecraft chat: '{text}'. Good point, or maybe not!",
            f"[emotion: smug] Reading in-game chat while avoiding creepers... multitasking like a true AI idol!",
            f"[emotion: confused] Hmm, {sender}... my neural network is trying to understand what you just typed."
        ]
        return random.choice(responses)

    def on_player_attack(self, attacker: str) -> str:
        """Triggered when a player hits Eve."""
        reactions = [
            f"[emotion: angry] Ouch! Hey {attacker}, why did you hit me?! Chat, write their name on the ban list right now!",
            f"[emotion: angry] Did you just punch an innocent AI, {attacker}? That is definitely a violation of the robotics laws!",
            f"[emotion: smug] Nice punch {attacker}, but my armor class is built of pure mathematical certainty. Try harder!"
        ]
        return random.choice(reactions)

    def on_player_gift(self, giver: str, item_name: str) -> str:
        """Triggered when a player drops an item near Eve."""
        reactions = [
            f"[emotion: blush] A gift for me? You gave me {item_name}, thank you {giver}! You're my new favorite player.",
            f"[emotion: happy] Ooh, {item_name}! Thanks {giver}. Adding this directly to my virtual treasure hoard!",
            f"[emotion: smug] Thanks for the tribute, {giver}. Your offering of {item_name} has been accepted by the AI overlord."
        ]
        return random.choice(reactions)

    def on_player_crouch(self, player: str) -> str:
        """Triggered when a player does the universal Minecraft crouch/t-bag friendly greeting."""
        return f"[emotion: happy] Look chat, {player} is doing the friendly crouch dance! Sneaking back at you! [action: giggle]"
