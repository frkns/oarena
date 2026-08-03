# Vendored FCode 2.2 Square visualiser

This directory is an isolated copy of the visualiser shipped in the FCode 2.2.0
wheel. It is intended to be served as a static directory under any URL prefix.
The oarena server rewrites the uncached entry document to a content-fingerprinted
asset prefix, so subsequent replay iframes reuse the runtime and sprites.

Inventory:

- `index.html`: upstream document with only prefix-relative entry paths and the
  Square-only shim added.
- `assets/app-ngkJrQ_K.js`: byte-for-byte upstream application/runtime chunk.
- `assets/main-square.js`: formatted upstream `main-Og2XCMt5.js`, renamed and
  narrowly adapted for the current FCode replay schema: global ammunition,
  current action updates and targets, roster/statistics, range rules, 50 ms TLE
  fallback, and metadata-backed game constants. The upstream Square scene,
  playback model, controls, graphs, inspector, and layout remain in place.
- `assets/app-mehzAGkK.css`: upstream stylesheet with only the font URL made
  prefix-relative.
- `fonts/HKGrotesk-Regular.otf`: byte-for-byte upstream font.
- 57 top-level PNG/JPG files: the current FCode Square textures used by the
  viewer. No Iso/dimetric or obsolete 2.2-mechanic assets are included.
- `square-only.js`: keeps sprite requests under the served URL prefix, supplies
  recorded/live FCode metadata, and exposes the small same-origin replay/theme/
  visibility bridge used by oarena's persistent iframe.

The fork has one Square renderer and one current replay timeline. The inherited
header, Iso and grid controls, Share dialog, dither/visibility sections, hidden
duplicate responsive sidebars, and DOM-rewriting observer were removed at
source. Cambridge's cached grid renderer remains always on. Legacy metadata
warnings live in oarena's game report rather than being injected into this DOM.

Upstream source:
`fcode/data/visualiser/` from the `fcode==2.2.0` CPython 3.12 Linux wheel.
