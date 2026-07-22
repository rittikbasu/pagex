---
name: pagex
description: Use when a researched, structured or visual answer is materially easier to consume as a private web page than as chat. Build one responsive self-contained HTML document in Pagex's restrained reading system, validate it and publish only when authorized.
license: MIT
compatibility: Requires Python 3.11+ on POSIX. Checking needs the Pagex CLI; publishing also needs Wrangler and configured Cloudflare R2 and Access.
metadata:
  version: "0.3.0"
  author: pagex contributors
  homepage: https://github.com/rittikbasu/pagex
  tags: pagex, publishing, research, html, cloudflare, design
---

# Pagex

## Use

Use Pagex for research briefs, comparisons, plans, technical explainers and answers worth saving. Stay in chat for short or conversational replies and when HTML adds ceremony rather than clarity. Choose the medium without asking when the benefit is obvious.

## Build

1. **Answer first.** Establish the conclusion, reader decision and evidence before choosing layout. The title, a one-to-three-sentence answer and the first substantive unit should normally appear in the first desktop viewport.
2. **Copy the foundation.** Resolve [`templates/document.html`](templates/document.html) relative to this skill's root and copy it to the working HTML file. Replace every placeholder title, description, label and body passage. Preserve the embedded font faces, base CSS, offline CSP and `data-pagex="theme"` runtime exactly; do not reconstruct the shell.
3. **Compose around evidence.** Keep ordinary content on `.flow`. Add `.wide`, `.split`, `.ruled`, `.table-wrap`, a figure, code excerpt or quotation only where the evidence earns it. Append narrowly scoped content CSS inside the existing `<style>` instead of rewriting foundation selectors.
4. **Write one file.** Keep all CSS and data inline. Do not add scripts or runtime dependencies; the exact bundled theme runtime is the only JavaScript Pagex accepts.

The template fixes the document shell, self-contained typography, theme, reading measure and basic elements. It does not prescribe the body structure. Remove unused example elements and let the subject determine the sections.

Distribution references: [Cormorant Garamond OFL](assets/licenses/cormorant-garamond-OFL.txt) and [Newsreader OFL](assets/licenses/newsreader-OFL.txt). These notices belong to installed copies of the skill, not generated pages.

## Design contract

- **One reading spine:** keep prose and explanatory captions near `60–70ch`. On wide screens its left edge aligns with the Pagex wordmark; intentional empty space remains on the right. Wider evidence is a local interruption, not a new page axis.
- **Editorial typography:** preserve the template's existing body, heading and wordmark roles. Do not redefine their font stacks or add external font requests.
- **Quiet hierarchy:** one restrained `h1`, descriptive headings and a lead at normal reading scale. Keep ordinary prose and the full lead at regular weight. Use bold for short phrases, never as the default treatment for a multi-line lead or callout.
- **Useful masthead:** preserve the Pagex wordmark, quiet divider and theme control. Do not add generic labels such as “answer document,” fake navigation or metadata that does not help the reader.
- **Near-black dark mode:** preserve the foundation's near-black surface and soft white text. Do not introduce tinted panels or lighten the whole canvas to create hierarchy.
- **Few visual voices:** use typography, italics, thin rules and space before adding weight or chrome. Reserve monospace for code or genuinely technical data.
- **Useful density:** no giant hero, detached deck, ceremonial emptiness or small content enlarged into bands.
- **Evidence earns structure:** introduce columns, rules, tables and graphics only when they clarify a relationship. In repeated comparisons, organize by comparison category: each category title must govern the complete row and separators must belong to the row, never dangle beneath only one column.
- **Evidence earns width:** Keep compact tables on the reading spine. Constrain prose comparisons below the full evidence shell when wider columns lengthen eye travel. Research tables, charts and diagrams that become cramped at `68ch` may use `.wide`. Preserve the shared left edge and let narrow layouts recompose rather than merely shrink.
- **Mobile preserves the argument:** stack decisive comparisons completely. A prose-heavy matrix is not a reference table; author it as labeled groups at the source instead of hiding columns behind horizontal scrolling. Give horizontally scrollable table and code regions `tabindex="0"` and a concise `aria-label` so keyboard and assistive-technology users can discover them. Place a visible `.scroll-cue` immediately before each genuinely wide region; the shell shows it only on narrow screens.
- **Narrow layouts are composed, not shrunk:** a desktop SVG, chart or formula table scaled until its labels are tiny is not responsive. Reposition labels, preserve readable type and use shape or text as well as color.
- **Content autonomy:** choose the information architecture. Do not turn the foundation into a fixed sequence of hero, cards, metrics and conclusion.

Avoid landing-page heroes, card grids, gradients, shadows, pills, fake metrics, repeated eyebrow labels, decorative diagrams, excessive rules, long unbroken essays, full code dumps and entire paragraphs set in bold. Minimal means fewer visual decisions, not less information rendered larger.

## Behavior contract

Preserve the exact bundled theme runtime and its CSP. Do not add or edit scripts. Use native `<details>` for disclosure and static inline SVG for explanatory graphics. Keep the answer useful when JavaScript is disabled; system light or dark preference still applies without the toggle.

Pagex rejects other scripts, inputs, canvas, forms, iframes, media embeds, external assets, unsafe URLs, pages over 2 MiB and likely credentials. Never include secrets or machine-private material.

## Verify and publish

Run `pagex check /path/to/answer.html`. For a new layout, inspect wide and narrow viewports. Confirm the opening contains substance, the reading measure stays calm, tables and code remain legible, graphics have a real narrow state, the page has no horizontal overflow and the no-JavaScript answer remains useful. Exercise light, dark, system preference and keyboard focus when the shell changed.

Publishing is an external side effect. With authorization, run `pagex publish /path/to/answer.html` and return its URL first. Use `pagex update <id> /path/to/revised.html` only for a correction to the same canonical page. Do not change Cloudflare resources, Access policy or public visibility without explicit approval.
