import pytest


class TestDetectRole:
    def test_empty_text_is_other(self, tracker):
        assert tracker.detect_role_from_text("") == "Other"
        assert tracker.detect_role_from_text(None) == "Other"

    def test_priority_roles_win_over_general_keywords(self, tracker):
        text = "Senior engineer, system specialist wanted"
        assert tracker.detect_role_from_text(text) == "System Specialist"

    def test_it_support(self, tracker):
        assert tracker.detect_role_from_text("IT Support technician") == "IT Support"

    def test_embedded_systems(self, tracker):
        result = tracker.detect_role_from_text("Embedded systems developer")
        assert result == "Embedded System Programming"

    def test_general_keyword_is_title_cased(self, tracker):
        assert tracker.detect_role_from_text("Looking for a data scientist") == "Data Scientist"

    def test_unknown_text_is_other(self, tracker):
        assert tracker.detect_role_from_text("Barista needed") == "Other"


class TestExtractUrls:
    def test_no_text(self, tracker):
        assert tracker._extract_all_urls("") == []
        assert tracker._extract_all_urls(None) == []

    def test_http_links(self, tracker):
        text = 'See https://example.com/job/1 and http://example.org/x?y=2.'
        assert tracker._extract_all_urls(text) == [
            "https://example.com/job/1",
            "http://example.org/x?y=2.",
        ]

    def test_www_links_get_a_scheme(self, tracker):
        assert tracker._extract_all_urls("visit www.example.com/jobs") == [
            "http://www.example.com/jobs"
        ]

    def test_stops_at_quotes_and_brackets(self, tracker):
        text = '<a href="https://example.com/a">x</a> (https://example.com/b)'
        assert tracker._extract_all_urls(text) == [
            "https://example.com/a",
            "https://example.com/b",
        ]


class TestSheetsRetry:
    def test_returns_result_on_first_success(self, tracker):
        class Req:
            def execute(self):
                return {"ok": True}

        assert tracker.sheets_execute_with_retry(lambda: Req()) == {"ok": True}

    def test_retries_then_succeeds(self, tracker, monkeypatch):
        import time

        sleeps = []
        monkeypatch.setattr(time, "sleep", sleeps.append)
        calls = {"n": 0}

        class Req:
            def execute(self):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise OSError("transient")
                return "done"

        assert tracker.sheets_execute_with_retry(lambda: Req(), max_retries=3) == "done"
        assert sleeps == [1.0, 2.0]

    def test_raises_after_last_attempt(self, tracker, monkeypatch):
        import time

        monkeypatch.setattr(time, "sleep", lambda s: None)

        class Req:
            def execute(self):
                raise OSError("down")

        with pytest.raises(OSError):
            tracker.sheets_execute_with_retry(lambda: Req(), max_retries=2)
