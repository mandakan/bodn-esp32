"""Tests for Blippa free-play NFC mode — focus on dispatch + audio selection."""


class TestStableHash:
    def test_deterministic(self):
        from bodn.ui.blippa import _stable_hash

        assert _stable_hash("cat_red") == _stable_hash("cat_red")

    def test_distinguishes(self):
        from bodn.ui.blippa import _stable_hash

        # Mystery-blip pitches must not collapse to the same value for
        # different card ids within the expected spread.
        ids = ["foo", "bar", "baz", "qux", "hotel_key", "bus_card"]
        hashes = {s: _stable_hash(s) for s in ids}
        assert len(set(hashes.values())) == len(ids)

    def test_empty_string(self):
        from bodn.ui.blippa import _stable_hash

        assert _stable_hash("") == 0


class TestNFCSubscription:
    def test_subscribes_to_sortera_and_rakna(self):
        from bodn.ui.blippa import BlippaScreen

        assert "sortera" in BlippaScreen.nfc_modes
        assert "rakna" in BlippaScreen.nfc_modes

    def test_does_not_subscribe_to_launcher(self):
        from bodn.ui.blippa import BlippaScreen

        # Launcher tags must be globally routed — never consumed by Blippa.
        assert "launcher" not in BlippaScreen.nfc_modes


class TestOnNfcTag:
    def _new_screen(self):
        from bodn.ui.blippa import BlippaScreen

        return BlippaScreen(overlay=None, arcade=None, audio=None)

    def test_consumes_tag_with_id(self):
        s = self._new_screen()
        consumed = s.on_nfc_tag({"mode": "sortera", "id": "cat_red"})
        assert consumed is True
        assert s._pending_tag == ("sortera", "cat_red")

    def test_rejects_tag_without_id(self):
        s = self._new_screen()
        # A subscribed-mode tag with no id can't show a card — fall through.
        consumed = s.on_nfc_tag({"mode": "sortera", "id": None})
        assert consumed is False
        assert s._pending_tag is None


class TestCardLabels:
    def test_returns_both_languages_capitalized(self):
        from bodn.ui.blippa import _card_labels

        assert _card_labels({"label_sv": "katt", "label_en": "cat"}) == ("Katt", "Cat")

    def test_missing_language_is_empty(self):
        from bodn.ui.blippa import _card_labels

        assert _card_labels({"label_sv": "katt", "label_en": ""}) == ("Katt", "")
        assert _card_labels({"label_sv": "", "label_en": "cat"}) == ("", "Cat")

    def test_none_card_returns_empty_pair(self):
        from bodn.ui.blippa import _card_labels

        assert _card_labels(None) == ("", "")


class TestEmojiName:
    def _new_screen(self):
        from bodn.ui.blippa import BlippaScreen

        return BlippaScreen(overlay=None, arcade=None, audio=None)

    def test_sortera_subject_from_id(self):
        s = self._new_screen()
        assert s._emoji_name_for("sortera", "cat_red", {}) == "cat"
        assert s._emoji_name_for("sortera", "firetruck_blue", {}) == "firetruck"

    def test_rakna_operator_card(self):
        s = self._new_screen()
        card = {"type": "operator", "operator": "+"}
        assert s._emoji_name_for("rakna", "op_plus", card) == "plus"

    def test_rakna_number_card_has_no_emoji(self):
        s = self._new_screen()
        card = {"type": "number", "quantity": 3}
        # No OpenMoji sprite for bare digits — render label only.
        assert s._emoji_name_for("rakna", "dots_3", card) is None
