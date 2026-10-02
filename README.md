# Weathered Board

A Blender 4.2+ add-on that generates wooden boards with realistic weathering, for 3D printing (resin first) and import into FreeCAD.

- Full-size board dimensions, reduced by a scale such as 1:48
- Curving grain ridges on the long faces, evenly spaced semicircles on the ends
- Weathering only on the faces you pick, carved inward so the board never exceeds its size
- Separate rounding on each of the 12 edges
- A new pattern every time; any board can be rebuilt from its seed

The full design is in [docs/DESIGN.md](docs/DESIGN.md).

**Status:** all seven build steps are done. The add-on builds boards with a separate rounding on each of the 12 edges and carves weathering into the chosen faces: curving grain on the long faces, semicircles on the ends, knots, cracks and patchy wear. Presets (Barn Siding, Dock Plank, Fence Board, or your own) set a whole look in one click. Check Printability lists any printing problems in the panel, and Export STL writes one file or one per board.

## Repository layout

```
weathered-board/
├── weathered_board/          The add-on (this folder is what gets zipped)
│   ├── blender_manifest.toml Extension metadata (id, version, Blender 4.2+)
│   ├── __init__.py           register() / unregister()
│   ├── properties.py         Settings stored on the scene and on each board
│   ├── operators.py          Add, Regenerate, New Seed, Set Edges, Presets, Check, Export STL
│   ├── preset_store.py       Saved presets on disk (JSON files)
│   ├── ui_panel.py           3D Viewport sidebar panel
│   ├── mesh_io.py            numpy arrays -> Blender mesh
│   └── core/                 Pure numpy, never imports bpy
│       ├── params.py         Settings, faces, edges, validation
│       ├── geometry.py       Router-shaped board with 12 edge radii
│       ├── grain.py          Long-face ring field (the virtual log)
│       ├── ends.py           End semicircles
│       ├── features.py       Knots, checks (cracks), patchy wear
│       ├── patterns.py       All fields per vertex + colour preview
│       ├── rng.py            Separate seeded random stream per part
│       ├── weather.py        Carving: ridges, recession, fold repair
│       ├── printcheck.py     Printability checks on the built board
│       ├── presets.py        Built-in presets, preset files, settings -> params
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

The panel is in the 3D Viewport sidebar (press N), on the **Weathered Board** tab. Boards can also be added with Shift+A > Mesh > Weathered Board. Turn on *Show Grain Pattern* to see the ring patterns as colour; it switches the viewport to Solid shading with attribute colours.

## Presets

The **Presets** menu at the top of the panel sets a whole look at once:

- **Barn Siding** — rough 1×12, 10 ft: deep crisp grain, lots of checks, knots, hard-worn ends.
- **Dock Plank** — 2×6, 12 ft: rolling grain, well-rounded top edges, eroded end grain.
- **Fence Board** — 5/8 in cedar picket, 6 ft: fine tight grain, near-square edges, light wear.

With boards selected, the preset restyles all of them; with nothing selected, it sets up the next board you add. Presets never change the scale, printer or seed. Turn off **Presets Set Size** (at the bottom of the menu) to take only the look and keep your own length, width and thickness.

Click **+** next to the menu to save the current settings as your own preset; it then appears in the menu under the built-ins. *Remove Saved Preset* in the same menu deletes one. Saved presets are small JSON files in the extension's user folder, so they survive updating the add-on.

## Building and installing

```bash
blender --command extension validate weathered_board
blender --command extension build --source-dir weathered_board --output-dir dist
```

This writes `dist/weathered_board-<version>.zip`. Install it with *Edit > Preferences > Get Extensions > Install from Disk* (drop-down arrow at the top right). Both commands are also VS Code tasks. Bump `version` in `blender_manifest.toml` for each release.

## Using boards in FreeCAD

Turning a mesh into a FreeCAD solid makes every triangle a face, and a full-detail 8 ft board at 1:48 has about 370,000 triangles, which takes a very long time. Before exporting for FreeCAD, turn on **Simplify Mesh** in the panel's *Printing* section:

- **Max Triangles** 20,000 (the default) keeps every point within about 0.009 mm of the full mesh; 10,000 stays within 0.015 mm and converts faster. Either is well below what a printer shows.
- The full-detail mesh stays underneath, so you can turn Simplify off again at any time without rebuilding.

Then *Export STL* (files are in millimetres).

### Import and convert to a solid

1. In FreeCAD, *File > Import* the STL. It arrives as a mesh. If you only need to place the board in a model, you can stop here.
2. Switch to the **Part** workbench, select the mesh and choose *Part > Create shape from mesh*, with a sewing tolerance of 0.01 mm or less.
3. Select the new shape and choose *Part > Convert to solid*.

### Make it a Body

1. Switch to the **Part Design** workbench.
2. Select the solid from step 3 and click **Create body**. The solid becomes the Body's *BaseFeature*, so PartDesign features (pockets, holes, pads) can be added on top. If the Body comes out empty, drag the solid onto the Body in the tree instead.
3. **Hide the earlier objects.** The imported mesh and the shape from mesh are still in the document, at the same position, and still visible. Select them in the tree and press **Space**. Otherwise they fill any hole you cut, so you see the hole's outline but can't see through it (the exported STL is fine either way). Keep the solid: the Body is built from it.

### Drill holes

The weathered faces are made of thousands of small triangles, so don't sketch on them. Even the flat bottom stays in many pieces (Refine shape doesn't merge them, because the bottom's edges ease off slightly where they meet the weathered sides). Sketch on the Body's base planes instead. The board's origin is at its centre: X runs along the length, Y across the width and Z through the thickness.

1. Create a sketch on the **XY plane** and draw the hole circles.
2. Use **Pocket** with *Type* set to *Through all* (or a distance), and tick **Symmetric to plane**. The sketch sits in the middle of the board, so the pocket cuts both ways.

For a hole from one face only, move the sketch to that face: in the sketch's *Attachment Offset*, set *Position z* to plus or minus half the printed thickness. For example, a 1.5 in board at 1:48 is 0.794 mm thick, so −0.397 mm puts the sketch on the bottom.

## Workflow

- Keep `docs/DESIGN.md` current: change it in the same commit as any code that changes the design.
- `core/` must never import `bpy`, so its tests run with plain Python.
- Every module, class and function gets a docstring with a one-line summary (PEP 257); `tests/test_docstrings.py` checks. Operator docstrings double as their buttons' tooltips in Blender, and every setting needs a `description=`, which is its tooltip.
- Run `python -m pytest` before each commit.
