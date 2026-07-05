from dak_maintenance.semver import BumpLevel, classify_update


def test_patch_bump():
    assert classify_update("1.51.0", "1.51.3") is BumpLevel.PATCH


def test_minor_bump():
    assert classify_update("1.51.0", "1.52.0") is BumpLevel.MINOR


def test_major_bump():
    assert classify_update("1.51.0", "2.0.0") is BumpLevel.MAJOR


def test_no_change():
    assert classify_update("1.2.3", "1.2.3") is BumpLevel.NONE


def test_v_prefix_and_suffixes():
    assert classify_update("v1.2.3", "1.2.4") is BumpLevel.PATCH
    assert classify_update("1.2.3rc1", "1.2.3") is BumpLevel.NONE
    assert classify_update("1.2.3", "1.3.0+local") is BumpLevel.MINOR


def test_zero_major_minor_is_treated_as_major():
    # 0.x では minor 変化を破壊的とみなす
    assert classify_update("0.27.0", "0.28.0") is BumpLevel.MAJOR
    assert classify_update("0.27.0", "0.27.1") is BumpLevel.MINOR


def test_missing_components_default_zero():
    assert classify_update("1", "1.0.1") is BumpLevel.PATCH
    assert classify_update("1.2", "1.3") is BumpLevel.MINOR


def test_unparseable_is_unknown():
    assert classify_update("", "1.0.0") is BumpLevel.UNKNOWN
    assert classify_update("abc", "def") is BumpLevel.UNKNOWN


def test_downgrade_is_unknown():
    assert classify_update("2.0.0", "1.9.0") is BumpLevel.UNKNOWN
