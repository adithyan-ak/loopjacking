# Bundled fonts

The site serves Chakra Petch, IBM Plex Sans, and JetBrains Mono from this directory.
The typefaces, requested weights, Unicode ranges, and `font-display: swap` setting
are retained from the captured Google Fonts stylesheet. Font files have not been
converted or subsetted here.

`manifest.json` records the source URLs, retrieval time, request user agent, file
sizes, and SHA-256 hashes. The 28 WOFF2 files total 323,112 bytes; that is the full
bundle size, not a measured page-load transfer. The browser can request subsets
according to the text and styles it renders.

Each family remains under its own SIL Open Font License 1.1 notice:

- [Chakra Petch](./chakra-petch-OFL.txt)
- [IBM Plex Sans](./ibm-plex-sans-OFL.txt), including the Reserved Font Name “Plex”
- [JetBrains Mono](./jetbrains-mono-OFL.txt)

Keep these complete notices with the font files. The website's code license does
not replace them. A font update needs a new source/provenance review, an updated
manifest, the site tests, and browser checks of typography and responsive layout.

All runtime font references are relative to `fonts.css`; no font service is
contacted by this stylesheet. System-font fallbacks remain in `styles.css` for
cases where webfonts cannot load.
