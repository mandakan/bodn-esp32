# bodn/ui/admin_qr.py — Admin URL screen with QR code

from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered
from bodn.i18n import t
from bodn import config


class AdminQRScreen(Screen):
    """Displays the admin web UI URL as text and a scannable QR code.

    Press any encoder button to go back.
    """

    def __init__(self, settings):
        self._settings = settings
        self._dirty = True
        self._manager = None
        self._qr_matrix = None
        self._url = ""

    def enter(self, manager):
        self._manager = manager
        self._dirty = True

        # Build URL from current IP
        from bodn.wifi import get_ip

        ip = get_ip()
        self._url = "http://{}".format(ip)

        # Generate QR code
        try:
            from bodn.qr import encode

            self._qr_matrix = encode(self._url)
        except Exception as e:
            print("QR encode failed:", e)
            self._qr_matrix = None

    def needs_redraw(self):
        return self._dirty

    def update(self, inp, frame):
        # Any encoder button press → go back
        if inp.enc_btn_pressed[config.ENC_NAV] or inp.enc_btn_pressed[config.ENC_A]:
            if self._manager:
                self._manager.pop()
            return
        # Any MCP button press → go back
        if inp.any_btn_pressed():
            if self._manager:
                self._manager.pop()

    def render(self, tft, theme, frame):
        self._dirty = False
        tft.fill(theme.BLACK)

        w = theme.width
        h = theme.height

        # Title
        draw_centered(tft, t("settings_admin"), 8, theme.WHITE, w)

        if self._qr_matrix:
            qr_size = len(self._qr_matrix)
            # Scale to fit display — leave room for title and URL text
            max_qr_h = h - 50  # title + url text
            max_qr_w = w - 20
            px = min(max_qr_h // qr_size, max_qr_w // qr_size)
            px = max(2, min(px, 8))  # clamp 2-8px per module

            total = qr_size * px
            ox = (w - total) // 2
            oy = 24

            # White quiet zone border (1 module)
            tft.fill_rect(ox - px, oy - px, total + px * 2, total + px * 2, theme.WHITE)

            # Draw QR modules
            for r in range(qr_size):
                for c in range(qr_size):
                    if self._qr_matrix[r][c]:
                        tft.fill_rect(ox + c * px, oy + r * px, px, px, theme.BLACK)

            # URL text below QR
            url_y = oy + total + px + 8
        else:
            url_y = h // 2

        # Display URL
        draw_centered(tft, self._url, url_y, theme.CYAN, w)

        # Hint
        draw_centered(tft, t("admin_back"), h - 14, theme.MUTED, w)
