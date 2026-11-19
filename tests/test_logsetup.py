import json
import logging

from nexus_core.logsetup import REDACTED, JsonFormatter, RedactFilter, request_id_var


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("nexus.test", logging.INFO, __file__, 1, msg, args, None)


def test_redacts_discord_token_and_bearer():
    f = RedactFilter()
    fake = "MTIzNDU2Nzg5MDEyMzQ1Njc4.GabcDE." + "x" * 38
    rec = _record("token=%s header=%s", fake, "Bearer abcdefghijklmnopqrstuvwxyz123456")
    f.filter(rec)
    out = rec.getMessage()
    assert fake not in out and "abcdefghijklmnopqrstuvwxyz" not in out
    assert out.count(REDACTED) == 2


def test_redacts_configured_secret(monkeypatch):
    f = RedactFilter()
    f.secrets = ["super-secret-value-123"]
    rec = _record("fallo con super-secret-value-123 dentro")
    f.filter(rec)
    assert "super-secret" not in rec.getMessage()


def test_json_formatter_includes_request_id():
    f = RedactFilter()
    tok = request_id_var.set("abc123")
    try:
        rec = _record("hola")
        f.filter(rec)
    finally:
        request_id_var.reset(tok)
    data = json.loads(JsonFormatter().format(rec))
    assert data["request_id"] == "abc123" and data["message"] == "hola"
