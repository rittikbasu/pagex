import base64
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pagex


SHORT_PAGE_ID = "abcdefgh"
SECOND_SHORT_PAGE_ID = "jkmnpqrs"
PAGE_CSP = (
    "default-src 'none'; base-uri 'none'; connect-src 'none'; font-src data:; "
    "form-action 'none'; frame-src 'none'; img-src data:; media-src 'none'; "
    "object-src 'none'; script-src 'unsafe-inline'; script-src-attr 'none'; "
    "style-src 'unsafe-inline'; worker-src 'none'"
)


class FakeR2:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.commands: list[list[str]] = []
        self.fail_next_put = False
        self.timeout_next_put = False

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        operation = command[3]
        if operation != "put":
            raise AssertionError(f"unexpected R2 operation: {operation}")
        if self.timeout_next_put:
            self.timeout_next_put = False
            raise subprocess.TimeoutExpired(command, 120)
        if self.fail_next_put:
            self.fail_next_put = False
            return subprocess.CompletedProcess(command, 1, "", "simulated upload failure")
        object_path = command[4]
        file_path = Path(command[command.index("--file") + 1])
        self.objects[object_path] = file_path.read_bytes()
        return subprocess.CompletedProcess(command, 0, "", "")


class InspectPageTests(unittest.TestCase):
    @staticmethod
    def page(body: str, head: str = "") -> str:
        return f"<!doctype html><html><head><title>test</title>{head}</head><body>{body}</body></html>"

    def test_accepts_minimal_self_contained_html(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answer.html"
            path.write_text(
                self.page("<main>use direct r2.</main>", "<style>body{color:#111}</style>"),
                encoding="utf-8",
            )
            result = pagex.inspect_page(path)
            self.assertEqual(result.title, "test")
            self.assertGreater(result.text_length, 0)

    def test_inspects_immutable_html_bytes(self):
        source = self.page("<main>bytes</main>").encode()
        result = pagex.inspect_html(source)
        self.assertEqual(result.title, "test")
        self.assertGreater(result.text_length, 0)

    def test_rejects_oversized_file_before_reading_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "huge.html"
            with path.open("wb") as handle:
                handle.truncate(pagex.MAX_PAGE_BYTES + 1)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("must not read")):
                with self.assertRaisesRegex(pagex.PageRejected, "2 MiB"):
                    pagex.inspect_page(path)

    def test_accepts_page_at_exact_size_limit(self):
        source = self.page("<main></main>").encode()
        padding = b"x" * (pagex.MAX_PAGE_BYTES - len(source))
        source = source.replace(b"<main>", b"<main>" + padding, 1)

        self.assertEqual(len(source), pagex.MAX_PAGE_BYTES)
        self.assertEqual(pagex.inspect_html(source).title, "test")

    def test_rejects_unreadable_input_as_page_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.html"
            path.mkdir()

            with self.assertRaisesRegex(pagex.PageRejected, "could not read page"):
                pagex.inspect_page(path)

    def test_accepts_static_inline_svg_visualisation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.html"
            path.write_text(
                self.page(
                    "<main><svg viewBox='0 0 200 100' role='img' aria-label='bar chart'>"
                    "<defs><linearGradient id='bar' x1='0' y1='0' x2='1' y2='0'>"
                    "<stop offset='0%' stop-color='#f60'/><stop offset='100%' stop-color='#fc0'/>"
                    "</linearGradient></defs><rect x='10' y='20' width='160' height='30' "
                    "rx='4' fill='url(#bar)'/><text x='10' y='80'>160 responses</text>"
                    "</svg></main>"
                ),
                encoding="utf-8",
            )
            result = pagex.inspect_page(path)
            self.assertGreater(result.text_length, 0)

    def test_svg_title_does_not_change_the_document_title(self):
        source = self.page(
            "<main>answer<svg viewBox='0 0 20 20' role='img' "
            "aria-labelledby='chart-title'><title id='chart-title'>retry ceiling</title>"
            "<circle cx='10' cy='10' r='4'></circle></svg></main>"
        )

        result = pagex.inspect_html(source.encode())

        self.assertEqual(result.title, "test")

    def test_accepts_embedded_woff2_font(self):
        font = base64.b64encode(b"wOF2" + b"pagex-font-data").decode()
        source = self.page(
            "<main>typeset answer</main>",
            "<style>"
            "@font-face{font-family:'Pagex Test';"
            f"src:url(data:font/woff2;base64,{font}) format('woff2');"
            "font-display:swap;font-style:normal;font-weight:400}"
            "body{font-family:'Pagex Test',serif}"
            "</style>",
        )

        result = pagex.inspect_html(source.encode())

        self.assertEqual(result.title, "test")

    def test_rejects_agent_authored_javascript(self):
        source = self.page(
            "<main>answer remains readable</main>",
            f'<meta http-equiv="Content-Security-Policy" content="{PAGE_CSP}">'
            "<script data-pagex='interaction'>document.body.dataset.ready='true';</script>",
        )

        with self.assertRaisesRegex(pagex.PageRejected, "bundled theme runtime"):
            pagex.inspect_html(source.encode())

    def test_rejects_theme_csp_outside_head(self):
        template = (Path(__file__).parent / "skills/pagex/templates/document.html").read_text(
            encoding="utf-8"
        )
        runtime = re.search(
            r'<script data-pagex="theme">(.*?)</script>', template, re.DOTALL
        ).group(1)
        source = (
            "<!doctype html><html><head><title>test</title></head><body>"
            f'<meta http-equiv="Content-Security-Policy" content="{PAGE_CSP}">'
            f"<main>answer remains readable</main><script data-pagex='theme'>{runtime}</script>"
            "</body></html>"
        )

        with self.assertRaisesRegex(pagex.PageRejected, "inside head"):
            pagex.inspect_html(source.encode())

    def test_rejects_reopened_head(self):
        source = (
            "<!doctype html><html><head><title>test</title></head><body>"
            "<head><meta name='description' content='late'></head><main>answer</main>"
            "</body></html>"
        )

        with self.assertRaisesRegex(pagex.PageRejected, "head element"):
            pagex.inspect_html(source.encode())

    def test_rejects_inputs_and_canvas(self):
        for element in (
            "<input type='range' aria-label='amount'>",
            "<canvas aria-label='chart'>fallback</canvas>",
        ):
            with self.subTest(element=element), self.assertRaisesRegex(
                pagex.PageRejected, "outside the Pagex boundary"
            ):
                pagex.inspect_html(self.page(f"<main>answer{element}</main>").encode())

    def test_rejects_unsafe_single_object_pages(self):
        unsafe_pages = {
            "missing doctype": "<html><head><title>x</title></head><body>x</body></html>",
            "script": self.page("<script>alert(1)</script>x"),
            "event handler": self.page("<main onload='alert(1)'>x</main>"),
            "encoded javascript": self.page("<a href='jav&#x61;script:alert(1)'>x</a>"),
            "external image": self.page("<img src='https://example.com/x.png'>x"),
            "base url": self.page("<base href='https://example.com/'>x"),
            "meta refresh": self.page("x", "<meta http-equiv='refresh' content='0;url=https://example.com'>"),
            "embedded svg": self.page("<svg><use href='https://example.com/x.svg#x'/></svg>x"),
            "form": self.page("<form action='https://example.com'><button>x</button></form>"),
            "css import": self.page("x", "<style>@import url('https://example.com/x.css')</style>"),
            "inline css url": self.page(
                "<main style='background:url(https://example.com/tracker.png)'>x</main>"
            ),
            "external font": self.page(
                "x",
                "<style>@font-face{font-family:x;src:url(https://example.com/x.woff2)}</style>",
            ),
            "fake woff2": self.page(
                "x",
                "<style>@font-face{font-family:x;"
                "src:url(data:font/woff2;base64,bm90LWEtZm9udA==)}</style>",
            ),
            "escaped css url": self.page("x", "<style>body{background:u\\72l(https://example.com/x.png)}</style>"),
            "comment": self.page("<!-- note --><main>x</main>"),
            "malformed comment": self.page("<!--><script>document.title='x'</script>--><main>x</main>"),
            "bogus declaration": self.page("<!pagex><main>x</main>"),
            "processing instruction": self.page("<?pagex><main>x</main>"),
            "credential": self.page("api_key = abcdefghijklmnopqrstuvwxyz"),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, source in unsafe_pages.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name}.html"
                    path.write_text(source, encoding="utf-8")
                    with self.assertRaises(pagex.PageRejected):
                        pagex.inspect_page(path)

    def test_rejects_high_confidence_credentials(self):
        values = (
            "Bearer " + "a" * 40,
            "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 24,
            "sk-proj-" + "a" * 40,
            "postgresql://user:" + "p" * 20 + "@db.example.com/app",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, value in enumerate(values):
                with self.subTest(index=index):
                    path = Path(directory) / f"credential-{index}.html"
                    path.write_text(self.page(f"<main>{value}</main>"), encoding="utf-8")
                    with self.assertRaisesRegex(pagex.PageRejected, "credential"):
                        pagex.inspect_page(path)


class SkillDesignTests(unittest.TestCase):
    def test_skill_is_agent_skills_portable_and_references_its_template(self):
        skill = (Path(__file__).parent / "skills" / "pagex" / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = skill.split("---", 2)[1]

        self.assertIn("name: pagex", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertIn("license: MIT", frontmatter)
        self.assertIn("compatibility:", frontmatter)
        self.assertIn("[`templates/document.html`](templates/document.html)", skill)
        self.assertIn("[Cormorant Garamond OFL](assets/licenses/cormorant-garamond-OFL.txt)", skill)
        self.assertIn("[Newsreader OFL](assets/licenses/newsreader-OFL.txt)", skill)
        self.assertIn("separators must belong to the row", skill)
        self.assertNotIn("/home/", skill)
        self.assertNotIn("~/.hermes", skill)
        self.assertNotIn("$HERMES", skill)
        metadata = frontmatter.split("metadata:\n", 1)[1]
        for line in metadata.splitlines():
            if not line.strip():
                continue
            self.assertRegex(line, r"^  [a-z][a-z0-9_-]*: .+")
            self.assertNotIn("[", line)

    def test_readme_retains_hermes_codex_and_generic_agent_install_paths(self):
        readme = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

        self.assertIn("hermes skills install", readme)
        self.assertIn("$skill-installer", readme)
        self.assertIn("other clients that support the agent skills format", readme)
        self.assertIn("skills/pagex/SKILL.md", readme)

    def test_bundled_document_template_is_self_contained_and_accepted(self):
        template = Path(__file__).parent / "skills/pagex/templates/document.html"
        assets = template.parent.parent / "assets"

        source = template.read_bytes()
        text = source.decode()
        inspection = pagex.inspect_html(source)
        embedded_fonts = re.findall(
            r"src: url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\) format\('woff2'\);",
            text,
        )
        asset_fonts = [
            (assets / filename).read_text(encoding="ascii").strip()
            for filename in (
                "cormorant-garamond-latin.woff2.b64",
                "newsreader-latin.woff2.b64",
                "newsreader-italic-latin.woff2.b64",
            )
        ]

        self.assertEqual(inspection.title, "Page title")
        self.assertLess(len(source), pagex.MAX_PAGE_BYTES)
        self.assertEqual(embedded_fonts, asset_fonts)
        self.assertIn("data-pagex=\"theme\"", text)
        self.assertRegex(
            text,
            r'<button\b(?=[^>]*\btype="button")(?=[^>]*\bdata-theme-toggle\b)'
            r'(?=[^>]*\baria-label="[^"]+")[^>]*>',
        )
        self.assertIn("button.setAttribute('aria-label'", text)

    def test_template_keeps_wide_content_reachable_without_custom_scrollbars(self):
        text = (Path(__file__).parent / "skills/pagex/templates/document.html").read_text(
            encoding="utf-8"
        )
        pre = re.search(r"\n    pre \{(.*?)\n    \}", text, re.DOTALL)
        cue = re.search(r"\n    \.scroll-cue \{(.*?)\n    \}", text, re.DOTALL)
        narrow = re.search(r"@media \(max-width: 52rem\) \{(.*?)\n    \}", text, re.DOTALL)

        self.assertIsNotNone(pre)
        self.assertIn("max-width: 100%", pre.group(1))
        self.assertIn("overflow: auto", pre.group(1))
        self.assertIn(".table-wrap { max-width: 100%; overflow-x: auto; }", text)
        self.assertIn(".table-wrap.wide { max-width: none; }", text)
        self.assertIsNotNone(cue)
        self.assertIn("display: none", cue.group(1))
        self.assertIsNotNone(narrow)
        self.assertIn(".scroll-cue { display: block; }", narrow.group(1))
        self.assertNotIn("scrollbar-color", text)
        self.assertNotIn("::-webkit-scrollbar", text)

    def test_bundled_font_assets_are_licensed_and_match_metadata(self):
        assets = Path(__file__).parent / "skills/pagex/assets"
        metadata = json.loads((assets / "fonts.json").read_text(encoding="utf-8"))

        self.assertEqual(len(metadata), 3)
        for item in metadata:
            payload = (assets / item["file"]).read_text(encoding="ascii").strip()
            font = base64.b64decode(payload, validate=True)
            self.assertTrue(font.startswith(b"wOF2"))
            self.assertEqual(len(font), item["bytes"])
            self.assertEqual(hashlib.sha256(font).hexdigest(), item["sha256"])
        for license_name in ("cormorant-garamond-OFL.txt", "newsreader-OFL.txt"):
            license_text = (assets / "licenses" / license_name).read_text(encoding="utf-8")
            self.assertIn("SIL OPEN FONT LICENSE Version 1.1", license_text)

    def test_rejects_modified_pagex_theme_runtime(self):
        template = (Path(__file__).parent / "skills/pagex/templates/document.html").read_text(
            encoding="utf-8"
        )
        modified = template.replace(
            "const storageKey = 'pagex-theme';",
            "const storageKey = 'not-pagex-theme';",
        )
        self.assertNotEqual(template, modified)
        with self.assertRaisesRegex(pagex.PageRejected, "theme runtime"):
            pagex.inspect_html(modified.encode())

    def test_package_configuration_includes_portable_skill(self):
        manifest = (Path(__file__).parent / "MANIFEST.in").read_text(encoding="utf-8")
        project = tomllib.loads(
            (Path(__file__).parent / "pyproject.toml").read_text(encoding="utf-8")
        )

        for extension in ("html", "b64", "json", "txt"):
            self.assertRegex(manifest, rf"recursive-include skills .*\*\.{extension}")
        data_files = project["tool"]["setuptools"]["data-files"]
        self.assertEqual(
            data_files["share/pagex/skills/pagex"],
            ["skills/pagex/SKILL.md"],
        )
        self.assertEqual(
            data_files["share/pagex/skills/pagex/templates"],
            ["skills/pagex/templates/document.html"],
        )
        self.assertEqual(
            data_files["share/pagex/skills/pagex/assets"],
            [
                "skills/pagex/assets/fonts.json",
                "skills/pagex/assets/*.woff2.b64",
            ],
        )
        self.assertEqual(
            data_files["share/pagex/skills/pagex/assets/licenses"],
            ["skills/pagex/assets/licenses/*.txt"],
        )


class PageIdTests(unittest.TestCase):
    def test_generates_unique_lowercase_8_character_ids(self):
        identifiers = {pagex.generate_page_id() for _ in range(1_000)}
        self.assertEqual(len(identifiers), 1_000)
        self.assertTrue(all(re.fullmatch(r"[a-z]{8}", value) for value in identifiers))

    def test_documented_page_ids_match_the_generated_format(self):
        root = Path(__file__).parent
        documentation = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in ("README.md", "docs/cloudflare.md")
        )
        examples = re.findall(r"https://pages\.example\.com/([a-z0-9]+)", documentation)

        self.assertTrue(examples)
        self.assertTrue(all(re.fullmatch(r"[a-z]{8}", value) for value in examples))


class FileSafetyTests(unittest.TestCase):
    def test_atomic_write_creates_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "private/page.html"
            pagex._atomic_write(b"exact bytes", destination)
            self.assertEqual(destination.read_bytes(), b"exact bytes")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)


class ConfigTests(unittest.TestCase):
    def test_reads_non_secret_config_from_explicit_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.toml"
            config_path.write_text(
                'bucket = "my-pagex"\n'
                'base_url = "https://pages.example.com"\n',
                encoding="utf-8",
            )

            config = pagex.load_config(
                {
                    "HOME": str(root),
                    "PAGEX_CONFIG": str(config_path),
                    "XDG_DATA_HOME": str(root / "data"),
                }
            )

            self.assertEqual(config.bucket, "my-pagex")
            self.assertEqual(config.base_url, "https://pages.example.com")
            self.assertEqual(config.data_dir, root / "data/pagex")
            self.assertEqual(config.wrangler, "wrangler")

    def test_environment_overrides_config_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.toml"
            config_path.write_text(
                'bucket = "from-file"\n'
                'base_url = "https://file.example.com"\n'
                'data_dir = "~/pagex-data"\n'
                'wrangler = "file-wrangler"\n',
                encoding="utf-8",
            )

            config = pagex.load_config(
                {
                    "HOME": str(root),
                    "PAGEX_CONFIG": str(config_path),
                    "PAGEX_BUCKET": "from-env",
                    "PAGEX_BASE_URL": "https://env.example.com/",
                    "PAGEX_DATA_DIR": str(root / "env-data"),
                    "PAGEX_WRANGLER": "env-wrangler",
                }
            )

            self.assertEqual(config.bucket, "from-env")
            self.assertEqual(config.base_url, "https://env.example.com")
            self.assertEqual(config.data_dir, root / "env-data")
            self.assertEqual(config.wrangler, "env-wrangler")

    def test_requires_bucket_and_base_url_for_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(pagex.PagexConfigError, "bucket.*base_url"):
                pagex.load_config(
                    {
                        "HOME": str(root),
                        "PAGEX_CONFIG": str(root / "missing.toml"),
                    }
                )

    def test_rejects_insecure_or_path_based_base_url(self):
        invalid_urls = (
            "http://pages.example.com",
            "https://pages.example.com/private",
            "https://pages.example.com?debug=1",
            "https://pages.example.com:abc",
            "https://pages.example.com:70000",
            "https://pages.example.com\\wrong",
            "https://pages.example.com wrong",
            "https://[::1",
            "https://xn--a.example",
            "https://999.999.999.999",
            "https://pages.example.com\n.evil.com",
            "https://pages.example.com\r.evil.com",
            "https://pages.example.com\t.evil.com",
        )
        for base_url in invalid_urls:
            with self.subTest(base_url=base_url), self.assertRaisesRegex(
                pagex.PagexConfigError, "HTTPS origin"
            ):
                pagex.load_config(
                    {
                        "PAGEX_BUCKET": "my-pagex",
                        "PAGEX_BASE_URL": base_url,
                    }
                )

    def test_normalizes_valid_idna_base_url(self):
        config = pagex.load_config(
            {
                "PAGEX_BUCKET": "my-pagex",
                "PAGEX_BASE_URL": "https://bücher.example/",
            }
        )

        self.assertEqual(config.base_url, "https://xn--bcher-kva.example")

    def test_empty_or_relative_xdg_roots_fall_back_to_home(self):
        for invalid_root in ("", "relative"):
            with self.subTest(invalid_root=invalid_root), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                config_path = home / ".config/pagex/config.toml"
                config_path.parent.mkdir(parents=True)
                config_path.write_text(
                    'bucket = "my-pagex"\n'
                    'base_url = "https://pages.example.com"\n',
                    encoding="utf-8",
                )

                config = pagex.load_config(
                    {
                        "HOME": str(home),
                        "XDG_CONFIG_HOME": invalid_root,
                        "XDG_DATA_HOME": invalid_root,
                    }
                )

                self.assertEqual(config.data_dir, home / ".local/share/pagex")

    def test_empty_or_relative_home_falls_back_to_system_home(self):
        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        for invalid_home in ("", "relative"):
            with self.subTest(invalid_home=invalid_home):
                config = pagex.load_config(
                    {
                        "HOME": invalid_home,
                        "PAGEX_BUCKET": "my-pagex",
                        "PAGEX_BASE_URL": "https://pages.example.com",
                    }
                )

                self.assertEqual(config.data_dir, account_home / ".local/share/pagex")

    def test_invalid_process_home_falls_back_to_account_home(self):
        account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        with tempfile.TemporaryDirectory() as directory:
            for invalid_home in ("", "relative"):
                with self.subTest(invalid_home=invalid_home):
                    environ = os.environ.copy()
                    environ.update(
                        HOME=invalid_home,
                        PAGEX_BASE_URL="https://pages.example.com",
                        PAGEX_BUCKET="my-pagex",
                        PAGEX_CONFIG=str(Path(directory) / "missing.toml"),
                    )
                    environ.pop("PAGEX_DATA_DIR", None)
                    environ.pop("XDG_DATA_HOME", None)
                    result = subprocess.run(
                        [sys.executable, "-c", "import pagex; print(pagex.load_config().data_dir)"],
                        capture_output=True,
                        check=False,
                        env=environ,
                        text=True,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), str(account_home / ".local/share/pagex"))

    def test_rejects_invalid_r2_bucket_name(self):
        with self.assertRaisesRegex(pagex.PagexConfigError, "bucket"):
            pagex.load_config(
                {
                    "PAGEX_BUCKET": "INVALID_BUCKET",
                    "PAGEX_BASE_URL": "https://pages.example.com",
                }
            )

    def test_rejects_relative_data_dir(self):
        with self.assertRaisesRegex(pagex.PagexConfigError, "data_dir"):
            pagex.load_config(
                {
                    "PAGEX_BUCKET": "my-pagex",
                    "PAGEX_BASE_URL": "https://pages.example.com",
                    "PAGEX_DATA_DIR": "relative",
                }
            )


class PublisherTests(unittest.TestCase):
    @staticmethod
    def make_publisher(root: Path, fake: FakeR2) -> pagex.PagexPublisher:
        return pagex.PagexPublisher(
            bucket="pagex",
            base_url="https://pages.example.com",
            data_dir=root / "data",
            wrangler="wrangler",
            runner=fake,
        )

    @staticmethod
    def html(path: Path, title: str = "x") -> None:
        path.write_text(f"<!doctype html><html><head><title>{title}</title></head><body><main>{title}</main></body></html>")

    def test_publish_uses_static_checks_and_exactly_one_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answer.html"
            self.html(source)
            fake = FakeR2()
            result = self.make_publisher(root, fake).publish(source, id_factory=lambda: SHORT_PAGE_ID)
            self.assertEqual(result.page_id, SHORT_PAGE_ID)
            self.assertEqual(fake.objects[f"pagex/{SHORT_PAGE_ID}"], source.read_bytes())
            self.assertEqual((root / f"data/pages/{SHORT_PAGE_ID}.html").read_bytes(), source.read_bytes())
            self.assertEqual([command[3] for command in fake.commands], ["put"])
            put = fake.commands[0]
            self.assertEqual(put.count("--remote"), 1)
            self.assertEqual(put[put.index("--content-type") + 1], "text/html; charset=utf-8")
            self.assertEqual(put[put.index("--cache-control") + 1], "private, no-store")


    def test_publish_uses_immutable_source_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answer.html"
            self.html(source)
            original = source.read_bytes()
            fake = FakeR2()
            real_inspect = pagex.inspect_html

            def inspect_then_mutate(data: bytes):
                result = real_inspect(data)
                source.write_text("<script>changed</script>")
                return result

            with patch("pagex.inspect_html", side_effect=inspect_then_mutate):
                self.make_publisher(root, fake).publish(source, id_factory=lambda: SHORT_PAGE_ID)
            self.assertEqual(fake.objects[f"pagex/{SHORT_PAGE_ID}"], original)

    def test_publish_regenerates_after_local_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answer.html"
            self.html(source)
            pages = root / "data/pages"
            pages.mkdir(parents=True)
            (pages / f"{SHORT_PAGE_ID}.html").write_text("old")
            identifiers = iter((SHORT_PAGE_ID, SECOND_SHORT_PAGE_ID))
            result = self.make_publisher(root, FakeR2()).publish(source, id_factory=lambda: next(identifiers))
            self.assertEqual(result.page_id, SECOND_SHORT_PAGE_ID)

    def test_update_accepts_current_page_id_with_one_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old.html"
            new = root / "new.html"
            self.html(old, "old")
            self.html(new, "new")
            local = root / f"data/pages/{SHORT_PAGE_ID}.html"
            local.parent.mkdir(parents=True)
            local.write_bytes(old.read_bytes())
            fake = FakeR2()
            result = self.make_publisher(root, fake).update(SHORT_PAGE_ID, new)
            self.assertEqual(result.page_id, SHORT_PAGE_ID)
            self.assertEqual(local.read_bytes(), new.read_bytes())
            self.assertEqual(fake.objects[f"pagex/{SHORT_PAGE_ID}"], new.read_bytes())
            self.assertEqual([command[3] for command in fake.commands], ["put"])
            versions = list((root / f"data/versions/{SHORT_PAGE_ID}").glob("*.html"))
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0].read_bytes(), old.read_bytes())

    def test_update_rejects_noncurrent_page_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "new.html"
            self.html(source, "new")
            publisher = self.make_publisher(Path(directory), FakeR2())
            for page_id in ("23456789", "abcdefghij", "abcdefghijklmnopqrstuvwxyz"):
                with self.subTest(page_id=page_id), self.assertRaisesRegex(
                    pagex.PublishFailed, "invalid page ID"
                ):
                    publisher.update(page_id, source)

    def test_update_restores_local_version_when_upload_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old.html"
            new = root / "new.html"
            self.html(old, "old")
            self.html(new, "new")
            local = root / f"data/pages/{SHORT_PAGE_ID}.html"
            local.parent.mkdir(parents=True)
            local.write_bytes(old.read_bytes())
            fake = FakeR2()
            fake.fail_next_put = True
            with self.assertRaises(pagex.PublishFailed):
                self.make_publisher(root, fake).update(SHORT_PAGE_ID, new)
            self.assertEqual(local.read_bytes(), old.read_bytes())

    def test_publish_retains_local_page_when_upload_outcome_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answer.html"
            self.html(source)
            fake = FakeR2()
            fake.timeout_next_put = True
            with self.assertRaisesRegex(pagex.PublishFailed, f"unknown.*{SHORT_PAGE_ID}"):
                self.make_publisher(root, fake).publish(source, id_factory=lambda: SHORT_PAGE_ID)
            self.assertEqual(
                (root / f"data/pages/{SHORT_PAGE_ID}.html").read_bytes(),
                source.read_bytes(),
            )

    def test_publish_removes_local_page_after_definitive_upload_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answer.html"
            self.html(source)
            fake = FakeR2()
            fake.fail_next_put = True

            with self.assertRaisesRegex(pagex.PublishFailed, "simulated upload failure"):
                self.make_publisher(root, fake).publish(
                    source, id_factory=lambda: SHORT_PAGE_ID
                )

            self.assertFalse((root / f"data/pages/{SHORT_PAGE_ID}.html").exists())

    def test_publish_reports_retained_page_when_failure_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "answer.html"
            self.html(source)
            fake = FakeR2()
            fake.fail_next_put = True

            with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
                with self.assertRaisesRegex(
                    pagex.PublishFailed, f"cleanup failed.*{SHORT_PAGE_ID}"
                ):
                    self.make_publisher(root, fake).publish(
                        source, id_factory=lambda: SHORT_PAGE_ID
                    )

            self.assertEqual(
                (root / f"data/pages/{SHORT_PAGE_ID}.html").read_bytes(),
                source.read_bytes(),
            )

    def test_update_retains_new_local_page_when_upload_outcome_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old.html"
            new = root / "new.html"
            self.html(old, "old")
            self.html(new, "new")
            local = root / f"data/pages/{SHORT_PAGE_ID}.html"
            local.parent.mkdir(parents=True)
            local.write_bytes(old.read_bytes())
            fake = FakeR2()
            fake.timeout_next_put = True
            with self.assertRaisesRegex(pagex.PublishFailed, f"unknown.*{SHORT_PAGE_ID}"):
                self.make_publisher(root, fake).update(SHORT_PAGE_ID, new)
            self.assertEqual(local.read_bytes(), new.read_bytes())


class CliTests(unittest.TestCase):
    def test_browser_flag_is_not_part_of_pagex(self):
        parser = pagex.build_parser()
        commands = (
            ["check", "a.html", "--browser"],
            ["publish", "a.html", "--browser"],
            ["update", SHORT_PAGE_ID, "a.html", "--browser"],
        )
        for command in commands:
            with self.subTest(command=command), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(command)


if __name__ == "__main__":
    unittest.main()
