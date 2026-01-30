"""Composed instructions for the unified agent."""

from .core import CORE_INSTRUCTIONS
from .shopping import SHOPPING_INSTRUCTIONS
from .travel import TRAVEL_INSTRUCTIONS


def get_full_instructions() -> str:
    """Return the full instruction string for the main agent (core + shopping + travel)."""
    return CORE_INSTRUCTIONS + SHOPPING_INSTRUCTIONS + TRAVEL_INSTRUCTIONS
