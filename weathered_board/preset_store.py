"""Where saved presets live on disk, and reading and writing them.

Each saved preset is one small JSON file (``<name>.json``) in the
extension's own user folder, which Blender keeps when the extension is
updated. The built-in presets are in core/presets.py and are never
written to disk.
"""

import os

import bpy

from .core.presets import BUILTIN_PRESETS, PresetError, from_json, to_json

# Tests point this at a temporary folder; None = the extension's user folder.
folder_override: str | None = None

_BAD_CHARS = '<>:"/\\|?*'


def folder() -> str:
    """The folder saved presets live in, created if it doesn't exist yet.

    Normally ``<Blender user folder>/extensions/.user/<repo>/weathered_board/presets``.
    When the add-on isn't running as an installed extension (for example
    loaded from a script), Blender's ``scripts/presets/weathered_board``
    is used instead.
    """
    if folder_override is not None:
        os.makedirs(folder_override, exist_ok=True)
        return folder_override
    try:
        return bpy.utils.extension_path_user(__package__, path="presets", create=True)
    except (ValueError, AttributeError):
        return bpy.utils.user_resource(
            "SCRIPTS", path=os.path.join("presets", "weathered_board"), create=True)


def clean_name(name: str) -> str:
    """A preset name with characters that can't go in a file name removed."""
    return "".join(c for c in name if c not in _BAD_CHARS and c >= " ").strip().strip(".")


def is_builtin(name: str) -> bool:
    """Whether ``name`` is one of the built-in presets (case-insensitive)."""
    return name.casefold() in {p.name.casefold() for p in BUILTIN_PRESETS}


def path_for(name: str) -> str:
    """The file a saved preset called ``name`` is stored in."""
    return os.path.join(folder(), clean_name(name) + ".json")


def saved_names() -> list[str]:
    """Names of all saved presets, in alphabetical order."""
    try:
        files = os.listdir(folder())
    except OSError:
        return []
    names = [f[:-5] for f in files if f.lower().endswith(".json")]
    return sorted(names, key=str.casefold)


def save(name: str, values) -> str:
    """Write a preset file; returns its path. Replaces one of the same name."""
    path = path_for(name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_json(values))
    return path


def load(name: str) -> dict:
    """Read a saved preset's values. Raises PresetError if it can't."""
    try:
        with open(path_for(name), encoding="utf-8") as fh:
            return from_json(fh.read())
    except OSError as err:
        raise PresetError(f"Can't read preset '{name}': {err.strerror}.") from None


def remove(name: str) -> None:
    """Delete a saved preset's file."""
    os.remove(path_for(name))
