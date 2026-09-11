"""
tree.py
-------
Converts the video_resources JSON tree into two structures used by the resolver.

Supported JSON format
---------------------
Flat array — no server wrapper, cameras and folders at any depth:
  [
    { "name": "CAM_ROOT_1", "type": "camera", "ip": "192.168.1.1" },
    { "name": "FolderName", "type": "folder", "children": [ ... ] }
  ]

  flatten_tree()     → flat list of every FlatCamera across the whole tree
  build_node_index() → mapping of folder name → cameras in its subtree
  build_ip_index()   → mapping of ip → FlatCamera for direct IP lookup
"""

from __future__ import annotations

from .models import FlatCamera

# ── Internal helpers ──────────────────────────────────────────────────────────


def _walk(
    node: dict,
    path: list[str],
    out: list[FlatCamera],
) -> None:
    """Recursively collect FlatCamera objects from a node's children."""
    for child in node.get("children") or []:
        if child["type"] == "camera":
            out.append(
                FlatCamera(
                    path=list(path),
                    camera_name=child["name"],
                    ip=child.get("ip", ""),
                )
            )
        elif child["type"] == "folder":
            _walk(child, path + [child["name"]], out)


def flatten_tree(resources: list[dict]) -> list[FlatCamera]:
    """
    Return every camera in the tree as a flat list of FlatCamera.

    Root-level cameras are included with path=[].
    Root-level folders are recursed into with the folder name as the
    first path segment.
    """
    flat: list[FlatCamera] = []
    for node in resources:
        if node["type"] == "camera":
            flat.append(
                FlatCamera(
                    path=[],
                    camera_name=node["name"],
                    ip=node.get("ip", ""),
                )
            )
        elif node["type"] == "folder":
            _walk(node, [node["name"]], flat)
    return flat


def _index_node(
    node: dict,
    path: list[str],
    index: dict[str, list[FlatCamera]],
) -> list[FlatCamera]:
    """
    Walk node, populate index[folder_name] with all cameras under it,
    and return the full camera list for the caller to accumulate upward.
    """
    local: list[FlatCamera] = []
    for child in node.get("children") or []:
        if child["type"] == "camera":
            local.append(
                FlatCamera(
                    path=list(path),
                    camera_name=child["name"],
                    ip=child.get("ip", ""),
                )
            )
        elif child["type"] == "folder":
            child_path = path + [child["name"]]
            child_cams = _index_node(child, child_path, index)
            index.setdefault(child["name"], []).extend(child_cams)
            local.extend(child_cams)
    return local


def build_node_index(resources: list[dict]) -> dict[str, list[FlatCamera]]:
    """
    Return a dict mapping every folder name to all FlatCameras that live
    inside that folder's subtree.

    Root-level cameras have no parent folder and are matched directly by
    camera name or IP in the resolver.

    Used by the resolver to scope matches: querying "HQ_Security_Block"
    returns every camera nested anywhere beneath that folder.
    """
    index: dict[str, list[FlatCamera]] = {}
    for node in resources:
        if node["type"] == "folder":
            folder_cams = _index_node(node, [node["name"]], index)
            index.setdefault(node["name"], []).extend(folder_cams)
        # root-level cameras are matched by camera name / IP in the resolver
    return index


def build_ip_index(resources: list[dict]) -> dict[str, FlatCamera]:
    """
    Return a dict mapping each camera's IP address to its FlatCamera.

    Cameras without an IP (empty string) are skipped.
    Used by the resolver for direct O(1) IP-based lookup when the user
    query contains an IP address literal.
    """
    return {cam.ip: cam for cam in flatten_tree(resources) if cam.ip}
