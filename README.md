# pagex

private one-file publishing for ai answer pages.

pagex gives an ai agent a private place to turn a long or visual answer into a polished web page and return a link instead of a wall of chat text.

```sh
pagex publish answer.html
# https://pages.example.com/jkmnpqrs
```

it reads the input once, performs cheap deterministic checks, stores those exact bytes in a private local archive and makes one cloudflare r2 upload. cloudflare access protects the resulting hostname.

## why

chat is good for conversation. it is less good for evidence-heavy research, comparisons, timelines, diagrams and answers worth saving.

pagex keeps the publishing half deliberately small:

```text
self-contained html
→ deterministic safety check
→ private local archive
→ one r2 object
→ authenticated url
```

the optional [`pagex` agent skill](skills/pagex/SKILL.md) handles the larger behavior: noticing when a page is the better medium, building it responsively, publishing it and returning the link.

## requirements

- linux, macos or wsl;
- python 3.11 or newer;
- [cloudflare wrangler](https://developers.cloudflare.com/workers/wrangler/) installed and authenticated;
- an r2 bucket connected to a custom domain protected by cloudflare access.

pagex has no runtime python dependencies.

## install

with `uv`:

```sh
uv tool install git+https://github.com/rittikbasu/pagex
```

or from a checkout:

```sh
git clone https://github.com/rittikbasu/pagex
cd pagex
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
```

## set up cloudflare

follow [`docs/cloudflare.md`](docs/cloudflare.md) to:

1. create an r2 bucket;
2. create a cloudflare access application and allow policy;
3. connect a custom domain;
4. test the access boundary;
5. configure pagex locally.

pagex intentionally does not automate cloudflare account, dns, identity-provider, access-policy, permission or spending decisions.

## configure

create `~/.config/pagex/config.toml`:

```toml
bucket = "your-pagex-bucket"
base_url = "https://pages.example.com"
```

the file contains no cloudflare credentials. pagex delegates authentication to wrangler.

supported environment overrides:

| variable | purpose |
|---|---|
| `PAGEX_CONFIG` | alternate config file |
| `PAGEX_BUCKET` | r2 bucket |
| `PAGEX_BASE_URL` | authenticated https origin |
| `PAGEX_DATA_DIR` | local archive directory |
| `PAGEX_WRANGLER` | wrangler executable |

environment variables override values in the config file.

## use

validate a page without configuration or network access:

```sh
pagex check answer.html
```

`publish` and `update` run the same validation themselves. use `check` while iterating locally, before publication is authorized or when debugging a rejected file.

publish a new page:

```sh
pagex publish answer.html
```

replace an existing page while keeping its url:

```sh
pagex update jkmnpqrs revised.html
```

`update` stores the previous local version under `~/.local/share/pagex/versions/` before uploading the replacement.

## use with agents

pagex ships an [agent skill](https://agentskills.io/) containing the medium decision, design system and publishing workflow. the `pagex` cli must already be installed and configured on the same machine.

### hermes agent

install the skill directly from github:

```sh
hermes skills install \
  https://raw.githubusercontent.com/rittikbasu/pagex/main/skills/pagex/SKILL.md
```

start a new session or run `/reset` after installation. hermes can then choose a page when it is a better delivery format, or you can invoke the skill explicitly with `/pagex`.

### codex

ask codex to install the skill from this repository:

```text
$skill-installer install https://github.com/rittikbasu/pagex/tree/main/skills/pagex
```

restart codex after installation.

other clients that support the agent skills format can install the complete [`skills/pagex/`](skills/pagex/) directory using their normal skill installer. agents without skill support can still use the cli directly if they can write one html file and run shell commands.

once installed, the skill lets the agent produce long, researched or visual answers as pages instead of forcing them into chat. it also provides a neutral document template with embedded newsreader body text, cormorant garamond display type, georgia fallbacks, persistent light and dark themes and content-shaped layouts. the ofl-licensed woff2 subsets are included locally, so generated pages make no font requests at runtime.

installed copies are independent of the repository and may need to be reinstalled or updated when the source skill changes.

## accepted pages

pagex accepts a strict self-contained, offline editorial subset:

- semantic prose, tables, figures, details and common static inline svg;
- embedded css;
- embedded base64 woff2 fonts;
- embedded raster data images;
- the exact bundled inline theme runtime;
- safe `http`, `https`, `mailto` and fragment links;
- files up to 2 mib.

the restrictive content security policy must remain inside the document head before the bundled theme runtime. pagex rejects every other script, inputs, canvas, event attributes, forms, iframes, media embeds, executable urls, external runtime assets, external css or font urls and high-confidence credential patterns.

## security model

- cloudflare access is the authentication boundary;
- page ids are short addresses, not secrets;
- the bucket's `r2.dev` endpoint must remain disabled;
- local pages and version history are written with private file permissions;
- pagex never stores cloudflare credentials;
- pages remain self-contained and their required csp disables connect, frame, media, object and worker access;
- a definitive failed upload rolls back local state, or reports the retained page id and path if cleanup itself fails;
- an uncertain timeout keeps the desired local bytes and reports the id so `pagex update` can converge it.

pagex deliberately does not perform browser verification, collision preflights, routine remote readbacks or distributed transaction coordination. use separate browser tooling only while developing a new template, debugging a layout or checking an uncertain visualization.

## local state

```text
~/.config/pagex/config.toml
~/.local/share/pagex/pages/<id>.html
~/.local/share/pagex/versions/<id>/<timestamp>.html
```

set `XDG_CONFIG_HOME` or `XDG_DATA_HOME` to use the corresponding standard alternate roots.

## development

```sh
python3 -W error -m unittest -v
python3 pagex.py check example.html
```

pagex uses only the python standard library at runtime. tests simulate r2 and do not require cloudflare credentials.

## scope

pagex is intentionally a one-user, one-machine publisher for private answer pages. it is not a general hosting platform, site generator, cloudflare provisioner, multi-user service or storage abstraction.

## license

mit
