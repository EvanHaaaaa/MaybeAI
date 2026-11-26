"""Highlight Auto-Marker, Vertical Clip Pipeline, and VOD Summarizer."""

from core.highlights.detector import HighlightDetector, HighlightMarker
from core.highlights.clipper import ClipPipeline
from core.highlights.vod_summarizer import VODSummarizer

__all__ = [
    "HighlightDetector",
    "HighlightMarker",
    "ClipPipeline",
    "VODSummarizer",
]
