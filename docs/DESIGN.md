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
| `checks` | 0–1 | 0.3 | Amount of cracks: straight splits along the fibres on weathered long faces, radial cracks on the ends |
| `patchiness` | 0–1 | 0.5 | How unevenly the depth varies across a face |
| `printer` | `FDM` or `resin` | `resin` | Sets `min_feature` and `resolution` defaults |
| `min_feature` | printed mm | 0.1 (resin), 0.4 (FDM) | Smallest ridge spacing the printer can hold; the add-on warns below it |
| `detail_boost` | float ≥ 1 | 1 | Exaggerates ring spacing and carving depth for small scales where true detail would be too fine to print |
| `auto_detail` | bool | on | Raises the boost as needed so the finest rings print at least 4 vertices and 2 smallest-features wide; `detail_boost` then acts as a minimum |
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
|  geometry.py   router-shaped box: 12 edge radii, normals     |
|       |                         |                            |
|  grain.py  long faces      ends.py  end semicircles  <-- rng.py streams + noise.py
|       |                         |                            |
|  features.py   knots, checks, patchy wear                    |
|  patterns.py   all fields per vertex + colour preview        |
|       |                                                      |
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

The panel also has:

- **Live Update** (on by default) — changing a selected board's setting rebuilds it automatically. Changes are queued and the board rebuilds once they pause for 0.35 s, so dragging a slider rebuilds a few times rather than on every step.
- **Show Grain Pattern** — colours the board by its ring pattern in the viewport: light earlywood, dark latewood, grey on faces that won't be weathered. The colours are stored as a colour attribute (`WB_Pattern`) and blend across rounded edges by face weight, exactly as the carving will.
- **Printed size and vertex count**, worked out from the settings before anything is built, with a warning when the mesh would be too heavy.
- Any build error, shown on the board's panel (live updates have no other way to report one).

Boards can also be added from the 3D Viewport's *Add > Mesh* menu (Shift+A).

## Base mesh with rounded edges

The board is shaped the way a router shapes one: every edge is rounded along its full length with its own radius, and where edges meet at a corner their roundings simply intersect. Each edge is therefore an exact quarter-circle along its whole length, and changing one edge's radius changes nothing else.

### Edge radii

Each edge's slider (0–1) is a fraction of the largest radius that edge can take: half the smaller of the two dimensions across its cross-section. For a long edge on a 1.5 × 3.5 in board, 1 means a 0.75 in radius, which fully rounds that side. Because every radius is at most half of each neighbouring dimension, two edges on the same face can never overlap.

### The shape

The board is the intersection of three extruded 2D rounded rectangles, one per cross-section, each with its own radius in each of its four corners:

| Cross-section | Edges it rounds (they run along) |
| --- | --- |
| Y–Z | the 4 long edges (X) |
| X–Z | `a_top`, `a_bottom`, `b_top`, `b_bottom` (Y) |
| X–Y | `a_front`, `a_back`, `b_front`, `b_back` (Z) |

Each cross-section has an exact signed distance, and the board's is the largest of the three (negative inside). With q = |p| − h + r in the section's two axes and r that quadrant's radius:

```latex
d_{\text{section}}(p) = \lVert \max(q, 0) \rVert + \min(\max(q_u, q_v), 0) - r, \qquad d(p) = \max(d_{YZ}, d_{XZ}, d_{XY})
```

The board is convex, which the mesher relies on.

### Building the mesh

1. Convert the 12 sliders to radii in full-size units.
2. Lay a grid of points on each flat face of the box. Spacing = `resolution` × scale, so density matches what the print can show. Each axis has one shared list of grid coordinates, refined inside each rounding band so every rounded edge gets at least 8 segments.
3. Merge the duplicate points along the 12 seams. They coincide exactly because every face uses the same axis coordinates, giving one closed surface.
4. Leave points on the flat parts where they are. Move every other point inward along the ray toward c, the point clamped to the inner box shrunk by each face's widest radius, until it reaches the surface (bisection on d). Every c is inside the board, so each ray crosses the surface exactly once.
5. Store per vertex: position, normal and six face weights.

Because the rays converge on points inside a convex shape, neighbouring grid points land next to each other and no triangle can face inward. A 96 in 1×6 at 1:48 builds in about half a second (185,000 vertices); 1:12 takes about 7 seconds (2.3 million). The builder refuses more than 4 million vertices and asks for a coarser resolution.

### Corners

Where radii meet at a corner, their roundings cross along a crease, exactly as on a routed board. With three equal radii each corner keeps (2 − √2) r³ of its r³ cube, one eighth of a Steinmetz tricylinder; the tests check the volume against this. A first version blended the radii into a smooth corner instead. When neighbouring radii differed much, it pushed the larger radius along the smaller edges and left visible waists and lumps, so it was dropped. Creases are a fraction of a millimetre at print scale, and later weathering softens them further.

### Normals and face weights

Flat-face vertices take their face's axis as normal. On a sharp edge or corner (radius 0) a vertex belongs fully to every face it touches, with the sum of those axes as normal. Rounded vertices take the mesh's own area-weighted normal.

Face weights say how much each vertex belongs to each face: 1 on a flat face, sliding smoothly from one face to the next across a rounded edge (squared normal components). Weathering is multiplied by these weights, so an unselected face stays perfectly flat and the change happens over the rounded edge rather than as a step.

## Weathering: long-face ridges and end semicircles

Every weathering value is a function of the vertex's 3D position, never of a face's own 2D coordinates. That is what keeps the mesh watertight: a vertex shared by two faces gets one answer.

### The virtual log

Each board gets a hidden pith line (the centre of the tree) running roughly along X:

- It sits outside the board, 0.3–3 board widths beyond the edge of the cross-section. In 70% of boards it is behind the top or bottom face (within ±20°), as in flat-sawn lumber, which gives cathedral arches on that face. The rest point any direction, giving straight or quarter-sawn grain.
- It tilts by up to about 2° from the X axis, so rings run out of the long faces at a slant, as they do in real boards.
- It wobbles gently along its length (about every 400 mm, by up to 0.15 board widths × `grain_waviness`).

For each vertex, R is its distance from the pith line, bent by smooth 3D noise so rings are not perfect circles. The ring phase is then:

```latex
\phi = \operatorname{frac}\big(N(R + w\,\mathrm{fbm}(p))\big), \qquad N(R) = n_0 + \int_0^R \frac{dr}{s(r)}
```

N(R) counts the rings from the pith out to R, and n₀ is a random offset. The ring width s(r) varies smoothly within the `ring_spacing` range, changing about every five rings, so some years are wide and some narrow; N is tabulated once per board and interpolated. The bending amplitude is w = 2 × mean spacing × `grain_waviness`, with noise features about 300 mm long and 25 mm across (two octaves), so grain lines wander along the board without turning ragged.

On the long faces, lines of equal R form long, curving, nested arches (cathedral grain) on the face nearest the pith and near-parallel wavy lines on the faces beside it. This field is used only for the four long faces.

### End faces: stylized semicircles

Each end gets its own simple pattern instead of true growth rings: evenly spaced semicircles centred on one edge of that end face.

1. Pick the centre edge from `end_center` (with `random`, each end draws its own: top or bottom 40% each, front or back 10% each, so the arcs usually span the width). Pick a point along that edge, within the middle 50% of it, so the two ends of one board differ.
2. For a vertex on the end, d = its 2D distance from the centre point within the end's plane.
3. Ring phase φ = frac(d / `end_spacing` + ½ `end_wobble` × noise), so wobble 1 shifts rings by up to half a ring. With wobble 0 the rings are perfect, evenly spaced semicircles.
4. The same ridge profile E(φ) as the long faces turns rings into raised ridges between carved grooves, so the style matches.

Arcs larger than the face are simply cut off by the face border, so a centre on the bottom edge shows full half-rings near it and partial arcs toward the top corners. The end pattern and the long-face grain do not line up at the edge between them; the edge rounding and `edge_margin` soften that meeting.

### Turning rings into ridges

In weathered wood the soft earlywood wears away and the hard latewood stands up as ridges. So the erosion profile E(φ) is 0 on the latewood ridge (φ = 0.88, the same band the colour preview shows dark) and rises to 1 deepest in the earlywood. The ridge's sides rise over a half-width hw = 0.5 − 0.44 × `ridge_sharpness` of a ring, as a half cosine; 20% of the depth curves the valley floor too, so valleys are scooped rather than flat. Sharpness 0 gives rolling waves; sharpness 1 gives narrow ridges between wide valleys. E is periodic, so there is no seam between one year and the next.

**Fine rings and coarse meshes.** A ridge wall that falls on too few mesh vertices carves as a jagged staircase wherever rings cross the grid at an angle, as the end semicircles always do. So:

- Where a ridge wall would get fewer than 4 vertices, the ridge is widened just enough to get 4.
- Where a whole ring gets fewer than 4 vertices, the carving fades, reaching zero at 2. The ridges stay on the original surface either way, so the board keeps its size.
- **Auto Detail Boost** (on by default) avoids both. It multiplies ring spacing and depth by the smallest factor that makes the finest rings print at least 4 vertices and 2 smallest-features wide. A 1×6 at 1:48 on a resin printer gets 3.2×: rings print 0.2 mm apart, where true scale would be 0.06 mm. The boosted depth is still capped at a quarter of the thickness.

### Extra features

All three live in `core/features.py`, each with its own random stream.

- **Knots** (`knots`: a min–max count per board). Each knot is a branch leaving the pith line at a random point along the middle 80% of the board. It is aimed through a point inside the board, tilted slightly along it as branches grow, so it always crosses the board and shows as an oval where it meets a face. Its radius is 4–12% of the board width, never under 4 mesh vertices.
  - The distance from the pith is pushed out near the branch (by up to 1.2 knot radii, fading over 2.5 radii), so the grain flows around the knot.
  - The knot's core resists wear (85% less erosion) and stands proud of the worn wood around it, as knots do on old boards.
  - Knots affect the long faces only.
- **Checks** (`checks`: 0–1). Narrow cracks, a quarter of a ring spacing wide (never under 4 mesh vertices).
  - **Long faces:** about 6 per metre of board at `checks` = 1, placed only on long faces that are being weathered, more often on wider faces. They split along the fibres, as surface checks do: nearly straight lines along the board with a slight wander (two gentle waves, under 4% of the width), 15–50% of the board long, thinning to both tips. They cut across the curving ridges, which is what makes them read as cracks.
  - **Ends:** about 4 per end at `checks` = 1. Each runs straight out from the ring centre, starting shallow and opening deepest toward the outside, as end checks do.
  - Checks cut 1.6 times the face's depth, up to 35% of the thickness (more than the 25% cap on wear). They are narrow, so even checks on opposite faces leave 30% of the wood between them.
- **Patchy wear** (`patchiness`: 0–1). A smooth noise map, with features about 300 mm along the board and half the width across, scales the depth. Sheltered areas wear as little as 1 − `patchiness` of full depth. It scales the smooth recession as well as the ridges, so it is fold-safe.

### Combining into a displacement

Each selected face f asks for a full depth Dn_f (its boosted depth, eased near borders as below) and a carved depth D_f = Dn_f · E(φ_f), where φ_f is the virtual log for long faces and the semicircles for ends. A vertex blends its faces by face weight into one Dn and one D. Every term depends only on the vertex's position, so a vertex shared by faces gets one answer and the mesh stays watertight.

The carving is then applied in two parts, each of which cannot fold the mesh:

1. **Recession.** The whole surface sinks by the smooth depth Dn. Each vertex p moves toward its own point c inside the board: p clamped to an inner box shrunk by at least three times the deepest cut (and by the rounding bands). It moves Dn along its dominant axis and proportionally along the others:

   ```latex
   p' = p - D_n \, \frac{p - c}{\max_k |p_k - c_k|}
   ```

   On a flat face this is a straight cut of depth Dn. Near an edge p − c tilts toward the edge, so the faces and the edge recede together: grooves run out over the edge, with no raised lip. Each vertex moves along its own ray toward c, by less than its distance from c.

2. **Ridges.** The latewood is built back up by Dn − D along the surface normal, like raising a height map. The normals used are eased across corner creases (12 smoothing passes on rounded vertices), because raising ridges along sharply diverging normals at a crease would pull neighbours apart. Any ridge that would poke past the original surface is shortened.

**Where depths meet.** Where a weathered face meets an unweathered one, or a shallower one (a long face beside an end with its own depth), the deeper face eases down to its neighbour's depth before their shared edge. It eases over three times the difference, so the depth never changes faster than 1 mm per 3 mm. The edge rounding can be a fraction of a millimetre wide, too narrow for the change.

**Repair.** A final pass checks every triangle against its uncarved orientation. Where one has turned over, the ridge height at its corners is halved, repeatedly. If that is not enough, the whole carving there is eased back. The uncarved board never folds, so this always ends clean. It touches at most about 0.5% of vertices, at corners with extreme settings, and none in typical boards.

The reported depth is the cut measured straight into the faces (the largest move along any one axis). At an edge the corner also recedes diagonally, as a box shrunk evenly on every face does.

Patchy wear scales both Dn_f and D_f. A knot's core scales down the erosion E on the long faces. A check sets D_f to at least its crack depth, which can be deeper than Dn_f: the "ridge" step then moves those vertices further in along the normal rather than out.

## Inset, randomization and blending

### Staying inside the original size

The weathering is inset in two ways:

- **Inward only.** D is never negative, so every vertex moves into the board. The highest ridges sit exactly on the original surface and everything else is cut below it. A 1.5 × 3.5 × 96 in board still measures 1.5 × 3.5 × 96 in across its ridge tops, which matters when boards must fit a model.
- **Optional border.** With `edge_margin` > 0, the depth fades to zero at each face's border over `edge_margin` (or over three times the depth, if that is wider, to keep the fade gentle), leaving a smooth frame of original surface around the weathered area.

Safety limits: `depth` (after the detail boost) is capped at a quarter of the thickness, so opposite faces can never meet. Folding is prevented by the two-part carving and the repair pass above. Tests confirm every vertex lies inside the original bounding box.

### Randomization

Each part of the board (grain, ends, knots, checks, patch map) draws from its own `numpy` generator, spawned from the board's seed (`core/rng.py`). Nothing else draws random numbers. Because the streams are separate, changing one part's settings never reshuffles another: a new end spacing leaves the grain exactly as it was. New streams are only ever appended to the list, so existing seeds keep their boards. Per board the streams choose:

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
- **Printable detail:** the printed ridge spacing (`ring_spacing` and `end_spacing` ÷ scale × boost) is at least `min_feature`; if not, it suggests a `detail_boost` value that would fix it. (With Auto Detail Boost on this always holds; the panel already shows the printed ring spacing and cut depth.)
- **Wall thickness:** the thinnest point between opposite faces after carving stays above 2 × `min_feature`.
- **Flat base:** notes whether the bottom is left unweathered, which prints best without supports.
- **Size:** the triangle count, with a warning above about 2 million, which some slicers handle slowly.

### Tests

- [x] Watertight: every output mesh is manifold with consistent normals.
- [x] No folds: no carved triangle turns over, for any rounding and face selection.
- [x] Envelope: no vertex outside the original box, for many random seeds.
- [x] Unselected faces: vertices with full weight on an unselected face do not move.
- [ ] Repeatable: same seed and settings give identical meshes; different seeds differ.
- [x] Per-edge rounding: each of the 12 sliders sets only its own edge's radius; mixed radii at a corner leave no gaps or folded triangles.
- [ ] End pattern: ring spacing measured on the end equals `end_spacing` with wobble 0.
- [x] Scale: printed size equals full size / N within 0.1%.
- [ ] Core tests run with plain Python (no Blender); add-on tests run with `blender --background --python`.

### Build plan

1. **Rounded box.** Done: router-style board with 12 edge radii, normals and face weights; 42 geometry tests.
2. **Blender shell.** Done: manifest, properties, sidebar panel, Add (also in Shift+A), Regenerate, New Seed, edge-group buttons, Export STL, live update, printed size and vertex estimate, error display.
3. **Patterns.** Done: vectorized Perlin noise, virtual log for long faces, stylized semicircles for ends, separate random streams, colour preview in the viewport; 71 pattern tests.
4. **Carving.** Done: erosion profile with scooped valleys, face selection, two-part fold-safe carving, easing between faces of different depth, auto detail boost, ring anti-aliasing, panel feedback on ring size and cut; 27 carving tests.
5. **Character.** Done: knots (grain bends around them, hard cores stand proud), checks (straight splits along the fibres on long faces, radial cracks on ends, cutting deeper than the wear), patchy wear, separate end depth (step 4); 25 feature tests.
6. **Printing.** Printability checks, STL export, FDM and resin defaults; test prints at 1:24, 1:48 and 1:87.
7. **Presets.** Common looks (barn siding, dock plank, fence board) saved as Blender operator presets.

### Decisions

- Built as a Blender add-on for Blender 4.2 or newer, installed as an extension. No support for older versions.
- Main use is 3D printing: watertight STL in millimetres, printability checks, bottom left flat by default.
- Resin is the primary printer: defaults are `printer` = resin, `resolution` = 0.05 mm and `min_feature` = 0.1 mm. FDM stays available as a setting.
- End pattern is evenly spaced, stylized semicircles.
- Each of the 12 edges has its own rounding value, with group buttons to set several at once.
- The design lives in this file (`docs/DESIGN.md`) under version control; update it in the same commit as any change that alters the design.
