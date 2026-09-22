# Loopjacking interactive explainer

This is a dependency-free, product-neutral attack explainer for GitHub Pages. The
production artifact is the contents of this directory.

To preview locally:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory site
```

Open http://127.0.0.1:4173/ through the server. The walkthrough uses a native
JavaScript module, so opening the HTML directly with `file://` is not supported.

Run the local teaching-model, color-token, reading, link, font, and figure-export
regression tests from the repository root with `node --test site-tests/*.test.mjs`.
These test the website, not any product vulnerability. The reading tests inspect
static source and execute the print/copy handlers with small DOM stubs; they do not
replace browser checks. Local-link tests also check filename casing for Linux
hosting. They do not fetch external links. There is no payment integration,
analytics, or backend.

The walkthrough compares approved and current actions. It assumes an approval
that is still valid, unused, and in the correct workflow; it does not implement
expiry, revocation, replay prevention, or a production authorization policy.

The three typefaces are bundled in `fonts/`, with their complete license notices
and source hashes. The page does not need a Google Fonts connection. Font tests
check the local files, face declarations, and notices; browser tests are still
needed to verify rendering. See `fonts/README.md` before updating those assets.

Without JavaScript, both mechanism explanations, the complete walkthrough, and a
short recap remain readable. JavaScript adds the comparison controls and quiz.
Print styles include both mechanisms and the reading walkthrough. Paginated print
output still needs review on the browser and paper size used for distribution.

The evidence section identifies the linked paper by its title, author, and stated
month. The reading tests pin the PDF bytes paired with that inspected citation.
Before replacing `loopjacking-paper.pdf`, review its title page and the displayed
citation, then update the test pin. This checks file identity, not scientific
correctness or publication status.

`loopjacking-explained.svg` is a self-contained downloadable figure;
`loopjacking-explained.png` is its 1200×630 raster export. Their fictional-amount
and authority-boundary captions must remain attached when reused. The footer also
offers a definition that copies with its authority qualification. Optional export
instructions are in `site-tools/README.md` at the repository root. The renderer is
not needed to view, test, or publish the site.

The public domain is `loopjacking.com`. Canonical and social-preview metadata use
that domain and the existing figure. The metadata tests check these references;
they do not test DNS, certificates, or a social platform's rendering.

## Publish an update

Commit the website changes to `main`, then run **Publish Loopjacking site** from
GitHub Actions. Publishing is manual. The workflow checks the JavaScript and runs
the site tests before uploading only this directory to GitHub Pages. The research
archive elsewhere in the repository is not part of the website deployment.

GitHub Pages uses **GitHub Actions** as its source. Its custom-domain setting is
`loopjacking.com`; DNS is managed separately in Cloudflare. Keep HTTPS enforcement
enabled once GitHub has issued the domain certificate. With an Actions deployment,
the custom domain is configured in Pages settings rather than a `CNAME` file.
