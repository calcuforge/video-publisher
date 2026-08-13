"""
CDP / Playwright helpers for headed-browser automation with human-in-the-loop
(human-collab) support.

Design rules:
- The browser is ALWAYS a headed (有头) Chromium, reached via its CDP debug
  port (`--remote-debugging-port=9222`). A user watching through VNC sees every
  step and can complete login / captcha / SMS tasks by hand.
- Any step that may need a human (login, captcha, verification, risky click)
  must use the blocking `human_wait_*` helpers below. They print a VNC hint to
  stdout (JSON envelope lines) and POLL until the condition is met or the
  timeout expires. The agent relays the hint to the user and waits.
- All progress is printed as JSON envelope lines (one per line, prefixed
  `@ENV@`) so the calling agent can parse state machine output reliably.

The script must be run with the playwright package installed
(`pip install -r requirements.txt` + `playwright install chromium`).
"""

from __future__ import annotations

import json
import socket
import sys
import time
from typing import Callable, Optional

try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover - fail later with a clear message
    Page = None  # type: ignore
    PlaywrightTimeoutError = Exception


def env_out(status: str, msg: str, **data) -> None:
    """Print a machine-readable JSON envelope line (prefixed @ENV@)."""
    line = json.dumps(
        {"env_status": status, "msg": msg, "data": data},
        ensure_ascii=False,
    )
    print(f"@ENV@ {line}", flush=True)


def human_hint(desc: str, condition: str = "") -> None:
    """Print the standard human-collab hint. Agents must relay this to the user."""
    cond = f"（脚本将阻塞等待，直到检测到：{condition}）" if condition else ""
    env_out(
        "human_collab",
        f"⚠ 需要用户通过 VNC 配合：{desc}{cond}",
        action="vnc",
        condition=condition,
    )


def check_cdp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """True if a browser is listening on the CDP port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def connect_browser(cdp_url: str):
    """Connect to a headed browser via its CDP endpoint.

    Returns a playwright Browser object. The browser must already be running
    headed with --remote-debugging-port (see human-collab.md for launch
    instructions). Raises RuntimeError with a VNC hint if unreachable.
    """
    if Page is None:
        raise RuntimeError("playwright not installed. Run: pip install -r requirements.txt")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed. Run: pip install -r requirements.txt")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                f"无法通过 CDP 连接到有头浏览器 {cdp_url}: {exc}\n"
                f"请先启动有头浏览器并开启调试端口，参见 references/human-collab.md"
            )
        return browser


def new_page(browser, url: str = "") -> Page:
    """Open a fresh tab. Prefers an incognito-less new context in the SAME
    browser so the user's logged-in cookies are reused."""
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    if url:
        page.goto(url, wait_until="domcontentloaded")
    return page


def human_wait(
    page: Page,
    desc: str,
    condition: Callable[[Page], bool],
    timeout: int = 600,
    poll: float = 3.0,
    condition_desc: str = "",
) -> None:
    """Block and poll until `condition(page)` is True.

    Prints a human-collab hint once, then a heartbeat every 30s. Raises
    RuntimeError after `timeout` seconds. Use for login / captcha / SMS waits.
    """
    human_hint(desc, condition_desc or "页面状态满足条件")
    deadline = time.monotonic() + timeout
    last_heartbeat = time.monotonic()
    while time.monotonic() < deadline:
        try:
            if condition(page):
                env_out("human_collab_done", f"人工介入完成：{desc}")
                return
        except Exception:
            pass  # page mid-navigation etc. — keep polling
        if time.monotonic() - last_heartbeat > 30:
            last_heartbeat = time.monotonic()
            env_out("human_collab_waiting", f"仍在等待人工介入：{desc}（已等待 {int(time.monotonic() + timeout - deadline)}s）")
        time.sleep(poll)
    raise RuntimeError(f"人工介入超时（{timeout}s）：{desc}")


def human_wait_url(page: Page, desc: str, url_contains: str, timeout: int = 600) -> None:
    """Block until the page URL contains `url_contains` (e.g. logged-in page)."""
    human_wait(
        page, desc,
        lambda p: url_contains in (p.url or ""),
        timeout=timeout,
        condition_desc=f"URL 包含 {url_contains}",
    )


def human_wait_selector(page: Page, desc: str, selector: str, timeout: int = 600) -> None:
    """Block until `selector` is visible on the page (e.g. upload form loaded)."""
    human_wait(
        page, desc,
        lambda p: p.locator(selector).count() > 0 and p.locator(selector).first.is_visible(),
        timeout=timeout,
        condition_desc=f"元素可见 {selector}",
    )


def fill_text(page: Page, selector: str, value: str) -> bool:
    """Fill a text field by CSS selector. Returns False if not found."""
    loc = page.locator(selector)
    if loc.count() == 0 or not loc.first.is_visible():
        return False
    loc.first.fill(value)
    return True


def fill_by_placeholder(page: Page, placeholder: str, value: str) -> bool:
    """Fill the first visible input whose placeholder contains `placeholder`."""
    loc = page.locator(f"input[placeholder*='{placeholder}'], textarea[placeholder*='{placeholder}']")
    for i in range(loc.count()):
        el = loc.nth(i)
        if el.is_visible():
            el.fill(value)
            return True
    return False


def fill_by_label(page: Page, label: str, value: str) -> bool:
    """Fill the input visually associated with a label text.

    Tries, in order: explicit <label for>, input inside <label>, and the first
    visible input/textarea in the same row/container as the label text.
    """
    try:
        loc = page.get_by_label(label, exact=False).first
        if loc.count() > 0:
            loc.fill(value)
            return True
    except Exception:
        pass
    text = page.get_by_text(label, exact=False).first
    if text.count() > 0:
        container = text.locator("xpath=ancestor::*[self::div or self::li or self::form][1]")
        if container.count() > 0:
            inp = container.locator("input, textarea").first
            if inp.count() > 0:
                inp.fill(value)
                return True
    return False


def click_by_text(page: Page, text: str) -> bool:
    """Click the first visible element whose text contains `text`."""
    loc = page.get_by_text(text, exact=False)
    for i in range(loc.count()):
        try:
            if loc.nth(i).is_visible():
                loc.nth(i).click()
                return True
        except Exception:
            continue
    return False


def click_by_selector(page: Page, selector: str) -> bool:
    """Click the first visible element matching `selector`."""
    loc = page.locator(selector)
    for i in range(loc.count()):
        try:
            if loc.nth(i).is_visible():
                loc.nth(i).click()
                return True
        except Exception:
            continue
    return False


def select_by_text(page: Page, selector: str, option_text: str) -> bool:
    """Select an <option> by visible text inside a <select>."""
    loc = page.locator(selector)
    if loc.count() == 0 or not loc.first.is_visible():
        return False
    try:
        loc.first.select_option(label=option_text)
        return True
    except Exception:
        try:
            loc.first.select_option(option_text)
            return True
        except Exception:
            return False


def upload_file(page: Page, selector: str, file_path: str) -> bool:
    """Upload a file through an <input type=file>.

    If `selector` does not match, falls back to any visible file input on the
    page. Raises RuntimeError if no file input exists (a human may need to
    click the real upload button — use human_wait_selector around it instead).
    """
    if selector:
        loc = page.locator(selector)
        if loc.count() > 0:
            loc.first.set_input_files(file_path)
            return True
    fallback = page.locator("input[type=file]")
    for i in range(fallback.count()):
        el = fallback.nth(i)
        if el.is_visible() or el.count() > 0:
            el.set_input_files(file_path)
            return True
    raise RuntimeError(f"页面没有找到可用的文件上传控件（selector={selector or 'auto'}），"
                       f"可能需要人工通过 VNC 点击上传按钮，或修正脚本中的上传逻辑")


def screenshot(page: Page, path: str) -> None:
    """Save a full-page screenshot (for the agent to inspect)."""
    page.screenshot(path=path, full_page=True)


def dump_page(page: Page) -> dict:
    """Extract the structural skeleton of the current page: URL, title,
    iframes, and every interactive element (input/textarea/select/file/button)
    with its attributes. Used by probe_page.py to feed DOM analysis."""
    def _attrs(el) -> dict:
        return {
            "tag": el.evaluate("e => e.tagName.toLowerCase()"),
            "name": el.get_attribute("name") or "",
            "id": el.get_attribute("id") or "",
            "type": el.get_attribute("type") or "",
            "placeholder": el.get_attribute("placeholder") or "",
            "class": (el.get_attribute("class") or "")[:120],
            "label": _near_label(el),
        }

    def _near_label(el) -> str:
        try:
            for anc in el.evaluate("""e => {
                const walk = [];
                let n = e.parentElement;
                for (let i = 0; n && i < 6; i++, n = n.parentElement) walk.push(n);
                return walk.map(x => x.tagName.toLowerCase());
            }"""):
                pass
            text = el.evaluate("""e => {
                let n = e.parentElement;
                for (let i = 0; n && i < 6; i++, n = n.parentElement) {
                    const t = n.innerText || '';
                    const lines = t.split('\\n').filter(x => x.trim());
                    for (const ln of lines) {
                        if (ln.trim().length < 30) return ln.trim();
                    }
                }
                return '';
            }""")
            return (text or "")[:40]
        except Exception:
            return ""

    result: dict = {
        "url": page.url,
        "title": page.title(),
        "frames": [],
        "elements": [],
    }
    for frame in page.frames:
        entry = {"name": frame.name or "", "url": (frame.url or "")[:200], "elements": []}
        try:
            for tag in ("input", "textarea", "select", "button", "a"):
                els = frame.locator(tag)
                for i in range(min(els.count(), 200)):
                    el = els.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                    except Exception:
                        continue
                    attrs = _attrs(el) if tag != "a" else {
                        "tag": "a",
                        "text": (el.inner_text() or "")[:40],
                        "href": el.get_attribute("href") or "",
                    }
                    entry["elements"].append(attrs)
        except Exception:
            pass
        result["frames"].append(entry)
    return result
