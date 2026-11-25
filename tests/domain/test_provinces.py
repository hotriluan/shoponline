from shoponline.domain.provinces import MERGED, fold_key, resolve, seed_aliases
from shoponline.domain.report_names import PROVINCES

ALIASES = seed_aliases()


def test_every_pre_merger_province_and_every_current_one_is_known():
    # 63 provinces before the merger; Huế was Thừa Thiên Huế, so 33 current names were old ones too.
    old = {name for olds in MERGED.values() for name in olds}
    assert len(old) + (len(PROVINCES) - 1) == 63
    assert all(resolve(name, ALIASES) is not None for name in old | set(PROVINCES))


def test_old_provinces_map_to_the_province_that_absorbed_them():
    assert resolve("Kiên Giang", ALIASES) == "An Giang"
    assert resolve("Bình Dương", ALIASES) == "Hồ Chí Minh"
    assert resolve("Bà Rịa - Vũng Tàu", ALIASES) == "Hồ Chí Minh"
    assert resolve("Thừa Thiên Huế", ALIASES) == "Huế"
    assert resolve("Hà Nội", ALIASES) == "Hà Nội"


def test_spelling_prefix_case_and_tone_marks_do_not_matter():
    assert resolve("TP. Hồ Chí Minh", ALIASES) == "Hồ Chí Minh"
    assert resolve("Thành phố Hồ Chí Minh", ALIASES) == "Hồ Chí Minh"
    assert resolve("tỉnh hòa bình", ALIASES) == "Phú Thọ"
    assert resolve("Hoà Bình", ALIASES) == "Phú Thọ"
    assert fold_key("  Đà   Nẵng ") == "da nang"


def test_a_city_or_district_is_not_guessed():
    assert resolve("Huyện Châu Thành", ALIASES) is None
    assert resolve("", ALIASES) is None
    assert resolve(None, ALIASES) is None


def test_common_districts_and_cities_resolve_to_their_province():
    assert resolve("Quận Bình Thạnh", ALIASES) == "Hồ Chí Minh"
    assert resolve("Quận 7", ALIASES) == "Hồ Chí Minh"
    assert resolve("Thành Phố Thủ Đức", ALIASES) == "Hồ Chí Minh"
    assert resolve("TP Dĩ An", ALIASES) == "Hồ Chí Minh"
    assert resolve("Thị Xã Thuận An", ALIASES) == "Hồ Chí Minh"
    assert resolve("Thành Phố Phan Thiết", ALIASES) == "Lâm Đồng"
    assert resolve("Huyện Mỏ Cày Nam", ALIASES) == "Vĩnh Long"
    assert resolve("huyện vân đồn", ALIASES) == "Quảng Ninh"


def test_a_district_prefix_keeps_places_with_one_name_apart():
    assert resolve("Quận Tân Phú", ALIASES) == "Hồ Chí Minh"
    assert resolve("Huyện Tân Phú", ALIASES) == "Đồng Nai"


def test_a_district_name_found_in_several_provinces_is_left_to_an_admin():
    for name in ("Huyện Châu Thành", "Huyện Chợ Mới", "Huyện Bảo Lâm", "Huyện Tân Châu"):
        assert resolve(name, ALIASES) is None


def test_a_district_never_overrides_a_province_name():
    assert resolve("Hòa Bình", ALIASES) == "Phú Thọ"
    assert resolve("Huyện Hòa Bình", ALIASES) is None
