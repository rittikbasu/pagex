# pagex

private one-file publishing for ai answer pages.

pagex gives an ai agent a private place to turn a long or visual answer into a polished web page and return a link instead of a wall of chat text.

```sh
pagex publish answer.html
# https://pages.example.com/4k7m9q2x
```

it reads the input once, performs cheap deterministic checks, stores those exact bytes in a private local archive and makes one cloudflare r2 upload. cloudflare access protects the resulting hostname.

## why

chat is good for conversation. it is less good for evidence-heavy research, comparisons, timelines, diagrams and answers worth saving.

pagex keeps the publishing half deliberately small:

```text
self-contained html
→ static safety check
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
pagex update 4k7m9q2x revised.html
```

`update` stores the previous local version under `~/.local/share/pagex/versions/` before uploading the replacement.

## use with hermes agent

install the bundled skill directly from github:

```sh
hermes skills install \
  https://raw.githubusercontent.com/rittikbasu/pagex/main/skills/pagex/SKILL.md
```

once pagex is configured and private publishing is authorized, the skill lets Hermes Agent choose a page when it is a better delivery format. this is especially useful for long answers delivered through telegram or another messaging surface.

the cli remains agent-agnostic. any agent or script that can write one html file can use pagex.

## accepted pages

pagex accepts a strict self-contained, javascript-free editorial subset:

- semantic prose, tables, figures, details and common static inline svg;
- embedded css;
- embedded raster data images;
- safe `http`, `https`, `mailto` and fragment links;
- files up to 2 mib.

it rejects scripts, comments, declarations, processing instructions, event handlers, forms, iframes, media embeds, executable urls, external runtime assets, css resource loading and high-confidence credential patterns.

the credential scan reduces accidental leakage; it does not prove a page is safe.

## security model

- cloudflare access is the authentication boundary;
- page ids are short addresses, not secrets;
- the bucket's `r2.dev` endpoint must remain disabled;
- local pages and version history are written with private file permissions;
- pagex never stores cloudflare credentials;
- a definitive failed upload restores the previous local state;
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
