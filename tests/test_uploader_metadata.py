import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uploader import _append_hashtags, _normalise_hashtag


def test_normalise_hashtag_accepts_ranked_dictionary():
    assert _normalise_hashtag({"tag": "#anatomie", "score": 9}) == "#anatomie"
    assert _normalise_hashtag({"tag": "science"}) == "#science"


def test_append_hashtags_accepts_ranked_dicts_and_strings():
    result = _append_hashtags(
        {
            "description": "Une explication scientifique.",
            "hashtags_ranked": [
                {"tag": "#anatomie", "score": 9},
                {"tag": "science", "score": 8},
                "#corpshumain",
                {"name": "curiosites"},
                None,
            ],
        }
    )
    assert "#anatomie" in result
    assert "#science" in result
    assert "#corpshumain" in result
    assert "#curiosites" in result
    assert result.count("#Shorts") == 1


def test_append_hashtags_falls_back_to_plain_hashtags():
    result = _append_hashtags({"description": "Test", "hashtags": ["#france", "science"]})
    assert "#france" in result
    assert "#science" in result
