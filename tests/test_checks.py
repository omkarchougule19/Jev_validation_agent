from jev_guard.checks import contradiction_verdict, format_verdict, on_topic_verdict


def test_on_topic_pass():
    assert on_topic_verdict(0.9) == "pass"


def test_on_topic_flag():
    assert on_topic_verdict(0.5) == "flag"


def test_on_topic_block():
    assert on_topic_verdict(0.1) == "block"


def test_on_topic_boundaries():
    assert on_topic_verdict(0.7) == "pass"
    assert on_topic_verdict(0.69999) == "flag"
    assert on_topic_verdict(0.4) == "flag"
    assert on_topic_verdict(0.39999) == "block"


def test_contradiction_pass():
    assert contradiction_verdict(0.0) == "pass"
    assert contradiction_verdict(0.3) == "pass"


def test_contradiction_flag():
    assert contradiction_verdict(0.5) == "flag"


def test_contradiction_block():
    assert contradiction_verdict(1.0) == "block"


def test_format_valid_high_confidence_passes():
    assert format_verdict("valid", 0.9) == "pass"


def test_format_valid_low_confidence_flags():
    assert format_verdict("valid", 0.5) == "flag"


def test_format_invalid_always_blocks():
    assert format_verdict("invalid", 0.99) == "block"
