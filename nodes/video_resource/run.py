from pathlib import Path
from typing import List

from exceptions import VideoResolutionException
from logger import get_logger, node_name_var

from .constants import MATCH_ORDER
from .models import FlatCamera
from .resolver import resolve_video_resources
from .tree import build_ip_index, build_node_index, flatten_tree

logger = get_logger("video.run")


class VideoResolutionFallbackHandler:
    """Handle failures in video resource resolution with graceful fallbacks."""

    def __init__(self, json_path: str | Path, fuzzy_threshold: int = 75):
        self.json_path = json_path
        self.fuzzy_threshold = fuzzy_threshold
        self.logger = get_logger("video.fallback")
        self._resources = None
        self._flat = None
        self._node_index = None
        self._ip_index = None
        self._load_resources()

    def _load_resources(self):
        """Load and cache resources with error handling."""
        try:
            import json

            print(f"[DEBUG] Reading JSON from: {self.json_path}", flush=True)
            raw = json.loads(Path(self.json_path).read_text())
            print(f"[DEBUG] Raw type: {type(raw)}, length: {len(raw)}", flush=True)

            if isinstance(raw, list):
                self._resources = raw
            elif isinstance(raw, dict) and "video_resources" in raw:
                self._resources = raw["video_resources"]
            else:
                raise ValueError(f"Unrecognised video resources format: {type(raw)}")

            print(f"[DEBUG] Resources count: {len(self._resources)}", flush=True)

            self._flat = flatten_tree(self._resources)
            self._node_index = build_node_index(self._resources)
            self._ip_index = build_ip_index(self._resources)

            print(f"[DEBUG] Flat cameras: {len(self._flat)}", flush=True)

            self.logger.debug(
                "Loaded video resources",
                extra={"cameras": len(self._flat)},
            )
        except Exception as e:
            print(f"[DEBUG] LOAD FAILED: {type(e).__name__}: {e}", flush=True)
            self.logger.error(f"Failed to load video resources: {e}", exc_info=True)
            self._resources = []
            self._flat = []
            self._node_index = {}
            self._ip_index = {}

    def get_default_fallback(self) -> dict:
        """Return default fallback for complete resolution failure."""
        return {
            "groups": [],
            "resolved_cameras": [],
            "error": {
                "type": "resolution_failed",
                "recovered": True,
                "fallback": "no_cameras",
            },
        }

    def _format_results(self, results: List[FlatCamera]) -> dict:
        """Format and sort resolution results."""
        if not results:
            return self.get_default_fallback()

        try:
            grouped: dict[tuple[str, str, float, str], List[FlatCamera]] = {}

            for cam in results:
                key = (
                    cam.matched_token,
                    cam.match_type,
                    cam.confidence,
                    cam.matched_raw_slice,
                )
                grouped.setdefault(key, []).append(cam)

            groups = []

            for (token, mtype, conf, raw_slice), cams in grouped.items():
                groups.append(
                    {
                        "matched_token": token,
                        "matched_raw_slice": raw_slice,
                        "match_type": mtype,
                        "confidence": conf,
                        "cameras": [c.camera_name for c in cams],
                    }
                )

            # Sort by priority
            groups.sort(
                key=lambda g: (
                    MATCH_ORDER.get(g["match_type"], 999),
                    -g["confidence"],
                )
            )

            return {
                "groups": groups,
                "resolved_cameras": [r.camera_name for r in results],
            }

        except Exception as e:
            self.logger.error(
                f"Error formatting results: {e}",
                exc_info=True,
            )
            return self.get_default_fallback()

    def resolve_with_fallback(self, user_text: str) -> dict:
        """
        Resolve video resources with comprehensive error handling.

        Args:
            user_text: User query text

        Returns:
            dict with groups and resolved_cameras (always valid structure)
        """
        node_name_var.set("video_resolution")
        self.logger.info(f"Starting video resolution for text: {user_text[:100]}...")

        if not self._flat or not self._resources:
            self.logger.warning("Video resources not loaded, returning empty")
            return self.get_default_fallback()

        try:
            results = resolve_video_resources(
                user_text=user_text,
                flat=self._flat,
                node_index=self._node_index,
                ip_index=self._ip_index,
                fuzzy_threshold=self.fuzzy_threshold,
            )

            if not results:
                self.logger.debug("No cameras matched in resolution")
                return self.get_default_fallback()

            formatted = self._format_results(results)
            self.logger.info(
                "Video resolution successful",
                extra={"groups": len(formatted.get("groups", []))},
            )
            return formatted

        except Exception as e:
            self.logger.error(
                f"Video resolution failed: {e}",
                exc_info=True,
            )
            return self.get_default_fallback()


def resolve_video_resources_with_error_handling(
    user_text: str,
    json_path: str | Path,
    fuzzy_threshold: int = 75,
) -> dict:
    """
    Public API for video resource resolution with error handling.

    Args:
        user_text: User query text
        json_path: Path to video resources JSON
        fuzzy_threshold: Fuzzy matching threshold

    Returns:
        dict with guaranteed structure (groups and resolved_cameras).
        Each group includes matched_raw_slice for source attribution.
    """
    try:
        handler = VideoResolutionFallbackHandler(json_path, fuzzy_threshold)
        return handler.resolve_with_fallback(user_text)
    except VideoResolutionException as e:
        logger.error(f"Video resolution exception: {e.message}")
        return {"groups": [], "resolved_cameras": [], "error": e.to_dict()}
    except Exception as e:
        logger.error(f"Unexpected error in video resolution: {e}", exc_info=True)
        return {"groups": [], "resolved_cameras": [], "error": {"type": "unknown"}}
