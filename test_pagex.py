import base64
import os
import pwd
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pagex


SHORT_PAGE_ID = "23456789"
SECOND_SHORT_PAGE_ID = "abcdefgh"
LEGACY_PAGE_ID = "23456789ab"
LONG_PAGE_ID = "23456789abcdefghjkmnpqrstu"


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
    def test_bundled_design_css_is_self_contained_and_accepted(self):
        script = Path(__file__).parent / "skills/pagex/scripts/design_css.py"

        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("font-family: 'Cormorant Garamond'", result.stdout)
        self.assertIn("font-family: 'Newsreader'", result.stdout)
        source = InspectPageTests.page(
            "<main><h1>designed answer</h1><p>readable body</p></main>",
            f"<style>{result.stdout}</style>",
        )
        inspection = pagex.inspect_html(source.encode())
        self.assertEqual(inspection.title, "test")


class PageIdTests(unittest.TestCase):
    def test_generates_unique_unambiguous_8_character_ids(self):
        identifiers = {pagex.generate_page_id() for _ in range(1_000)}
        self.assertEqual(len(identifiers), 1_000)
        self.assertTrue(all(re.fullmatch(r"[23456789abcdefghjkmnpqrstuvwxyz]{8}", value) for value in identifiers))


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

    def test_update_accepts_8_10_and_26_character_ids_with_one_upload(self):
        for page_id in (SHORT_PAGE_ID, LEGACY_PAGE_ID, LONG_PAGE_ID):
            with self.subTest(page_id=page_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                old = root / "old.html"
                new = root / "new.html"
                self.html(old, "old")
                self.html(new, "new")
                local = root / f"data/pages/{page_id}.html"
                local.parent.mkdir(parents=True)
                local.write_bytes(old.read_bytes())
                fake = FakeR2()
                result = self.make_publisher(root, fake).update(page_id, new)
                self.assertEqual(result.page_id, page_id)
                self.assertEqual(local.read_bytes(), new.read_bytes())
                self.assertEqual(fake.objects[f"pagex/{page_id}"], new.read_bytes())
                self.assertEqual([command[3] for command in fake.commands], ["put"])
                versions = list((root / f"data/versions/{page_id}").glob("*.html"))
                self.assertEqual(len(versions), 1)
                self.assertEqual(versions[0].read_bytes(), old.read_bytes())

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
            ["update", LEGACY_PAGE_ID, "a.html", "--browser"],
        )
        for command in commands:
            with self.subTest(command=command), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(command)


if __name__ == "__main__":
    unittest.main()
