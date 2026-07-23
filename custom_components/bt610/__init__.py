"""The BT610 integration.

NOTE (Task 3 addition, not in the Task 3 brief's file list): the brief's
tests/test_config_flow.py patches `custom_components.bt610.async_setup_entry`
via unittest.mock.patch, which requires the attribute to already exist on the
module (patch() without create=True raises AttributeError otherwise). __init__.py
was an empty scaffold file from Task 1. Adding this minimal stub is the smallest
change that makes the brief's verbatim tests importable/patchable; Task 4 owns
the real runtime implementation and is expected to replace this body.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BT610 from a config entry (stub; full wiring lands in Task 4)."""
    return True
