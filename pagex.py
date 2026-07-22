#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Mapping
from datetime import datetime, timezone
import argparse
import base64
import binascii
import fcntl
import hashlib
import os
import pwd
import re
import secrets
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlsplit


MAX_PAGE_BYTES = 2 * 1024 * 1024
PAGE_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
PAGE_ID_LENGTH = 8
PAGE_ID_PATTERN = re.compile(f"[{re.escape(PAGE_ID_ALPHABET)}]+")
R2_BUCKET_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])")
HOST_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
CONFIG_KEYS = {"base_url", "bucket", "data_dir", "wrangler"}
SVG_TAGS = {
    "circle", "clippath", "defs", "ellipse", "g", "line", "lineargradient",
    "path", "polygon", "polyline", "radialgradient", "rect", "stop", "svg",
    "text", "tspan",
}
ALLOWED_TAGS = {
    "a", "abbr", "article", "aside", "b", "blockquote", "body", "br",
    "button", "caption", "cite", "code", "col", "colgroup", "dd", "details", "dfn",
    "div", "dl", "dt", "em", "figcaption", "figure", "footer", "h1", "h2",
    "h3", "h4", "h5", "h6", "head", "header", "hr", "html", "i", "img",
    "kbd", "li", "main", "mark", "meta", "nav", "ol", "p", "pre", "q",
    "s", "samp", "script", "section", "small", "span", "strong", "style", "sub",
    "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "time",
    "title", "tr", "u", "ul", "var",
} | SVG_TAGS
GLOBAL_ATTRIBUTES = {"class", "dir", "hidden", "id", "lang", "role", "style", "tabindex", "title"}
SVG_PAINT_ATTRIBUTES = {
    "fill", "fill-opacity", "opacity", "stroke", "stroke-dasharray",
    "stroke-dashoffset", "stroke-linecap", "stroke-linejoin", "stroke-opacity",
    "stroke-width", "transform", "vector-effect",
}
TAG_ATTRIBUTES = {
    "a": {"href", "rel", "target"},
    "blockquote": {"cite"},
    "button": {"disabled", "type"},
    "col": {"span"},
    "details": {"open"},
    "img": {"alt", "decoding", "height", "loading", "src", "width"},
    "li": {"value"},
    "meta": {"charset", "content", "http-equiv", "name"},
    "ol": {"reversed", "start", "type"},
    "q": {"cite"},
    "td": {"colspan", "headers", "rowspan"},
    "th": {"abbr", "colspan", "headers", "rowspan", "scope"},
    "time": {"datetime"},
    "svg": {"height", "preserveaspectratio", "viewbox", "width"} | SVG_PAINT_ATTRIBUTES,
    "g": SVG_PAINT_ATTRIBUTES,
    "path": {"d", "pathlength"} | SVG_PAINT_ATTRIBUTES,
    "rect": {"height", "rx", "ry", "width", "x", "y"} | SVG_PAINT_ATTRIBUTES,
    "circle": {"cx", "cy", "r"} | SVG_PAINT_ATTRIBUTES,
    "ellipse": {"cx", "cy", "rx", "ry"} | SVG_PAINT_ATTRIBUTES,
    "line": {"x1", "x2", "y1", "y2"} | SVG_PAINT_ATTRIBUTES,
    "polyline": {"points"} | SVG_PAINT_ATTRIBUTES,
    "polygon": {"points"} | SVG_PAINT_ATTRIBUTES,
    "text": {"dominant-baseline", "dx", "dy", "font-size", "font-weight", "text-anchor", "x", "y"} | SVG_PAINT_ATTRIBUTES,
    "tspan": {"dx", "dy", "x", "y"} | SVG_PAINT_ATTRIBUTES,
    "lineargradient": {"gradienttransform", "gradientunits", "spreadmethod", "x1", "x2", "y1", "y2"},
    "radialgradient": {"cx", "cy", "fr", "fx", "fy", "gradienttransform", "gradientunits", "r", "spreadmethod"},
    "stop": {"offset", "stop-color", "stop-opacity"},
    "clippath": {"clippathunits", "transform"},
}
SAFE_META_NAMES = {"color-scheme", "description", "robots", "theme-color", "viewport"}
PAGE_CSP_DIRECTIVES = {
    "base-uri": "'none'",
    "connect-src": "'none'",
    "default-src": "'none'",
    "font-src": "data:",
    "form-action": "'none'",
    "frame-src": "'none'",
    "img-src": "data:",
    "media-src": "'none'",
    "object-src": "'none'",
    "script-src": "'unsafe-inline'",
    "script-src-attr": "'none'",
    "style-src": "'unsafe-inline'",
    "worker-src": "'none'",
}
THEME_RUNTIME_SHA256 = "af780b3803d0086a11dd371dd4ab032a311c9fd4ad02695953a86d815a0ad3a3"
SAFE_DATA_IMAGE = re.compile(r"data:image/(?:gif|jpeg|png|webp);base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
SAFE_DATA_FONT = re.compile(
    r"url\(\s*(?P<quote>['\"]?)data:font/woff2;base64,"
    r"(?P<payload>[A-Za-z0-9+/]+={0,2})(?P=quote)\s*\)",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_|github_pat_|glpat-|hf_|npm_|xox[baprs]-)[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\b(?:sk-(?:proj-|ant-)?|sk_live_)[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:/]+:[^\s/@]{8,}@"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{16,}"
    ),
)


class PageRejected(ValueError):
    pass


class PublishFailed(RuntimeError):
    pass


class UploadUncertain(PublishFailed):
    pass


class PagexConfigError(ValueError):
    pass


def _mask_embedded_woff2(css: str) -> str:
    def validate(match: re.Match[str]) -> str:
        try:
            font = base64.b64decode(match.group("payload"), validate=True)
        except (binascii.Error, ValueError) as error:
            raise PageRejected("embedded WOFF2 font is not valid base64") from error
        if not font.startswith(b"wOF2"):
            raise PageRejected("embedded font must use WOFF2 data")
        return "embedded-woff2"

    return SAFE_DATA_FONT.sub(validate, css)


def _is_offline_csp(content: str) -> bool:
    directives: dict[str, str] = {}
    for raw_directive in content.split(";"):
        parts = raw_directive.split()
        if not parts:
            continue
        name = parts[0].lower()
        if name in directives:
            return False
        directives[name] = " ".join(parts[1:])
    return directives == PAGE_CSP_DIRECTIVES


@dataclass(frozen=True)
class PagexConfig:
    bucket: str
    base_url: str
    data_dir: Path
    wrangler: str


def _expand_path(value: str, home: Path) -> Path:
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    return Path(value)


def _absolute_env_path(environ: Mapping[str, str], name: str, fallback: Path) -> Path:
    value = environ.get(name, "")
    path = Path(value) if value else fallback
    return path if path.is_absolute() else fallback


def _config_path(environ: Mapping[str, str], home: Path) -> Path:
    if configured := environ.get("PAGEX_CONFIG"):
        return _expand_path(configured, home)
    config_home = _absolute_env_path(environ, "XDG_CONFIG_HOME", home / ".config")
    return config_home / "pagex" / "config.toml"


def _read_config(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PagexConfigError(f"could not read config {path}: {error}") from error
    unknown = sorted(set(values) - CONFIG_KEYS)
    if unknown:
        raise PagexConfigError(f"unknown config key: {unknown[0]}")
    for key, value in values.items():
        if not isinstance(value, str):
            raise PagexConfigError(f"config value {key} must be a string")
    return values


def _parse_base_url(value: str) -> str:
    message = "base_url must be an HTTPS origin without a path, query or fragment"
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise PagexConfigError(message)
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise PagexConfigError(message) from error

    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise PagexConfigError(message)

    try:
        authority = hostname.encode("idna").decode("ascii").lower()
        labels = authority.split(".")
        if len(authority) > 253 or not all(
            HOST_LABEL_PATTERN.fullmatch(label) for label in labels
        ):
            raise ValueError("invalid hostname")
        if labels[-1].isdigit():
            raise ValueError("numeric top-level label")
        for label in labels:
            if label.startswith("xn--"):
                decoded = label.encode("ascii").decode("idna")
                if decoded.encode("idna").decode("ascii").lower() != label:
                    raise ValueError("invalid IDNA label")
    except (UnicodeError, ValueError) as error:
        raise PagexConfigError(message) from error

    if port is not None:
        authority = f"{authority}:{port}"
    return f"https://{authority}"


def load_config(environ: Mapping[str, str] | None = None) -> PagexConfig:
    environ = os.environ if environ is None else environ
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    home = _absolute_env_path(environ, "HOME", account_home)
    path = _config_path(environ, home)
    values = _read_config(path)

    bucket = environ.get("PAGEX_BUCKET", values.get("bucket", "")).strip()
    base_url = environ.get("PAGEX_BASE_URL", values.get("base_url", "")).strip()
    missing = [name for name, value in (("bucket", bucket), ("base_url", base_url)) if not value]
    if missing:
        names = ", ".join(missing)
        raise PagexConfigError(
            f"missing required configuration: {names}; add them to {path} "
            "or set PAGEX_BUCKET and PAGEX_BASE_URL"
        )
    if not R2_BUCKET_PATTERN.fullmatch(bucket):
        raise PagexConfigError(
            "bucket must be 3-63 lowercase letters, numbers or hyphens "
            "and cannot begin or end with a hyphen"
        )

    base_url = _parse_base_url(base_url)

    data_home = _absolute_env_path(environ, "XDG_DATA_HOME", home / ".local" / "share")
    data_dir_value = environ.get("PAGEX_DATA_DIR", values.get("data_dir", ""))
    data_dir = _expand_path(data_dir_value, home) if data_dir_value else data_home / "pagex"
    if not data_dir.is_absolute():
        raise PagexConfigError("data_dir must be an absolute path or begin with ~/")
    wrangler = environ.get("PAGEX_WRANGLER", values.get("wrangler", "wrangler")).strip()
    if not wrangler:
        raise PagexConfigError("wrangler must not be empty")

    return PagexConfig(
        bucket=bucket,
        base_url=base_url,
        data_dir=data_dir,
        wrangler=wrangler,
    )


def generate_page_id() -> str:
    return "".join(secrets.choice(PAGE_ID_ALPHABET) for _ in range(PAGE_ID_LENGTH))


@dataclass(frozen=True)
class PageInspection:
    title: str
    text_length: int


@dataclass(frozen=True)
class PublishResult:
    page_id: str
    url: str
    local_path: Path


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.in_head = False
        self.in_style = False
        self.in_script = False
        self.in_button = False
        self.button_has_accessible_name = False
        self.button_text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.css_parts: list[str] = []
        self.current_script_parts: list[str] = []
        self.scripts: list[str] = []
        self.text_length = 0
        self.has_html = False
        self.has_head = False
        self.has_body = False
        self.has_page_csp = False
        self.violations: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        names = [name.lower() for name, _ in attrs]
        if len(names) != len(set(names)):
            self.violations.append(f"duplicate attributes on <{tag}>")
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag not in ALLOWED_TAGS:
            self.violations.append(f"element <{tag}> is outside the Pagex boundary")
        allowed_attributes = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, set())
        for name in attributes:
            if name.startswith("on"):
                self.violations.append(f"event attribute {name} is not allowed")
            elif not (name in allowed_attributes or name.startswith("aria-") or name.startswith("data-")):
                self.violations.append(f"attribute {name} on <{tag}> is not allowed")
        if tag == "html":
            if self.has_html:
                self.violations.append("page must contain only one html element")
            self.has_html = True
        elif tag == "head":
            if self.has_head or self.has_body:
                self.violations.append("head element must appear once before body")
            self.has_head = True
            self.in_head = True
        elif tag == "body":
            if self.has_body or not self.has_head or self.in_head:
                self.violations.append("body element must appear once after head")
            self.has_body = True
        elif tag == "title":
            self.in_title = self.in_head
        elif tag == "style":
            self.in_style = True
        elif tag == "script":
            self.in_script = True
            self.current_script_parts = []
            if not self.has_page_csp:
                self.violations.append(
                    "offline content security policy must appear before the first script"
                )
            if attributes.get("data-pagex", "") != "theme":
                self.violations.append("inline scripts must use the bundled theme runtime")
        elif tag == "button":
            self.in_button = True
            self.button_text_parts = []
            self.button_has_accessible_name = bool(
                attributes.get("aria-label", "").strip()
                or attributes.get("aria-labelledby", "").strip()
            )

        inline_style = attributes.get("style", "").strip()
        if inline_style:
            self.css_parts.append(inline_style)

        if tag in SVG_TAGS:
            for value in attributes.values():
                compact = re.sub(r"\s+", "", value)
                if "url(" in compact.lower() and not re.fullmatch(r"url\(#[A-Za-z][\w.-]*\)", compact):
                    self.violations.append("SVG resource URLs must be local fragment references")
                if re.search(r"(?i)(?:https?|data|file|ftp|javascript):|//", value):
                    self.violations.append("external or executable SVG values are not allowed")

        if tag == "a" and "href" in attributes:
            href = re.sub(r"[\x00-\x20]+", "", attributes["href"]).lower()
            if not (href.startswith(("#", "https://", "http://", "mailto:"))):
                self.violations.append("anchor URL scheme is not allowed")
        if tag == "img":
            source = attributes.get("src", "")
            if not SAFE_DATA_IMAGE.fullmatch(source):
                self.violations.append("images must be embedded raster data URLs")
        if tag == "button" and attributes.get("type", "").lower() != "button":
            self.violations.append("buttons must use type button")
        if tag == "meta":
            http_equiv = attributes.get("http-equiv", "").lower()
            name = attributes.get("name", "").lower()
            if not self.in_head:
                self.violations.append("meta elements must appear inside head")
            if http_equiv:
                if http_equiv != "content-security-policy":
                    self.violations.append(f"meta http-equiv {http_equiv} is not allowed")
                elif self.has_page_csp:
                    self.violations.append("content security policy must not be repeated")
                elif not _is_offline_csp(attributes.get("content", "")):
                    self.violations.append(
                        "content security policy must match the Pagex offline policy"
                    )
                else:
                    self.has_page_csp = True
                if name or "charset" in attributes:
                    self.violations.append(
                        "content security policy meta cannot also declare name or charset"
                    )
            elif name and name not in SAFE_META_NAMES:
                self.violations.append(f"meta name {name} is not allowed")
            if "content" in attributes and not (name or http_equiv):
                self.violations.append("meta content requires an allowed name")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "head":
            self.in_head = False
        elif tag == "title":
            self.in_title = False
        elif tag == "style":
            self.in_style = False
        elif tag == "script":
            self.in_script = False
            self.scripts.append("".join(self.current_script_parts))
            self.current_script_parts = []
        elif tag == "button":
            if not self.button_has_accessible_name and not "".join(
                self.button_text_parts
            ).strip():
                self.violations.append("buttons require an accessible name")
            self.in_button = False
            self.button_has_accessible_name = False
            self.button_text_parts = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self.in_button:
            self.button_text_parts.append(data)
        if self.in_title:
            self.title_parts.append(text)
        elif self.in_style:
            self.css_parts.append(data)
        elif self.in_script:
            self.current_script_parts.append(data)
        else:
            self.text_length += len(text)


def inspect_html(data: bytes) -> PageInspection:
    if len(data) > MAX_PAGE_BYTES:
        raise PageRejected("page exceeds the 2 MiB v0 limit")
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PageRejected("page must be UTF-8") from error
    doctype = re.match(r"\s*<!doctype\s+html\s*>", source, re.IGNORECASE)
    if not doctype:
        raise PageRejected("missing HTML5 doctype")
    if "<!" in source[doctype.end():] or "<?" in source[doctype.end():]:
        raise PageRejected("HTML comments, declarations and processing instructions are not allowed")
    for pattern in SECRET_PATTERNS:
        if pattern.search(source):
            raise PageRejected("possible credential detected")

    parser = _PageParser()
    parser.feed(source)
    if not (parser.has_html and parser.has_head and parser.has_body):
        raise PageRejected("page must contain html, head and body elements")
    if len(parser.scripts) > 1:
        parser.violations.append("pages may contain only one bundled theme script")
    for javascript in parser.scripts:
        if not javascript.strip():
            parser.violations.append("inline scripts cannot be empty")
        elif hashlib.sha256(javascript.encode()).hexdigest() != THEME_RUNTIME_SHA256:
            parser.violations.append("Pagex theme runtime must match the audited template")
    if parser.violations:
        raise PageRejected(parser.violations[0])
    css = _mask_embedded_woff2("\n".join(parser.css_parts))
    if (
        "\\" in css
        or re.search(r"(?i)(?:https?|data|file|ftp):|//|(?:-webkit-)?image-set\s*\(", css)
        or re.search(
            r"@import\b|\burl\s*\(|\bexpression\s*\(|"
            r"(?:^|[;{])\s*(?:behavior|-moz-binding)\s*:",
            css,
            re.IGNORECASE,
        )
    ):
        raise PageRejected("CSS resource or executable construct is not allowed")
    if not parser.title_parts:
        raise PageRejected("page must contain a title")
    if parser.text_length == 0:
        raise PageRejected("page body is empty")
    return PageInspection(title=" ".join(parser.title_parts), text_length=parser.text_length)


def inspect_page(path: Path) -> PageInspection:
    return inspect_html(_read_page(path))


def _read_page(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_PAGE_BYTES:
            raise PageRejected("page exceeds the 2 MiB v0 limit")
        return path.read_bytes()
    except OSError as error:
        raise PageRejected(f"could not read page: {error.strerror or error}") from error


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)


def _atomic_write(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        temporary.chmod(0o600)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            _safe_unlink(temporary)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with path.open("a+", encoding="utf-8") as handle:
        path.chmod(0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


@dataclass
class PagexPublisher:
    bucket: str
    base_url: str
    data_dir: Path
    wrangler: str
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _run_command

    def _upload(self, page_id: str, path: Path) -> None:
        command = [
            self.wrangler,
            "r2",
            "object",
            "put",
            f"{self.bucket}/{page_id}",
            "--file",
            str(path),
            "--content-type",
            "text/html; charset=utf-8",
            "--cache-control",
            "private, no-store",
            "--remote",
        ]
        try:
            completed = self.runner(command)
        except subprocess.TimeoutExpired as error:
            raise UploadUncertain(
                f"upload outcome unknown for {page_id}; local page kept; retry with pagex update"
            ) from error
        except Exception as error:
            raise PublishFailed(f"Wrangler invocation failed: {error}") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "Wrangler failed"
            raise PublishFailed(detail)

    def _result(self, page_id: str, local_path: Path) -> PublishResult:
        return PublishResult(
            page_id=page_id,
            url=f"{self.base_url.rstrip('/')}/{page_id}",
            local_path=local_path,
        )

    def publish(
        self,
        source: Path,
        *,
        id_factory: Callable[[], str] = generate_page_id,
    ) -> PublishResult:
        data = _read_page(source)
        inspect_html(data)
        with _exclusive_lock(self.data_dir / ".pagex.lock"):
            pages_dir = self.data_dir / "pages"
            for _ in range(16):
                page_id = id_factory()
                if len(page_id) != PAGE_ID_LENGTH or not PAGE_ID_PATTERN.fullmatch(page_id):
                    raise PublishFailed("invalid generated page ID")
                local_path = pages_dir / f"{page_id}.html"
                if not local_path.exists():
                    break
            else:
                raise PublishFailed("could not generate an unused page ID")

            _atomic_write(data, local_path)
            try:
                self._upload(page_id, local_path)
            except UploadUncertain:
                raise
            except PublishFailed as upload_error:
                try:
                    local_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    raise PublishFailed(
                        f"{upload_error}; cleanup failed for {page_id}; "
                        f"local page kept at {local_path}"
                    ) from cleanup_error
                raise
            return self._result(page_id, local_path)

    def update(self, page_id: str, source: Path) -> PublishResult:
        if len(page_id) != PAGE_ID_LENGTH or not PAGE_ID_PATTERN.fullmatch(page_id):
            raise PublishFailed("invalid page ID")
        data = _read_page(source)
        inspect_html(data)
        with _exclusive_lock(self.data_dir / ".pagex.lock"):
            local_path = self.data_dir / "pages" / f"{page_id}.html"
            if not local_path.exists():
                raise PublishFailed(f"local page not found: {page_id}")

            previous = local_path.read_bytes()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            backup_path = self.data_dir / "versions" / page_id / f"{timestamp}.html"
            _atomic_write(previous, backup_path)
            _atomic_write(data, local_path)
            try:
                self._upload(page_id, local_path)
            except UploadUncertain:
                raise
            except PublishFailed:
                _atomic_write(previous, local_path)
                raise
            return self._result(page_id, local_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pagex",
        description="verify and publish private static answer pages",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="validate an HTML file")
    check.add_argument("file", type=Path)
    publish = commands.add_parser("publish", help="publish a new page with a unique URL")
    publish.add_argument("file", type=Path)
    update = commands.add_parser("update", help="replace a page while preserving its URL")
    update.add_argument("page_id")
    update.add_argument("file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "check":
            inspection = inspect_page(arguments.file)
            print(f"ok: {inspection.title}")
            return 0

        config = load_config()
        publisher = PagexPublisher(
            bucket=config.bucket,
            base_url=config.base_url,
            data_dir=config.data_dir,
            wrangler=config.wrangler,
        )
        if arguments.command == "publish":
            result = publisher.publish(arguments.file)
        else:
            result = publisher.update(arguments.page_id, arguments.file)
        print(result.url)
        return 0
    except (FileNotFoundError, PageRejected, PagexConfigError, PublishFailed) as error:
        print(f"pagex: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
