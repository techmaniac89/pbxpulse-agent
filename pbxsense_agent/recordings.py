from __future__ import annotations

from pathlib import Path


_AUDIO_SUFFIXES = {".wav", ".mp3", ".ogg", ".gsm", ".ulaw", ".alaw", ".flac"}


def find_recording(root: str, recording_id: str) -> Path | None:
    """Find an audio file under a configured recording root without exposing paths."""
    if not root or not recording_id:
        return None
    try:
        directory = Path(root)
        if not directory.is_dir():
            return None
        requested = _normalized(recording_id)
        for candidate in directory.rglob("*"):
            if not candidate.is_file() or candidate.suffix.lower() not in _AUDIO_SUFFIXES:
                continue
            if requested in _normalized(candidate.name):
                return candidate
    except OSError:
        return None
    return None


def _normalized(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())
