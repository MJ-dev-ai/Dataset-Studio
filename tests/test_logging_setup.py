from core import logging_setup


def test_pending_crash_log_is_durable_and_append_only(tmp_path):
    logging_setup._LOG_DIRECTORY = tmp_path
    path = logging_setup.append_pending_crash("first failure")
    logging_setup.append_pending_crash("second failure")
    text = path.read_text(encoding="utf-8")
    assert "first failure" in text
    assert "second failure" in text
