from reels_factory.utils import apply_patterns, reel_id_from_title


def test_apply_patterns_replaces_case_insensitive():
    patterns = [{"pattern": r"foo", "replacement": "bar"}]
    assert apply_patterns("Foo fighters", patterns) == "bar fighters"


def test_reel_id_is_deterministic():
    title = "A memorable story title"
    assert reel_id_from_title(title) == reel_id_from_title(title)
