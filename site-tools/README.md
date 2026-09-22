# Figure export

The SVG in `site/` is the editable source. The PNG is its opaque, full-size export
for readers who need a raster image. Both retain the fictional-amount and attacker
authority qualifications. Do not crop those qualifications off when reusing it.

This authoring tool is optional; neither the site nor its tests need Sharp. From
the repository root, install the pinned renderer in a separate temporary directory:

```sh
figure_tools="$(mktemp -d)"
npm install --prefix "$figure_tools" --no-save --package-lock=false sharp@0.35.4
LOOPJACKING_SHARP_MODULE="$figure_tools/node_modules/sharp" node site-tools/export-figure.mjs
node --test site-tests/*.test.mjs
```

If Sharp 0.35.4 is already installed, point `LOOPJACKING_SHARP_MODULE` at that
module instead. The script uses paths relative to itself, not the shell's working
directory. It replaces only the PNG and `figure-export.json`.

Inspect the full export and a 390px-wide preview after changing the SVG. Check the
amounts, recipient labels, approval arrow, attacker boundary, and fictional-example
caption. A centered 2:1 crop is an additional local stress check, not a promise
about any social platform's crop behavior.

Commit the SVG, PNG, and generated `figure-export.json` together. The record binds
the exact source and output bytes; a regression test rejects stale or unrecorded
edits. This is not proof of pixel equivalence: fonts and rasterization can differ
across systems even with the same Sharp version. Reinspect every regenerated image.

Social-preview metadata in `site/index.html` uses `https://loopjacking.com/` and
this PNG. Nothing in this tool publishes or uploads files.
