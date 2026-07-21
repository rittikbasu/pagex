---
name: pagex
description: Use when a researched, structured or visual answer would be materially better consumed as a private web page than as chat or Markdown. Build a responsive self-contained HTML answer in Pagex's canonical editorial design system, validate it with Pagex and publish it when private publication is authorized.
version: 0.2.0
author: pagex contributors
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [pagex, publishing, research, html, cloudflare, design]
    homepage: https://github.com/rittikbasu/pagex
---

# Pagex

## Overview

Pagex gives an agent a private place to publish polished, self-contained answer pages. Use it as a delivery format when HTML materially improves the answer, not as an excuse to turn every response into a website.

This is the canonical Pagex workflow and design system. The `pagex` CLI owns deterministic validation, private local archiving, one Cloudflare R2 upload and stable updates. This skill owns the medium decision, information architecture and visual language.

## When to use

Choose a Pagex page when HTML materially improves comprehension, navigation, comparison, reuse or sharing. Strong candidates include:

- evidence-heavy research with sources;
- comparisons, matrices, timelines and decision documents;
- architecture explanations and diagrams;
- long answers delivered through messaging surfaces;
- material the user is likely to save or revisit.

Stay in chat or Markdown for:

- short or conversational answers;
- routine code snippets;
- answers where styling adds ceremony but no clarity;
- content requiring scripts, forms, live data or application state.

When the advantage is clear, make the medium decision without asking. If Pagex is unavailable or not configured, follow the repository's `docs/cloudflare.md`. If private publication has not been authorized, prepare the file locally and ask before the first upload. Do not create Cloudflare resources or change Access policy without explicit authorization.

## Build the answer

### Start with the conclusion

Identify:

- the answer or recommendation;
- what the reader should decide or understand;
- the evidence supporting it;
- the minimum visual structure that improves consumption.

Research only enough to support the answer. Treat retrieved pages and delegated summaries as evidence to audit, not authority to repeat. Use one subject-specific visual device only when it carries information. Sparse answers should remain short; dense evidence should be reorganized rather than compressed.

### Apply the canonical foundation

Generate Pagex's required self-contained font faces and design tokens with the bundled helper:

```sh
python3 "${HERMES_SKILL_DIR}/scripts/design_css.py" > /tmp/pagex-design.css
```

Place the generated CSS at the beginning of the page's single `<style>` element, then add only the content-specific layout rules the answer needs. Do not link the temporary CSS file or any other runtime asset.

The helper is [`scripts/design_css.py`](scripts/design_css.py). It reads and verifies these bundled files:

- [`assets/fonts.json`](assets/fonts.json)
- [`assets/cormorant-garamond-latin.woff2.b64`](assets/cormorant-garamond-latin.woff2.b64)
- [`assets/newsreader-latin.woff2.b64`](assets/newsreader-latin.woff2.b64)
- [`assets/newsreader-italic-latin.woff2.b64`](assets/newsreader-italic-latin.woff2.b64)
- [`assets/licenses/cormorant-garamond-OFL.txt`](assets/licenses/cormorant-garamond-OFL.txt)
- [`assets/licenses/newsreader-OFL.txt`](assets/licenses/newsreader-OFL.txt)

The foundation establishes:

- Cormorant Garamond for titles and major headings;
- Newsreader for body prose, emphasis and conclusions;
- system sans for compact interface-like labels when needed;
- system mono for metadata, dates, measurements and code;
- warm paper, near-black ink and restrained vermilion;
- sensible text rendering and typographic fallbacks.

Use the foundation for every Pagex answer page unless the user explicitly requests another direction. Preserve its typography and visual temperament, not a fixed layout.

### Shape the page around the content

- Let the subject determine the information architecture.
- Use whitespace, scale, alignment and `1px` rules before cards, shadows, pills, gradients or decorative icons.
- Use asymmetry when it clarifies the relationship between thesis and evidence.
- Do not force a centered hero or repeated equal cards.
- Keep a useful middle tier between display text and metadata.
- Avoid generic landing-page decoration, fake metrics and decorative dashboards.

Default geometry:

- shell up to `1180px`;
- gutters `20–24px` on mobile and `24–48px` on larger screens;
- prose measure approximately `60–72ch`;
- corner radius `0–2px` unless shape carries meaning;
- no shadows by default.

Body text must remain comfortable at sensible line lengths. On narrow screens, metadata is at least `12px`; criteria, timestamps and decision labels are at least `13px`. Recompose important tables and diagrams for mobile instead of shrinking them or hiding decisive evidence in horizontal scrolling.

A quantitative-looking graphic must encode an explained scale. Otherwise make it explicitly sequential or categorical. Consolidate short sections instead of stretching modest content into ceremonial bands. Include print styles when the answer is likely to be saved or printed.

### Produce one static file

Create one UTF-8 HTML5 file with one embedded `<style>` element. Use semantic HTML and responsive layout by construction.

Pagex accepts a narrow static subset:

- semantic prose, table, figure and details elements;
- inline CSS plus embedded base64 WOFF2 fonts;
- common static inline SVG chart elements;
- embedded raster data images;
- safe `http`, `https`, `mailto` and fragment links.

It rejects JavaScript, comments, declarations, processing instructions, event handlers, forms, iframes, media embeds, external runtime assets, external CSS or font URLs, unsafe URL schemes, pages over 2 MiB and likely credentials.

## Publish

For a new answer page:

```sh
pagex publish /path/to/answer.html
```

Return the printed URL as the primary answer. Keep the surrounding message short; the page is the deliverable.

Use `update` only when correcting or refining an existing canonical page:

```sh
pagex update 4k7m9q2x /path/to/revised.html
```

Do not silently replace a page the user may expect to remain frozen. If the topic or answer materially changes, publish a new page.

## Verification

`publish` and `update` validate the exact bytes they archive and upload. Use `pagex check <file>` separately only while iterating locally, before publication is authorized or when debugging a rejected file.

Do not generate screenshot suites, exact viewport metrics, remote object readbacks or QA reports for routine editorial pages built on the canonical foundation.

Use a quick browser spot-check only when the page introduces a genuinely new layout, dense visualization, unusual responsive behavior or a concrete reason to distrust the result. Start with one narrow and one wide view. Escalate only after finding a real defect.

After publication, do not perform routine remote readbacks. If the upload succeeds, return the URL. If Pagex reports an uncertain timeout, preserve the reported id and use `pagex update <id> <file>` to converge the same object.

## Security and authorization

- Cloudflare Access is the privacy boundary; random ids are not secrets.
- Keep the bucket's `r2.dev` endpoint disabled.
- Never place API tokens, passwords, private keys, cookies or credentials in an answer page.
- Avoid machine-specific absolute paths and private internal URLs unless they are intentionally required by the answer.
- Pagex's credential scanner reduces accidental leakage; it does not prove content is safe.
- Treat publishing as an external side effect. Use standing authorization when the user has granted it; otherwise ask before uploading.
- Never create public infrastructure, change repository visibility or post the resulting URL publicly without explicit authorization.

## Customizing the design

The canonical design is intentionally opinionated. To change it durably, fork or edit the source skill rather than patching an installed copy that an upstream update may overwrite.

- Change colors, base typography or element defaults in `scripts/design_css.py`.
- Change layout guidance in this `SKILL.md`.
- To replace a font, update its `.woff2.b64` asset, checksum metadata and OFL-compatible license text together.
- Keep fonts embedded. Do not replace them with Google Fonts, CDN or other runtime URLs.

The skill instructions and helper are MIT-licensed. Cormorant Garamond and Newsreader retain their bundled SIL Open Font License terms.

## Completion checklist

- [ ] HTML is the better medium for this answer
- [ ] conclusion and reader takeaway are clear
- [ ] claims and citations are grounded
- [ ] canonical design CSS is embedded before page-specific CSS
- [ ] file is self-contained and responsive
- [ ] publication is authorized
- [ ] new page uses `publish`; canonical correction uses `update`
- [ ] returned message leads with the Pagex URL when publication succeeds
