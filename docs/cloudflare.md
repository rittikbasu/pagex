# cloudflare setup

pagex deliberately does not provision cloudflare resources. bucket names, dns, identity providers, access policies, permissions and spending are account-level decisions that should remain visible to the account owner.

this guide follows cloudflare's documented flow: create a bucket, create an access application, connect a custom domain and test the policy.

## before you start

you need:

- a cloudflare account;
- a domain using cloudflare dns;
- r2 enabled for the account;
- wrangler installed and authenticated;
- an access login method or identity provider you are comfortable using.

review current [r2 pricing](https://developers.cloudflare.com/r2/pricing/) and [cloudflare access plans](https://www.cloudflare.com/zero-trust/products/access/) before creating resources. pagex does not set budgets or spending limits.

## 1. authenticate wrangler

install wrangler using cloudflare's current instructions, then authenticate:

```sh
wrangler login
wrangler whoami
```

for unattended environments, wrangler can use `CLOUDFLARE_API_TOKEN`. keep that token in your secret manager or agent environment; never put it in `config.toml`, an answer page or the repository.

## 2. create the bucket

choose a bucket name and create it:

```sh
wrangler r2 bucket create your-pagex-bucket
wrangler r2 bucket list
```

bucket names must be 3–63 lowercase letters, numbers or hyphens and cannot begin or end with a hyphen.

cloudflare creates r2 buckets as private by default. do not enable the `r2.dev` public development url.

## 3. choose the hostname

choose a dedicated hostname such as:

```text
pages.example.com
```

pagex stores each page at the bucket root under its generated id, so a page will be served as:

```text
https://pages.example.com/jkmnpqrs
```

## 4. create the access application

in the cloudflare zero trust dashboard:

1. open **access controls → applications**;
2. add a self-hosted application;
3. enter the hostname chosen above;
4. create an allow policy for the users or groups who should read pages;
5. select the intended login method or identity provider;
6. save the application.

cloudflare access is the privacy boundary. page ids are addresses, not passwords.

follow Cloudflare's current [protect an R2 bucket with Access](https://developers.cloudflare.com/r2/tutorials/cloudflare-access/) guide if dashboard labels have changed.

## 5. connect the custom domain

in the r2 dashboard:

1. open the bucket;
2. open **settings**;
3. under **custom domains**, connect the hostname chosen above;
4. wait for the domain status to become active.

use the same hostname in r2 and the access application. keep the bucket's `r2.dev` url disabled.

## 6. test access before publishing

open the hostname in a private/incognito browser window. it should present the cloudflare access login before r2 responds.

sign in with an allowed account and confirm the request reaches r2. a missing-object response after authentication is fine; a public r2 response before authentication is not.

also test with an account that should not be allowed when the policy is more than a single-user allow rule.

## 7. configure pagex

create `~/.config/pagex/config.toml`:

```toml
bucket = "your-pagex-bucket"
base_url = "https://pages.example.com"
```

this file contains no cloudflare credentials. pagex delegates authentication to wrangler.

for a non-default location, set `PAGEX_CONFIG`. individual values can be overridden with `PAGEX_BUCKET`, `PAGEX_BASE_URL`, `PAGEX_DATA_DIR` and `PAGEX_WRANGLER`.

## 8. publish the example

from the repository:

```sh
pagex check example.html
pagex publish example.html
```

the explicit `check` is useful here as a first-run installation diagnostic. routine `publish` and `update` commands validate the page themselves.

pagex prints the new authenticated url. open it in an already-authorized browser and confirm the example renders.

## what pagex does not automate

pagex does not create or delete buckets, mutate dns, configure identity providers, create access policies, mint tokens or change account permissions. those operations have different security and failure semantics from publishing one checked html object and remain intentionally outside the project.
