# Weathered Board Generator — Design

Sep 30, 2026 · John

## Overview

The tool is a Blender add-on that adds a weathered board object to the scene, ready to export as STL for 3D printing (and for import into FreeCAD). It builds a closed mesh of a board with a separate rounding value on each of its 12 edges, then carves weathering into chosen faces by pushing vertices inward.

Two patterns drive the weathering. The long faces use a hidden "virtual log" of growth rings, which gives natural curving ridges. The ends use evenly spaced, stylized semicircles centred on one edge of each end.

Goals:

- Board of any full-size dimensions, reduced by a user-given scale (e.g. 1:48).
- Weathering only on the faces the user picks.
- Long faces: curving ridges along the grain. Ends: evenly spaced semicircular ridges.
- Weathering carved inward only, so the board never exceeds its original size.
- A new pattern every run; the same seed reproduces a board exactly.
- A rounding value for each of the 12 edges, from sharp to fully rounded.
- A watertight, printable mesh with detail no finer than the printer can resolve.

## User inputs and parameters

All settings live in the add-on's panel in the 3D Viewport sidebar (N panel, "Weathered Board" tab) and are stored on the board object, so a board can be regenerated or tweaked later. Weathering sizes are given in full-size units, so a preset looks the same at any scale; the board is built at full size and shrunk by the scale as the last step.

Coordinate convention: X = length, Y = width, Z = thickness, origin at the board's centre. The six faces are `top` (+Z), `bottom` (−Z), `front` (−Y), `back` (+Y), `end_a` (−X) and `end_b` (+X). The first four are the long faces.

Each of the 12 edges is named by the two faces it joins:

- **Long edges (4):** `top_front`, `top_back`, `bottom_front`, `bottom_back`.
- **End A edges (4):** `a_top`, `a_bottom`, `a_front`, `a_back`.
- **End B edges (4):** `b_top`, `b_bottom`, `b_front`, `b_back`.

| Parameter | Type / units | Default | Meaning |
| --- | --- | --- | --- |
| `length`, `width`, `thickness` | float, full-size | required | Actual board size (a nominal 2×4 is 1.5 × 3.5 in) |
| `units` | `in` or `mm` | `in` | Units of the full-size inputs |
| `scale` | `1:N` | `1:1` | Reduction ratio, e.g. `1:48`, `1:87` |
| `faces` | six checkboxes | all except `bottom` | Faces to weather; a flat bottom sits cleanly on the print bed |
| `edge_round_<edge>` | 0–1, one per edge | 0.15 | Rounding of that edge as a fraction of the most it can take; 0 = sharp, 1 = fully rounded |
| `edge_round_all`, `_long`, `_end_a`, `_end_b` | 0–1 | — | Buttons that set a group of edges at once; each edge can then be adjusted |
| `depth` | full-size length | 3 mm | Deepest weathering cut |
| `edge_margin` | full-size length | 0 | Band along each face border where weathering fades to zero |
| `ring_spacing` | full-size length, range | 3–6 mm | Distance between growth rings on the long faces |
| `ridge_sharpness` | 0–1 | 0.6 | 0 = soft rolling waves, 1 = crisp ridges with steep valleys |
| `grain_waviness` | 0–1 | 0.4 | How much the long-face grain lines wander |
| `end_spacing` | full-size length | 4 mm | Even distance between the semicircles on the ends |
| `end_center` | `random`, `top`, `bottom`, `front`, `back` | `random` | Which edge of each end the semicircles are centred on |
| `end_wobble` | 0–1 | 0.1 | Slight hand-made unevenness in the arcs; 0 = perfect circles |
| `end_depth` | full-size length or unset | same as `depth` | Separate depth for the end pattern |
| `knots` | int or range | 0–2 | Number of knots on the long faces |
| `checks` | 0–1 | 0.3 | Amount of long cracks along the grain and radial cracks on the ends |
| `patchiness` | 0–1 | 0.5 | How unevenly the depth varies across a face |
| `printer` | `FDM` or `resin` | `resin` | Sets `min_feature` and `resolution` defaults |
| `min_feature` | printed mm | 0.1 (resin), 0.4 (FDM) | Smallest ridge spacing the printer can hold; the add-on warns below it |
| `detail_boost` | float ≥ 1 | 1 | Exaggerates spacing and depth for small scales where true detail would be too fine to print |
| `resolution` | printed mm | 0.05 (resin), 0.1 (FDM) | Target spacing between vertices in the final mesh |
| `seed` | int | random | Stored on the object; a "New seed" button rolls a fresh board |
| `count` | int | 1 | Number of boards to add, laid out side by side |

The panel rejects impossible values, such as a `depth` greater than a quarter of the thickness or an `edge_margin` wider than half a face. The same settings can be driven from a Python script through the operator, for batch work.

## Architecture

The add-on is packaged as a Blender 4.2+ extension (`blender_manifest.toml`), installed from a zip. It uses only what ships with Blender: `bpy`, `bmesh` and `numpy`. The geometry lives in a `core/` package that never imports `bpy`, so it can be unit-tested with plain Python and stays fast because every step works on whole numpy arrays.

```
ui_panel.py   Sidebar panel (settings stored on the object via properties.py)
     |
operators.py  Add / Regenerate / New Seed / Check / Export
     |
+--- core/  (pure numpy, no bpy) ------------------------------+
|  geometry.py   rounded box: 12 edge radii, normals, weights  |
|       |                         |                            |
|  grain.py  long faces      ends.py  end semicircles  <-- seeded RNG + noise.py
|       |                         |                            |
|  weather.py    carve: erosion, knots, checks; inward only    |
+--------------------------------------------------------------+
     |
mesh_io.py    shrink by scale, write Blender mesh, print checks
     |
Export STL    Blender's built-in STL exporter
```

The panel only collects settings; the operator hands them to the core as plain values and gets back vertex and triangle arrays. `mesh_io.py` loads those into a Blender mesh with `foreach_set` (far faster than `from_pydata` for dense meshes). Randomness enters only inside the core, from one seeded source, so any board can be rebuilt from its stored seed.

Operators on the panel:

- **Add Weathered Board** — creates a new board object from the current settings.
- **Regenerate** — rebuilds the selected board's mesh after settings change, keeping its seed.
- **New Seed** — rolls a new seed and regenerates, for a different board of the same size.
- **Check Printability** — runs the checks in the output section and reports problems.
- **Export STL** — exports the selected boards in millimetres.

## Base mesh with rounded edges

The base mesh is a dense grid on each of the six box faces, pulled onto a rounded box whose 12 edges each have their own radius. This gives even triangles everywhere and one rule for every edge, from sharp to fully round.

### Edge radii

Each edge's slider (0–1) is a fraction of the largest radius that edge can take: half the smaller of the two faces it joins. For a long edge on a 1.5 × 3.5 in board, 1 means a 0.75 in radius, which fully rounds that side. Because every radius is at most half of each neighbouring dimension, two edges on the same face can never overlap.

### Building the mesh

1. Convert the 12 sliders to radii in full-size units.
2. Lay a grid of points on each flat face. Spacing = `resolution` × scale, so density matches what the print can show. Add extra grid lines inside each rounding band so every rounded edge gets at least 8 segments.
3. Map each point onto the rounded surface (below).
4. Triangulate each grid and merge the duplicate points along the 12 seams, giving one closed surface.
5. Store per vertex: position, exact surface normal, and six face weights.

### The mapping

For each point p, three insets a = (a_x, a_y, a_z) say how far each axis is rounded at that spot. Near a long edge, a_y and a_z both equal that edge's radius; near an end edge parallel to Y, a_x and a_z equal its radius; and so on. The point is clamped to the inner box shrunk by a, then pushed back out along an ellipsoid with semi-axes a:

```latex
c = \operatorname{clamp}(p,\; -h + a,\; h - a), \qquad u = \frac{A^{-1}(p - c)}{\lVert A^{-1}(p - c) \rVert}, \qquad p' = c + A\,u, \qquad A = \operatorname{diag}(a)
```

The normal is A⁻¹u, normalized. On a flat region p = c, so nothing moves. Along the middle of an edge, the two insets are equal and the edge is an exact quarter-circle.

### Corners where different radii meet

At each of the 8 corners three edges meet, and they may disagree: the long edge wants a_y = 0.2 in while the end edge beside it wants a_y = 0.5 in. Each inset therefore blends, along the edge, from the edge's own radius to the corner value (the largest of the radii meeting there), using a smoothstep over a distance equal to that corner value. The edge stays a true circle for most of its length and becomes slightly elliptical just before the corner, which closes the corner smoothly with no gaps or creases.

### Face weights

Face weights say how much each vertex belongs to each face: 1 on a flat face, sliding smoothly from one face to the next across a rounded edge (squared normal components). Weathering is multiplied by these weights, so an unselected face stays perfectly flat and the change happens over the rounded edge rather than as a step. On a sharp edge (radius 0) a seam vertex has weight 1 for both faces.

## Weathering: long-face ridges and end semicircles

Every weathering value is a function of the vertex's 3D position, never of a face's own 2D coordinates. That is what keeps the mesh watertight: a vertex shared by two faces gets one answer.

### The virtual log

Each board gets a hidden pith line (the centre of the tree) running roughly along X:

- It sits outside the board's cross-section, 0.3–3 board widths away, in a random direction. Close and centred behind a face gives strong cathedral arches on that face; far away gives straighter grain.
- It tilts by up to about 2° from the X axis, so rings run out of the long faces at a slant, as they do in real boards.
- It wobbles gently along its length, driven by low-frequency noise scaled by `grain_waviness`.

For each vertex, R is its distance from the pith line, bent by smooth 3D noise so rings are not perfect circles. The ring phase is then:

```latex
\phi = \operatorname{frac}\!\left(\frac{R + w\,\mathrm{fbm}(p)}{s(R)}\right)
```

s(R) is the local ring spacing, varied slowly within the `ring_spacing` range so some years are wide and some narrow, and w is the waviness amplitude.

On the long faces, lines of equal R form long, curving, nested arches (cathedral grain) on the face nearest the pith and near-parallel wavy lines on the faces beside it. This field is used only for the four long faces.

### End faces: stylized semicircles

Each end gets its own simple pattern instead of true growth rings: evenly spaced semicircles centred on one edge of that end face.

1. Pick the centre edge from `end_center` (with `random`, each end draws its own, weighted toward the long `top`/`bottom` edges so the arcs span the width). Pick a point along that edge, within the middle 50% of it, so the two ends of one board differ.
2. For a vertex on the end, d = its 2D distance from the centre point within the end's plane.
3. Ring phase φ = frac(d / `end_spacing` + `end_wobble` × small noise). With wobble 0 the rings are perfect, evenly spaced semicircles.
4. The same ridge profile E(φ) as the long faces turns rings into raised ridges between carved grooves, so the style matches.

Arcs larger than the face are simply cut off by the face border, so a centre on the bottom edge shows full half-rings near it and partial arcs toward the top corners. The end pattern and the long-face grain do not line up at the edge between them; the edge rounding and `edge_margin` soften that meeting.

### Turning rings into ridges

In weathered wood the soft earlywood wears away and the hard latewood stands up as ridges. So the erosion profile E(φ) is high across most of each ring and drops to zero at a narrow latewood band near φ = 1. `ridge_sharpness` narrows that band and steepens its sides: low values give rolling waves, high values give crisp ridges between scooped valleys.

### Extra features

- **Knots:** each knot is a short branch axis leaving the pith line. Near it, R is bent so rings flow around the knot, and the knot core gets low erosion so it stands proud, as knots do on old boards.
- **Checks:** a few narrow, deep cracks. On long faces they follow a single ring line for a random stretch and taper at both ends. On ends they run straight outward from the semicircle centre, crossing the rings. Amount set by `checks`.
- **Patchiness:** a low-frequency noise map multiplies the depth, so some areas are deeply worn and others barely touched.

### Combining into a displacement

```latex
D_f(p) = \text{depth}_f \cdot \text{patch}(p) \cdot \max\!\big(E(\phi_f(p)),\, \text{check}_f(p)\big)\cdot \text{taper}(p), \qquad v = -\sum_{f} s_f\, w_f(p)\, D_f(p)\, n_f
```

φ_f is the ring phase for face f: the virtual log for long faces, the semicircles for ends. s_f is 1 for a selected face and 0 otherwise, w_f the face weight and n_f the face's outward axis. Every term depends only on the vertex's position, so a vertex shared by two faces gets one answer and the mesh stays watertight. On a rounded edge the two faces' patterns blend; on a sharp edge a seam vertex is pushed in from both sides.

## Inset, randomization and blending

### Staying inside the original size

The weathering is inset in two ways:

- **Inward only.** D is never negative, so every vertex moves into the board. The highest ridges sit exactly on the original surface and everything else is cut below it. A 1.5 × 3.5 × 96 in board still measures 1.5 × 3.5 × 96 in across its ridge tops, which matters when boards must fit a model.
- **Optional border.** With `edge_margin` > 0, a taper fades the depth to zero over that distance from each face's border, leaving a smooth frame of original surface around the weathered area.

Safety limits: `depth` is capped at a quarter of the thickness so opposite faces can never meet, and within the rounded edges the depth is capped at 0.8 r so the curve can't fold over itself. A final check confirms every vertex lies inside the original bounding box.

### Randomization

One `numpy.random.Generator` is created from the seed and passed to every step, so nothing else draws random numbers. Per board it chooses:

| What varies | Range |
| --- | --- |
| Pith distance and direction | 0.3–3 widths; any angle outside the cross-section |
| Pith tilt and wobble | 0–2°; wobble scaled by `grain_waviness` |
| Ring spacing per year | within `ring_spacing` |
| Noise offsets | a random offset into each noise field |
| Knots | count, position, size, branch angle |
| Checks | count, position, length, depth |
| Patch map | a random offset into the patch noise |
| End semicircle centre | which edge (if random) and a point in its middle 50%, per end |

The seed is stored on the board object along with every other setting, so Regenerate always rebuilds the same board and New Seed gives a fresh one. With `count` > 1, board i uses seed + i.

### Noise

Smooth 3D noise (fractal value or simplex noise, 3–5 octaves) is written in numpy inside the core and evaluated on all vertices at once. Blender's own `mathutils.noise` is not used because it works one point at a time, which is far too slow for meshes of several hundred thousand vertices.

## Output for 3D printing, testing and build plan

### Output for printing

After carving, the mesh is multiplied by 1/scale and written to the board object in millimetres, with the scene set to metric, millimetre units so the slicer reads the size correctly. Export STL uses Blender's built-in exporter on the selected boards, one file per board or all in one.

Check Printability runs before export and reports, per board:

- **Watertight:** no open edges or non-manifold vertices (via `bmesh`).
- **No self-intersections:** carving never folds the surface over itself.
- **Printable detail:** the printed ridge spacing (`ring_spacing` and `end_spacing` ÷ scale × `detail_boost`) is at least `min_feature`; if not, it suggests a `detail_boost` value that would fix it.
- **Wall thickness:** the thinnest point between opposite faces after carving stays above 2 × `min_feature`.
- **Flat base:** notes whether the bottom is left unweathered, which prints best without supports.
- **Size:** the triangle count, with a warning above about 2 million, which some slicers handle slowly.

### Tests

- [ ] Watertight: every output mesh is manifold with consistent normals.
- [ ] Envelope: no vertex outside the original box, for many random seeds.
- [ ] Unselected faces: vertices with full weight on an unselected face do not move.
- [ ] Repeatable: same seed and settings give identical meshes; different seeds differ.
- [ ] Per-edge rounding: each of the 12 sliders changes only its own edge; mixed radii at a corner leave no gaps, creases or folded triangles.
- [ ] End pattern: ring spacing measured on the end equals `end_spacing` with wobble 0.
- [ ] Scale: printed size equals full size / N within 0.1%.
- [ ] Core tests run with plain Python (no Blender); add-on tests run with `blender --background --python`.

### Build plan

1. **Rounded box.** Core mesh builder with 12 edge radii, corner blending and face weights; test every rounding combination.
2. **Blender shell.** Extension manifest, properties, panel, Add and Regenerate operators, `foreach_set` mesh loading, so progress can be seen in Blender from step 3 on.
3. **Patterns.** Virtual log for long faces and semicircles for ends; show φ as vertex colour on the uncarved board to tune them before any carving.
4. **Carving.** Erosion profile, face selection, inward-only displacement and limits.
5. **Character.** Knots, checks, patchiness, separate end depth.
6. **Printing.** Printability checks, STL export, FDM and resin defaults; test prints at 1:24, 1:48 and 1:87.
7. **Presets.** Common looks (barn siding, dock plank, fence board) saved as Blender operator presets.

### Decisions

- Built as a Blender add-on for Blender 4.2 or newer, installed as an extension. No support for older versions.
- Main use is 3D printing: watertight STL in millimetres, printability checks, bottom left flat by default.
- Resin is the primary printer: defaults are `printer` = resin, `resolution` = 0.05 mm and `min_feature` = 0.1 mm. FDM stays available as a setting.
- End pattern is evenly spaced, stylized semicircles.
- Each of the 12 edges has its own rounding value, with group buttons to set several at once.
- The design lives in this file (`docs/DESIGN.md`) under version control; update it in the same commit as any change that alters the design.
