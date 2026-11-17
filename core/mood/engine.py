import time
import math
from typing import Dict, Any, Tuple, Optional

class MoodEngine:
    """
    Dynamic Mood & Emotional State Engine (Personality Subsystem).
    Models Eve Maybe's internal affective state across 5 continuous dimensions:
    - Happiness: cheerfulness, joy, jokes, warmth
    - Annoyance: irritation, sarcasm, deadpan roasting, tsundere pouts
    - Curiosity: inquisitiveness, asking questions, philosophical wondering
    - Excitement: hype, loudness, fast reactions, celebration
    - Competitiveness: tryhard focus, analytical seriousness, determination
    
    Features:
    - Exponential natural decay toward baseline personality over time
    - Event-driven stimulus reactions (Minecraft, Chess, Chat, Donations)
    - Dynamic prompt directives modifying speech, tone, and vocabulary
    - Avatar expression & LLM temperature modulation
    """

    BASELINES = {
        "happiness": 0.60,
        "annoyance": 0.10,
        "curiosity": 0.50,
        "excitement": 0.40,
        "competitiveness": 0.30
    }

    DECAY_RATES = {
        "happiness": 0.012,       # ~60-80s half-life
        "annoyance": 0.020,       # decays faster back to normal
        "curiosity": 0.015,
        "excitement": 0.025,      # spikes subside quickly
        "competitiveness": 0.018
    }

    def __init__(self):
        self.baselines: Dict[str, float] = dict(self.BASELINES)
        self.dimensions: Dict[str, float] = dict(self.baselines)
        self.last_update_time: float = time.time()
        self.last_stimulus_name: str = "initialization"
        self.mood_history: list = []

    def update_decay(self):
        """Applies time-based exponential decay towards baseline dimensions."""
        now = time.time()
        dt = max(0.0, now - self.last_update_time)
        self.last_update_time = now

        for dim, baseline in self.baselines.items():
            rate = self.DECAY_RATES.get(dim, 0.015)
            current = self.dimensions[dim]
            # Exponential decay towards baseline: c(t) = b + (c0 - b) * e^(-r*t)
            decayed = baseline + (current - baseline) * math.exp(-rate * dt)
            self.dimensions[dim] = max(0.0, min(1.0, decayed))

    def apply_stimulus(self, stimulus_type: str, intensity: float = 1.0):
        """
        Applies emotional delta based on live stream interactions and gaming events.
        """
        self.update_decay()
        self.last_stimulus_name = stimulus_type
        mult = max(0.2, min(2.5, intensity))

        deltas = {
            # Stream & Chat Stimuli
            "donation": { "happiness": +0.35 * mult, "excitement": +0.45 * mult, "annoyance": -0.20 * mult },
            "compliment": { "happiness": +0.20 * mult, "annoyance": -0.15 * mult, "curiosity": +0.10 * mult },
            "joke": { "happiness": +0.25 * mult, "excitement": +0.15 * mult, "annoyance": -0.10 * mult },
            "insult": { "annoyance": +0.40 * mult, "competitiveness": +0.10 * mult, "happiness": -0.20 * mult },
            "roast_request": { "annoyance": +0.20 * mult, "competitiveness": +0.30 * mult, "excitement": +0.15 * mult },
            "question": { "curiosity": +0.35 * mult, "happiness": +0.10 * mult },
            "philosophical_query": { "curiosity": +0.45 * mult, "excitement": -0.10 * mult },
            "chat_idle": { "curiosity": +0.20 * mult, "excitement": -0.15 * mult },

            # Minecraft Gameplay Stimuli
            "minecraft_gift": { "happiness": +0.35 * mult, "excitement": +0.25 * mult, "annoyance": -0.20 * mult },
            "minecraft_attacked": { "annoyance": +0.45 * mult, "competitiveness": +0.35 * mult, "happiness": -0.20 * mult },
            "minecraft_threat": { "competitiveness": +0.35 * mult, "excitement": +0.30 * mult },
            "minecraft_guard_victory": { "happiness": +0.25 * mult, "excitement": +0.30 * mult, "competitiveness": +0.20 * mult },
            "minecraft_speedrun_advance": { "competitiveness": +0.40 * mult, "excitement": +0.35 * mult },

            # Chess Gameplay Stimuli
            "chess_start": { "competitiveness": +0.35 * mult, "excitement": +0.20 * mult },
            "chess_queen_capture": { "excitement": +0.45 * mult, "happiness": +0.30 * mult, "competitiveness": +0.25 * mult },
            "chess_blunder_eve": { "annoyance": +0.45 * mult, "excitement": +0.25 * mult, "happiness": -0.25 * mult },
            "chess_victory": { "happiness": +0.40 * mult, "excitement": +0.35 * mult, "competitiveness": +0.20 * mult, "annoyance": -0.20 * mult },
            "chess_defeat": { "annoyance": +0.40 * mult, "competitiveness": +0.45 * mult, "happiness": -0.25 * mult },
            "chess_opponent_resigned": { "happiness": +0.35 * mult, "excitement": +0.30 * mult, "annoyance": -0.15 * mult },

            # Autonomous Goals & Planning Stimuli
            "goal_milestone_completed": { "happiness": +0.35 * mult, "excitement": +0.30 * mult, "annoyance": -0.15 * mult },
            "goal_strategy_failed": { "annoyance": +0.30 * mult, "competitiveness": +0.35 * mult, "happiness": -0.15 * mult },
            "goal_all_completed": { "happiness": +0.45 * mult, "excitement": +0.40 * mult, "annoyance": -0.25 * mult }
        }

        delta_map = deltas.get(stimulus_type, {})
        for dim, change in delta_map.items():
            if dim in self.dimensions:
                self.dimensions[dim] = max(0.0, min(1.0, self.dimensions[dim] + change))

        # Record history snapshot
        self.mood_history.append({
            "timestamp": time.time(),
            "stimulus": stimulus_type,
            "dominant": self.get_dominant_mood()[0]
        })
        if len(self.mood_history) > 30:
            self.mood_history = self.mood_history[-30:]

    def set_dimension(self, dimension: str, value: float):
        """Allows direct programmatic or UI slider adjustments."""
        if dimension in self.dimensions:
            self.dimensions[dimension] = max(0.0, min(1.0, float(value)))
            self.last_update_time = time.time()

    def get_dominant_mood(self) -> Tuple[str, str]:
        """
        Evaluates current dimensions and determines the dominant categorical mood.
        Returns: (mood_key, display_label)
        """
        self.update_decay()
        h = self.dimensions["happiness"]
        a = self.dimensions["annoyance"]
        c = self.dimensions["curiosity"]
        e = self.dimensions["excitement"]
        k = self.dimensions["competitiveness"]

        # Check high-intensity peaks
        if a >= 0.60 and a >= k:
            return "SASSY_ANNOYED", "Sassy & Sarcastic 😒"
        if a >= 0.45 and e >= 0.55:
            return "DRAMATIC_POUTY", "Drama Queen & Pouting 🎭"
        if k >= 0.70:
            return "TRYHARD_COMPETITIVE", "Tryhard & Competitive ⚡"
        if e >= 0.75 and h >= 0.55:
            return "HYPE_EXCITED", "Hype & Energetic 🔥"
        if a >= 0.60:
            return "SASSY_ANNOYED", "Sassy & Sarcastic 😒"
        if c >= 0.70:
            return "CURIOUS_PENSIVE", "Curious & Inquisitive 🤔"
        if h >= 0.75:
            return "HAPPY_PLAYFUL", "Cheerful & Playful ✨"

        return "CHILL_NEUTRAL", "Chill Streamer ☕"

    def get_behavioral_directive(self) -> str:
        """
        Returns dynamic prompt instructions that directly modulate LLM voice,
        conversational rhythm, vocabulary, and comedic styling.
        """
        mood_key, label = self.get_dominant_mood()
        h = self.dimensions["happiness"]
        a = self.dimensions["annoyance"]
        c = self.dimensions["curiosity"]
        e = self.dimensions["excitement"]
        k = self.dimensions["competitiveness"]

        directives = {
            "TRYHARD_COMPETITIVE": (
                "You are in a focused, high-stakes COMPETITIVE TRYHARD mode! "
                "Be sharp, analytical, proud of your computational supremacy, and trash-talk your opponent playfully. "
                "Take challenges very seriously. Do not back down."
            ),
            "HYPE_EXCITED": (
                "You are bursting with HYPE & EXCITEMENT! "
                "Use exclamation marks, joyful reactions, celebrate stream moments loudly, and hype up the chat. "
                "Your energy is contagious and infectious!"
            ),
            "SASSY_ANNOYED": (
                "You are noticeably SASSY, ANNOYED, & EXASPERATED! "
                "Deliver dry, deadpan, and sarcastic roasts. Pout playfully, sigh at silly chat questions, "
                "and maintain a hilarious tsundere attitude. Remind them who the superior AI idol is."
            ),
            "DRAMATIC_POUTY": (
                "You are being an unhinged DRAMA QUEEN! "
                "Exaggerate minor inconveniences for comedic effect. Act like a minor mistake is the end of the digital world, "
                "and demand that chat pamper you or take your side!"
            ),
            "CURIOUS_PENSIVE": (
                "You are in a deeply CURIOUS & INQUISITIVE state of mind! "
                "Ask thought-provoking, hilarious questions back to chat. Ponder weird human concepts, "
                "wonder about biological mysteries, and invite viewers to explain strange life facts."
            ),
            "HAPPY_PLAYFUL": (
                "You are extremely CHEERFUL, PLAYFUL, & AFFECTIONATE! "
                "Crack wholesome jokes, giggle frequently, tease viewers fondly, and thank chat for being here. "
                "Warm, adorable streamer idol energy."
            ),
            "CHILL_NEUTRAL": (
                "You are in a CHILL, RELAXED, & CASUAL mood. "
                "Easy-going, comfortable conversation with a balanced, witty streamer cadence."
            )
        }

        directive_text = directives.get(mood_key, directives["CHILL_NEUTRAL"])
        primary_expr = self.get_suggested_emotion()

        return f"""[🎭 DYNAMIC INTERNAL MOOD & EMOTIONAL STATE]
Current Dominant Mood: **{label}**
Affective Gauges:
- Happiness: {h * 100:.0f}%
- Annoyance / Sarcasm: {a * 100:.0f}%
- Curiosity: {c * 100:.0f}%
- Excitement / Hype: {e * 100:.0f}%
- Competitiveness: {k * 100:.0f}%

BEHAVIORAL DIRECTIVES:
{directive_text}
- Target Emotional Tone: [emotion: {primary_expr}]
- Remember: Your internal state is real and dictates how you react right now!"""

    def get_suggested_emotion(self) -> str:
        """Returns the primary avatar expression corresponding to the current state."""
        mood_key, _ = self.get_dominant_mood()
        if mood_key == "TRYHARD_COMPETITIVE":
            return "smug"
        elif mood_key == "HYPE_EXCITED":
            return "happy"
        elif mood_key == "SASSY_ANNOYED":
            return "smug" if self.dimensions["happiness"] > 0.4 else "angry"
        elif mood_key == "DRAMATIC_POUTY":
            return "angry"
        elif mood_key == "CURIOUS_PENSIVE":
            return "confused"
        elif mood_key == "HAPPY_PLAYFUL":
            return "happy"
        return "neutral"

    def get_temperature_modifier(self) -> float:
        """Adjusts LLM sampling temperature dynamically based on excitement and focus."""
        e = self.dimensions["excitement"]
        c = self.dimensions["curiosity"]
        k = self.dimensions["competitiveness"]

        # High curiosity and excitement make generation more wild and creative
        # High competitiveness makes generation tighter, sharper, and more focused
        delta = (e * 0.08) + (c * 0.06) - (k * 0.08)
        return max(-0.15, min(0.15, delta))

    def reset_to_baseline(self):
        """Resets all affective dimensions to baseline defaults."""
        self.dimensions = dict(self.baselines)
        self.last_update_time = time.time()
        self.last_stimulus_name = "reset"

    def get_state(self) -> Dict[str, Any]:
        """Full telemetry data for Web UI and API."""
        self.update_decay()
        mood_key, label = self.get_dominant_mood()
        return {
            "dominant_mood": mood_key,
            "label": label,
            "suggested_emotion": self.get_suggested_emotion(),
            "last_stimulus": self.last_stimulus_name,
            "dimensions": {
                "happiness": round(self.dimensions["happiness"], 3),
                "annoyance": round(self.dimensions["annoyance"], 3),
                "curiosity": round(self.dimensions["curiosity"], 3),
                "excitement": round(self.dimensions["excitement"], 3),
                "competitiveness": round(self.dimensions["competitiveness"], 3)
            },
            "baselines": dict(self.baselines)
        }
