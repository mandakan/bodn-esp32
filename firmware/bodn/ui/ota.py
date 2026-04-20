# bodn/ui/ota.py — OTA firmware sync status screen
#
# Rendered directly by primary_task while bodn.web.ota_active(settings)
# is True. The normal UI render loop is skipped during OTA to free the
# Python VM for the upload handler (see bodn.web._mark_ota_active and
# the primary/secondary render loops in main.py); this module provides
# a minimal "Updating..." takeover so the device isn't visually frozen
# from the child's perspective.

from bodn.i18n import t
from bodn.ui import widgets


def _fmt_path(path, max_chars):
    """Truncate a path to fit `max_chars`, keeping the tail (filename).

    /bodn/ui/nfc_provision.py  →  ...fc_provision.py
    """
    if not path:
        return ""
    if len(path) <= max_chars:
        return path
    return "..." + path[-(max_chars - 3) :]


def render(tft, theme, settings, frame):
    """Paint the full OTA status screen.

    Called at ~4 fps from primary_task (enough to show progress moving
    without meaningfully competing with the upload handler for CPU).
    """
    w = tft.width
    h = tft.height

    # Full black background every frame — simpler than dirty tracking,
    # and we only redraw ~4× per second anyway.
    tft.fill(theme.BLACK)

    # Big banner near the top
    banner = t("ota_updating")
    banner_y = h // 4 - 12
    widgets.draw_centered(tft, banner, banner_y, theme.CYAN, w, scale=2)

    # "Please wait" subtext
    wait = t("ota_please_wait")
    widgets.draw_centered(tft, wait, banner_y + 28, theme.MUTED, w, scale=1)

    # Current file being written (truncated to fit at scale=1)
    path = settings.get("_ota_current_path", "") or ""
    if path:
        path_chars = max(1, w // 8)  # 8px per char at scale=1
        shown = _fmt_path(path, path_chars)
        widgets.draw_centered(tft, shown, h // 2, theme.WHITE, w, scale=1)

    # Counter: "N / TOTAL" files
    files_done = settings.get("_ota_files_done", 0)
    total_files = settings.get("_ota_total_files", 0)
    if total_files > 0:
        label = "{} / {}".format(files_done, total_files)
        widgets.draw_centered(tft, label, h // 2 + 20, theme.AMBER, w, scale=2)

    # Progress bar
    bar_h = 16
    bar_w = int(w * 0.75)
    bar_x = (w - bar_w) // 2
    bar_y = (h * 3) // 4
    total_bytes = settings.get("_ota_total_bytes", 0)
    bytes_done = settings.get("_ota_bytes_done", 0)
    if total_bytes > 0:
        widgets.draw_progress_bar(
            tft,
            bar_x,
            bar_y,
            bar_w,
            bar_h,
            bytes_done,
            total_bytes,
            fg=theme.CYAN,
            bg=theme.DIM,
            border=theme.MUTED,
        )
        kb_done = bytes_done // 1024
        kb_total = total_bytes // 1024
        kb_label = "{} / {} KB".format(kb_done, kb_total)
        widgets.draw_centered(tft, kb_label, bar_y + bar_h + 6, theme.MUTED, w, scale=1)
    else:
        # Indeterminate: no totals yet. Animate a sliding chunk to show
        # the device is alive.
        chunk_w = bar_w // 4
        # Ping-pong across the bar once every ~20 frames (at 4 fps, ~5 s).
        phase = frame % 40
        pos = phase if phase < 20 else 40 - phase
        chunk_x = bar_x + (bar_w - chunk_w) * pos // 20
        tft.rect(bar_x, bar_y, bar_w, bar_h, theme.MUTED)
        tft.fill_rect(bar_x + 1, bar_y + 1, bar_w - 2, bar_h - 2, theme.DIM)
        tft.fill_rect(chunk_x, bar_y + 1, chunk_w, bar_h - 2, theme.CYAN)


def render_secondary(tft, theme, settings):
    """Paint a minimal 'Updating' panel on the 128×128 secondary display.

    Low frequency (once when entering OTA mode, then on each
    render-tick from secondary_task). Kept dead simple — no animation,
    no progress bar — so a single fill + two text calls per cycle.
    """
    tft.fill(theme.BLACK)
    banner = t("ota_updating")
    y = tft.height // 2 - 12
    widgets.draw_centered(tft, banner, y, theme.CYAN, tft.width, scale=1)
    wait = t("ota_please_wait")
    widgets.draw_centered(tft, wait, y + 14, theme.MUTED, tft.width, scale=1)
