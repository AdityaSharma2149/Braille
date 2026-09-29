"""
Real browser tests (Playwright + Chromium) for the accessible web front-end.

These exercise what a screen-reader/keyboard-only user actually experiences:
landmarks, focus movement, live-region announcements, and keyboard shortcuts
-- not just "does the page return 200".
"""
import threading

import pytest
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp import Handler

playwright_sync = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


# ---------------------------------------------------------------------------
# Landmarks, skip link, focus management
# ---------------------------------------------------------------------------
def test_page_has_main_landmark_and_skip_link(page, server_url):
    page.goto(f"{server_url}/index.html")
    assert page.title() == "GanitDrishti — Solve a Math Question"
    main = page.locator("main#main")
    assert main.count() == 1
    assert main.get_attribute("tabindex") == "-1"
    skip_link = page.locator("a.skip-link")
    assert skip_link.get_attribute("href") == "#main"


def test_skip_link_moves_focus_to_main(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.keyboard.press("Tab")  # first focusable element should be the skip link
    focused_text = page.evaluate("document.activeElement.textContent")
    assert "Skip to main content" in focused_text
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    is_main_focused = page.evaluate("document.activeElement.id === 'main'")
    assert is_main_focused


def test_all_buttons_are_real_button_elements(page, server_url):
    """Screen readers need real <button>, not clickable <div>s."""
    page.goto(f"{server_url}/index.html")
    fake_buttons = page.locator("div[onclick], span[onclick]").count()
    assert fake_buttons == 0


def test_every_form_control_has_a_label(page, server_url):
    page.goto(f"{server_url}/index.html")
    unlabeled = page.evaluate(
        """
        () => {
          const controls = document.querySelectorAll('input, select, textarea');
          let bad = [];
          controls.forEach(el => {
            const id = el.id;
            const hasLabel = id && document.querySelector(`label[for="${id}"]`);
            const hasAriaLabel = el.getAttribute('aria-label');
            const wrappedInLabel = el.closest('label');
            if (!hasLabel && !hasAriaLabel && !wrappedInLabel) bad.push(el.outerHTML);
          });
          return bad;
        }
        """
    )
    assert unlabeled == [], f"Unlabeled controls: {unlabeled}"


# ---------------------------------------------------------------------------
# Keyboard shortcuts
# ---------------------------------------------------------------------------
def test_alt_2_switches_to_voice_panel(page, server_url):
    page.goto(f"{server_url}/index.html")
    assert page.locator("#panel-voice").is_hidden()
    page.keyboard.press("Alt+2")
    page.wait_for_timeout(50)
    assert page.locator("#panel-voice").is_visible()
    assert page.locator("#panel-type").is_hidden()


def test_alt_3_switches_to_image_panel(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.keyboard.press("Alt+3")
    page.wait_for_timeout(50)
    assert page.locator("#panel-image").is_visible()


def test_alt_1_switches_back_to_type_panel(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.keyboard.press("Alt+2")
    page.keyboard.press("Alt+1")
    page.wait_for_timeout(50)
    assert page.locator("#panel-type").is_visible()


def _ask_and_solve(page, question):
    """Drive the 3-step wizard: Step 1 (ask) -> Step 2 (language/solve) -> Step 3 (result)."""
    page.fill("#question-text", question)
    page.click("#step1-continue")
    page.wait_for_selector("#step-2:not([hidden])", timeout=5000)
    page.click("#solve-btn")
    page.wait_for_selector("#step-3:not([hidden])", timeout=15000)


def test_wizard_steps_are_mutually_exclusive(page, server_url):
    """Only one step should ever be visible at a time (the 'no scrolling' design)."""
    page.goto(f"{server_url}/index.html")
    assert page.locator("#step-1").is_visible()
    assert page.locator("#step-2").is_hidden()
    assert page.locator("#step-3").is_hidden()
    assert "Step 1 of 3" in page.locator("#step-indicator").inner_text()


def test_step1_continue_blocks_on_empty_question(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.click("#step1-continue")
    page.wait_for_timeout(200)
    assert page.locator("#step-1").is_visible()
    assert page.locator("#step-2").is_hidden()
    error_box = page.locator("#step1-error")
    assert error_box.is_visible()
    assert error_box.get_attribute("role") == "alert"
    assert "before continuing" in error_box.inner_text()


def test_step1_continue_advances_to_step2(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.fill("#question-text", "2*x + 3 = 11")
    page.click("#step1-continue")
    page.wait_for_selector("#step-2:not([hidden])", timeout=5000)
    assert page.locator("#step-1").is_hidden()
    assert "Step 2 of 3" in page.locator("#step-indicator").inner_text()


def test_step2_back_returns_to_step1_with_question_kept(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.fill("#question-text", "2*x + 3 = 11")
    page.click("#step1-continue")
    page.wait_for_selector("#step-2:not([hidden])", timeout=5000)
    page.click("#step2-back")
    page.wait_for_selector("#step-1:not([hidden])", timeout=5000)
    assert page.input_value("#question-text") == "2*x + 3 = 11"


def test_alt_s_advances_then_solves_across_steps(page, server_url):
    """Alt+S is context-sensitive: Continue on step 1, Solve on step 2."""
    page.goto(f"{server_url}/index.html")
    page.fill("#question-text", "2*x + 3 = 11")
    page.keyboard.press("Alt+S")
    page.wait_for_selector("#step-2:not([hidden])", timeout=5000)
    page.keyboard.press("Alt+S")
    page.wait_for_selector("#step-3:not([hidden])", timeout=15000)
    engine_text = page.locator("#engine-badge").inner_text()
    assert "Verified" in engine_text
    result_text = page.locator("#result-text").inner_text()
    assert "x = 4" in result_text


def test_solved_result_receives_keyboard_focus(page, server_url):
    """A screen-reader user should not have to hunt for the answer."""
    page.goto(f"{server_url}/index.html")
    _ask_and_solve(page, "sqrt(16) + 9")
    is_result_focused = page.evaluate("document.activeElement.id === 'result-block'")
    assert is_result_focused


def test_ask_another_question_resets_to_step1(page, server_url):
    page.goto(f"{server_url}/index.html")
    _ask_and_solve(page, "2*x + 3 = 11")
    page.click("#ask-another-btn")
    page.wait_for_selector("#step-1:not([hidden])", timeout=5000)
    assert page.input_value("#question-text") == ""
    assert "Step 1 of 3" in page.locator("#step-indicator").inner_text()


# ---------------------------------------------------------------------------
# Live-region correctness (errors must interrupt, not queue politely)
# ---------------------------------------------------------------------------
def test_empty_question_error_uses_alert_role(page, server_url):
    """Step 1's own guard (role="alert") is what a user actually hits now --
    Step 2's Solve button is unreachable without a question already set."""
    page.goto(f"{server_url}/index.html")
    page.click("#step1-continue")
    page.wait_for_timeout(200)
    error_box = page.locator("#step1-error")
    assert error_box.get_attribute("role") == "alert"
    assert error_box.is_visible()


def test_success_status_uses_polite_live_region(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.fill("#question-text", "3 + 4")
    page.click("#step1-continue")
    page.wait_for_selector("#step-2:not([hidden])", timeout=5000)
    page.click("#solve-btn")
    page.wait_for_selector("#step-3:not([hidden])", timeout=15000)
    status = page.locator("#result-status")
    assert status.get_attribute("aria-live") == "polite"


# ---------------------------------------------------------------------------
# History and Read Again
# ---------------------------------------------------------------------------
def test_history_records_solved_questions(page, server_url):
    page.goto(f"{server_url}/index.html")
    _ask_and_solve(page, "2*x + 3 = 11")
    page.click("#toggle-history-btn")
    page.wait_for_selector(".history-item", timeout=5000)
    history_items = page.locator(".history-item")
    assert history_items.count() == 1
    assert "2*x + 3 = 11" in history_items.first.inner_text()


def test_read_again_button_present_after_solving(page, server_url):
    page.goto(f"{server_url}/index.html")
    _ask_and_solve(page, "2*x + 3 = 11")
    assert page.locator("#read-again-btn").is_visible()


# ---------------------------------------------------------------------------
# Display settings persistence
# ---------------------------------------------------------------------------
def _scroll_overflow_px(page):
    """How many px taller the document is than the viewport (0 = no scroll needed)."""
    return page.evaluate(
        "Math.max(0, document.documentElement.scrollHeight - window.innerHeight)"
    )


@pytest.mark.parametrize(
    "width,height,label",
    [
        (1280, 800, "laptop"),
        (768, 1024, "tablet"),
        (375, 812, "phone"),
        (375, 667, "small phone (iPhone SE)"),
    ],
)
def test_step1_fits_viewport_without_scrolling(page, server_url, width, height, label):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{server_url}/index.html")
    overflow = _scroll_overflow_px(page)
    assert overflow <= 4, f"Step 1 needs {overflow}px of scrolling on {label} ({width}x{height})"


@pytest.mark.parametrize("width,height,label", [(1280, 800, "laptop"), (375, 812, "phone")])
def test_step3_result_fits_viewport_without_scrolling(page, server_url, width, height, label):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{server_url}/index.html")
    _ask_and_solve(page, "2*x + 3 = 11")
    overflow = _scroll_overflow_px(page)
    assert overflow <= 4, f"Step 3 needs {overflow}px of scrolling on {label} ({width}x{height})"


def _is_visible_at_current_scroll(page, selector):
    """True if the element's box is actually within the current viewport
    (not just present in the DOM with display != none)."""
    rect = page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect()")
    return rect["bottom"] > 0 and rect["top"] < page.viewport_size["height"] and rect["width"] > 0


@pytest.mark.parametrize("width,height,label", [(1280, 800, "laptop"), (375, 812, "phone"), (375, 667, "small phone")])
def test_step_content_starts_visible_not_centered_off_top(page, server_url, width, height, label):
    """Regression test for a real bug: `justify-content: center` on a flex
    column whose content can overflow makes browsers hide the START of the
    content first (confirmed by screenshot: the Quick Ask heading and
    button were completely invisible and unreachable by scrolling). The
    fix is `justify-content: safe center`. On fresh page load (scrollTop
    is 0 by default), the step's own heading -- its first child -- must
    actually be on screen, not scrolled away before the user does anything."""
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{server_url}/index.html")
    assert _is_visible_at_current_scroll(page, "#step1-heading"), (
        f"Step 1 heading is not visible on load at {width}x{height} ({label}) -- "
        "content is being centered off the top of an overflowing container."
    )
    # The Quick Ask button (the very first interactive control) must be
    # reachable too, not just the heading above it.
    assert _is_visible_at_current_scroll(page, "#quick-ask-btn") or _scroll_overflow_px(page) == 0, (
        f"Quick Ask button is not visible on load at {width}x{height} ({label})."
    )


def test_topbar_first_button_visible_on_load(page, server_url):
    """Same bug class, horizontal: a scrollable single-row toolbar centered
    with plain `justify-content: center` starts scrolled to the MIDDLE of
    its overflow, hiding the first (and last) buttons. Confirmed by
    screenshot on a 375px-wide phone: only the "A" button was visible,
    with Dark Mode/A-/A+/Read Aloud scrolled out of reach on both sides."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{server_url}/index.html")
    scroll_left = page.evaluate("document.querySelector('.topbar').scrollLeft")
    assert scroll_left == 0, f"Topbar starts scrolled {scroll_left}px from the left -- first button(s) are hidden."


def test_larger_text_size_does_not_break_layout(page, server_url):
    """Bumping text size must not hide content -- it may need scroll, but
    nothing may become inaccessible (that would violate WCAG Reflow)."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{server_url}/index.html")
    for _ in range(4):
        page.click("#font-bigger")
    page.wait_for_timeout(100)
    # The primary action must still be present and clickable even if the
    # step now needs to scroll internally at this larger text size.
    assert page.locator("#step1-continue").is_visible()


def test_theme_toggle_switches_and_persists(page, server_url):
    page.goto(f"{server_url}/index.html")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"
    page.click("#theme-toggle")
    page.wait_for_timeout(50)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    page.reload()
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"


def test_font_size_controls_change_scale(page, server_url):
    page.goto(f"{server_url}/index.html")
    initial = page.evaluate("getComputedStyle(document.documentElement).fontSize")
    page.click("#font-bigger")
    page.click("#font-bigger")
    page.wait_for_timeout(50)
    bigger = page.evaluate("getComputedStyle(document.documentElement).fontSize")
    assert float(bigger.replace("px", "")) > float(initial.replace("px", ""))


# ---------------------------------------------------------------------------
# Other pages
# ---------------------------------------------------------------------------
def test_worksheet_page_solves_multiple_questions(page, server_url):
    page.goto(f"{server_url}/worksheet.html")
    page.click("#worksheet-btn")
    page.wait_for_selector("#worksheet-summary:not(.hidden)", timeout=20000)
    summary = page.locator("#worksheet-summary").inner_text()
    assert "5 question" in summary
    assert "100% solved" in summary  # JS renders the float 100.0 as "100"


def test_about_page_loads_with_heading(page, server_url):
    page.goto(f"{server_url}/about.html")
    assert page.locator("h1").inner_text() == "How This Tool Works"


# ---------------------------------------------------------------------------
# GanitDrishti: new elements added to match the reference dashboard, kept in
# our accessible theme (real health check, real camera/waveform wiring, an
# honest 2-stage progress indicator, real stat tiles -- not decoration).
# ---------------------------------------------------------------------------
def test_engine_status_shows_online_for_a_healthy_server(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.wait_for_function(
        "document.getElementById('engine-status').dataset.tone !== 'muted'", timeout=5000
    )
    status = page.locator("#engine-status")
    assert status.get_attribute("data-tone") == "ok"
    assert "Online" in status.inner_text()


def test_camera_controls_present_and_start_hidden_state_correct(page, server_url):
    page.goto(f"{server_url}/index.html")
    page.keyboard.press("Alt+3")  # switch to image mode
    page.wait_for_selector("#panel-image:not(.hidden)", timeout=5000)
    assert page.locator("#camera-start").is_visible()
    assert page.locator("#camera-capture").is_hidden()
    assert page.locator("#camera-stop").is_hidden()
    assert page.locator("#camera-preview").is_hidden()


def test_waveform_canvases_exist_and_start_hidden(page, server_url):
    page.goto(f"{server_url}/index.html")
    for sel in ["#quick-ask-waveform", "#voice-waveform"]:
        canvas = page.locator(sel)
        assert canvas.count() == 1
        assert canvas.is_hidden()
        assert canvas.get_attribute("aria-hidden") == "true"


def test_engine_progress_stages_exist_and_are_decorative(page, server_url):
    page.goto(f"{server_url}/index.html")
    progress = page.locator("#engine-progress")
    assert progress.get_attribute("aria-hidden") == "true"  # result-status carries the real a11y signal
    stages = progress.locator("li")
    assert stages.count() == 2
    assert stages.nth(0).get_attribute("data-stage") == "read"
    assert stages.nth(1).get_attribute("data-stage") == "solve"


def test_stat_tiles_populate_with_real_braille_fidelity_after_solving(page, server_url):
    page.goto(f"{server_url}/index.html")
    _ask_and_solve(page, "2*x + 3 = 11")
    value = page.locator("#stat-braille-fidelity").inner_text()
    assert value.endswith("%")
    assert value != "—%"
    # No photo was used for this question, so the OCR tile must stay hidden.
    assert page.locator("#stat-ocr-tile").is_hidden()


def test_project_is_named_ganitdrishti(page, server_url):
    page.goto(f"{server_url}/index.html")
    assert page.locator(".app-header h1").inner_text() == "GanitDrishti"
    assert "GanitDrishti" in page.title()


def test_manifest_and_service_worker_registered(page, server_url):
    page.goto(f"{server_url}/index.html")
    manifest_href = page.locator('link[rel="manifest"]').get_attribute("href")
    assert manifest_href == "manifest.json"
    page.wait_for_timeout(300)
    has_sw = page.evaluate("'serviceWorker' in navigator")
    assert has_sw
