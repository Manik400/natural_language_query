from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MatchType = Literal["token", "ip", ""]


@dataclass
class FlatCamera:
    path: list[str]  # folder names from root down to (but not including) camera
    camera_name: str  # camera node name
    ip: str = ""  # IP address of the camera node

    # --- match metadata ---
    match_type: MatchType = ""  # "token" | "ip" | ""
    matched_token: str = ""  # the normalised token that triggered the match
    matched_raw_slice: str = ""  # verbatim slice of the user query that matched
    confidence: float = 100.0

    @property
    def key(self) -> tuple:
        return (tuple(self.path), self.camera_name)

    def full_path(self) -> str:
        return " → ".join(self.path + [self.camera_name])

    def to_dict(self) -> dict:
        return {
            "full_path": self.full_path(),
            "folder_path": self.path,
            "camera_name": self.camera_name,
            "ip": self.ip,
            "match_type": self.match_type,
            "matched_token": self.matched_token,
            "matched_raw_slice": self.matched_raw_slice,
            "confidence": self.confidence,
        }
