import json
import ladder_lib


def _ladder(tmp_path):
    return str(tmp_path / "ladder.json")


def test_tier_of_defaults_to_shadow(tmp_path):
    assert ladder_lib.tier_of("prd-draft", path=_ladder(tmp_path)) == "shadow"


def test_advance_climbs_one_rung(tmp_path):
    p = _ladder(tmp_path)
    assert ladder_lib.advance("prd-draft", path=p) == "supervised"
    assert ladder_lib.tier_of("prd-draft", path=p) == "supervised"
    assert ladder_lib.advance("prd-draft", path=p) == "autonomous"
    assert ladder_lib.advance("prd-draft", path=p) == "autonomous"  # cannot climb past top


def test_demote_drops_one_rung(tmp_path):
    p = _ladder(tmp_path)
    ladder_lib.set_tier("x", "autonomous", path=p)
    assert ladder_lib.demote("x", path=p) == "supervised"
    assert ladder_lib.demote("x", path=p) == "shadow"
    assert ladder_lib.demote("x", path=p) == "shadow"  # floor


def test_all_tiers_roundtrips(tmp_path):
    p = _ladder(tmp_path)
    ladder_lib.set_tier("a", "supervised", path=p)
    assert ladder_lib.all_tiers(path=p)["a"] == "supervised"


def test_thresholds_have_moderate_defaults(tmp_path):
    th = ladder_lib.thresholds(path=_ladder(tmp_path))
    assert th["shadow_to_supervised"]["min_judged"] == 4
    assert th["shadow_to_supervised"]["min_approval"] == 0.75
    assert th["shadow_to_supervised"]["min_agreement"] == 0.70
    assert th["supervised_to_autonomous"]["min_judged"] == 12
    assert th["supervised_to_autonomous"]["min_approval"] == 0.85
    assert th["supervised_to_autonomous"]["min_agreement"] == 0.80


def test_thresholds_include_min_reacted(tmp_path):
    th = ladder_lib.thresholds(path=_ladder(tmp_path))
    assert th["shadow_to_supervised"]["min_reacted"] == 3
    assert th["supervised_to_autonomous"]["min_reacted"] == 6


def test_thresholds_overridable_in_file(tmp_path):
    p = _ladder(tmp_path)
    with open(p, "w") as f:
        json.dump({"tiers": {}, "thresholds": {"shadow_to_supervised": {"min_judged": 99}}}, f)
    th = ladder_lib.thresholds(path=p)
    assert th["shadow_to_supervised"]["min_judged"] == 99       # override wins
    assert th["shadow_to_supervised"]["min_approval"] == 0.75   # default fills the rest


def test_legacy_gated_tier_migrates_on_read(tmp_path):
    # A teammate's pre-rename store may hold "gated" / "shadow_to_gated".
    p = _ladder(tmp_path)
    with open(p, "w") as f:
        json.dump({"tiers": {"prd-draft": "gated"},
                   "thresholds": {"shadow_to_gated": {"min_judged": 99}}}, f)
    assert ladder_lib.tier_of("prd-draft", path=p) == "supervised"
    assert ladder_lib.all_tiers(path=p)["prd-draft"] == "supervised"
    # legacy threshold override is honored under the new key
    assert ladder_lib.thresholds(path=p)["shadow_to_supervised"]["min_judged"] == 99


def test_demote_record_tracks_consecutive(tmp_path):
    p = _ladder(tmp_path)
    assert ladder_lib.note_demotion_signal("a", below=True, path=p) == 1
    assert ladder_lib.note_demotion_signal("a", below=True, path=p) == 2
    assert ladder_lib.note_demotion_signal("a", below=False, path=p) == 0  # resets
