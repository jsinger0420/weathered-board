# Weathered Board

A Blender 4.2+ add-on that generates wooden boards with realistic weathering, for 3D printing (resin first) and import into FreeCAD.

- Full-size board dimensions, reduced by a scale such as 1:48
- Curving grain ridges on the long faces, evenly spaced semicircles on the ends
- Weathering only on the faces you pick, carved inward so the board never exceeds its size
- Separate rounding on each of the 12 edges
- A new pattern every time; any board can be rebuilt from its seed

The full design is in [docs/DESIGN.md](docs/DESIGN.md).

**Status:** scaffold. The add-on installs, shows its panel, and adds, regenerates, reseeds and exports boards, but the board is still a plain box. The rounded box and weathering come next, following the build plan in the design doc.

## Repository layout

```
weathered-board/
├── weathered_board/          The add-on (this folder is what gets zipped)
│   ├── blender_manifest.toml Extension metadata (id, version, Blender 4.2+)
│   ├── __init__.py           register() / unregister()
│   ├── properties.py         Settings stored on the scene and on each board
│   ├── operators.py          Add, Regenerate, New Seed, Set Edges, Export STL
│   ├── ui_panel.py           3D Viewport sidebar panel
│   ├── mesh_io.py            numpy arrays -> Blender mesh
│   └── core/                 Pure numpy, never imports bpy
│       ├── params.py         Settings, faces, edges, validation
│       ├── geometry.py       Rounded box (placeholder box for now)
│       ├── grain.py          Long-face ring field
│       ├── ends.py           End semicircles
│       ├── weather.py        Carving
│       └── noise.py          Vectorized fractal noise
├── tests/                    pytest: core tests + Blender smoke tests
├── docs/DESIGN.md            Design document
├── requirements-dev.txt
└── .vscode/                  Recommended extensions, test and build tasks
```

## Setup

```bash
git clone <your-repo-url> weathered-board
cd weathered-board
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

`fake-bpy-module-4.2` only gives VS Code autocomplete for `bpy`. The Blender smoke tests are skipped unless the real `bpy` is importable; to run them outside Blender, `pip install "bpy==4.2.*"` (needs Python 3.11).

Open the folder in VS Code and accept the recommended extensions.

## Developing with Blender

Pick one:

1. **Blender Development extension (VS Code).** Run *Blender: Start* from the command palette to launch Blender with the add-on loaded, then *Blender: Reload Addons* after each change.
2. **Link the folder into Blender.** Make a symbolic link from Blender's extensions folder to `weathered_board/`, then enable it in *Edit > Preferences > Add-ons*. Restart Blender to pick up changes.
   - Windows: `%APPDATA%\Blender Foundation\Blender\4.2\extensions\user_default\weathered_board`
   - macOS: `~/Library/Application Support/Blender/4.2/extensions/user_default/weathered_board`
   - Linux: `~/.config/blender/4.2/extensions/user_default/weathered_board`

The panel is in the 3D Viewport sidebar (press N), on the **Weathered Board** tab.

## Building and installing

```bash
blender --command extension validate weathered_board
blender --command extension build --source-dir weathered_board --output-dir dist
```

This writes `dist/weathered_board-<version>.zip`. Install it with *Edit > Preferences > Get Extensions > Install from Disk* (drop-down arrow at the top right). Both commands are also VS Code tasks. Bump `version` in `blender_manifest.toml` for each release.

## Using boards in FreeCAD

Export STL from the panel's *Printing* section; files are in millimetres. In FreeCAD, *File > Import* the STL (Mesh workbench). To use it in Part or PartDesign, *Part > Create shape from mesh*, then *Part > Convert to solid*. Dense weathered meshes make heavy solids, so keep the mesh as a mesh where you can, or use a coarser resolution for the FreeCAD copy.

## Workflow

- Keep `docs/DESIGN.md` current: change it in the same commit as any code that changes the design.
- `core/` must never import `bpy`, so its tests run with plain Python.
- Run `python -m pytest` before each commit.
