---
name: pagex
description: Use when a researched, structured or visual answer would be materially better consumed as a private web page than as chat or Markdown. Build a responsive self-contained HTML answer, validate it with Pagex and publish it when the user has configured Pagex and authorized private publication.
version: 0.1.0
author: pagex contributors
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [pagex, publishing, research, html, cloudflare]
    homepage: https://github.com/rittikbasu/pagex
---

# Pagex

## Overview

Pagex gives an agent a private place to publish polished, self-contained answer pages. Use it as a delivery format, not as an excuse to turn every response into a website.

The agent owns the medium decision and the page. The `pagex` CLI owns deterministic validation, private local archiving, one Cloudflare R2 upload and stable updates.

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
- content requiring scripts, forms, live data, external assets or application state.

When the advantage is clear, make the medium decision without asking. If Pagex is unavailable or not configured, follow the repository's `docs/cloudflare.md`. If private publication has not been authorized, prepare the file locally and ask before the first upload. Do not create Cloudflare resources or change Access policy without explicit authorization.

## Build the answer

### Start with the conclusion

Identify:

- the answer or recommendation;
- what the reader should decide or understand;
- the evidence supporting it;
- the minimum visual structure that improves consumption.

Research only enough to support the answer. Treat retrieved pages and delegated summaries as evidence to audit, not authority to repeat.

### Produce one static file

Create one UTF-8 HTML5 file with embedded CSS. Use semantic HTML and responsive layout by construction.

Pagex intentionally accepts a narrow static subset:

- semantic prose, table, figure and details elements;
- ordinary inline CSS;
- common static inline SVG chart elements;
- embedded raster data images;
- safe `http`, `https`, `mailto` and fragment links.

It rejects JavaScript, comments, declarations, processing instructions, event handlers, forms, iframes, media embeds, external runtime assets, CSS resource loading, unsafe URL schemes, pages over 2 MiB and likely credentials.

Prefer:

- system fonts;
- readable body measure;
- clear heading hierarchy;
- mobile reflow instead of horizontal scrolling;
- evidence-linked citations;
- one subject-specific visual device only when it carries information.

Do not use generic landing-page decoration, fake metrics, decorative dashboards or repeated cards when plain editorial structure is clearer.

## Fast path

For a routine answer page built from a proven pattern:

```sh
pagex publish /path/to/answer.html
```

Return the printed URL as the primary answer. Keep the surrounding message short; the page is the deliverable.

Use `publish` for a new artifact. Use `update` only when correcting or refining an existing canonical page:

```sh
pagex update 4k7m9q2x /path/to/revised.html
```

Do not silently replace a page the user may expect to remain frozen. If the topic or answer materially changes, publish a new page.

## Verification

`publish` and `update` validate the exact bytes they archive and upload. Use `pagex check <file>` separately only while iterating locally, before publication is authorized or when debugging a rejected file.

Do not generate screenshot suites, exact viewport metrics, remote object readbacks or QA reports for routine editorial pages.

Use a quick browser spot-check only when the page introduces a genuinely new template, dense visualization, unusual responsive behavior or a concrete reason to distrust the layout. Start with one narrow and one wide view. Escalate only after finding a real defect.

After publication, do not perform routine remote readbacks. If the upload succeeds, return the URL. If Pagex reports an uncertain timeout, preserve the reported id and use `pagex update <id> <file>` to converge the same object.

## Security and authorization

- Cloudflare Access is the privacy boundary; random ids are not secrets.
- Keep the bucket's `r2.dev` endpoint disabled.
- Never place API tokens, passwords, private keys, cookies or credentials in an answer page.
- Avoid machine-specific absolute paths and private internal URLs unless they are intentionally required by the answer.
- Pagex's credential scanner reduces accidental leakage; it does not prove content is safe.
- Treat publishing as an external side effect. Use standing authorization when the user has granted it; otherwise ask before uploading.
- Never create public infrastructure, change repository visibility or post the resulting URL publicly without explicit authorization.

## Completion checklist

- [ ] HTML is the better medium for this answer
- [ ] conclusion and reader takeaway are clear
- [ ] claims and citations are grounded
- [ ] file is self-contained and responsive
- [ ] publication is authorized
- [ ] new page uses `publish`; canonical correction uses `update`
- [ ] returned message leads with the Pagex URL
