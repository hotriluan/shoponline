import unicodedata

import pytest

from shoponline.domain.report_names import (
    PROVINCES,
    ReportNameSuggestion,
    province_of,
    suggest_report_name,
)


def test_thirty_four_provinces():
    assert len(set(PROVINCES)) == 34


@pytest.mark.parametrize(
    ("address", "province"),
    [
        ("Phường Sài Gòn, Thành phố Hồ Chí Minh, Việt Nam", "Hồ Chí Minh"),
        ("Xã Mỹ Hòa Hưng, Tỉnh An Giang, Việt Nam", "An Giang"),
        ("12 Lê Lợi, Phường Long Xuyên, An Giang, Việt Nam", "An Giang"),  # Lazada, TikTok
        ("Phường Ba Đình, Hà Nội, Việt Nam", "Hà Nội"),
        ("Phường Nha Trang, Tỉnh Khánh Hoà, Việt Nam", "Khánh Hòa"),  # old tone placement
        ("Xã Hoằng Hóa, thanh hoá, việt nam", "Thanh Hóa"),
        ("Phường Một, TP. Hồ Chí Minh, Việt Nam", "Hồ Chí Minh"),
        ("Phường Một, Thành phố Huế", "Huế"),  # no country
        ("Phường Một ,  Thành phố  Đà Nẵng ,Việt Nam ,", "Đà Nẵng"),
    ],
)
def test_province_of(address, province):
    assert province_of(address) == province


def test_province_of_decomposed_text():
    address = unicodedata.normalize("NFD", "Phường Long Xuyên, Tỉnh An Giang, Việt Nam")
    assert address != unicodedata.normalize("NFC", address)
    assert province_of(address) == "An Giang"
    assert province_of(unicodedata.normalize("NFD", "Xã X, Tỉnh Đắk Lắk, Việt Nam")) == "Đắk Lắk"


@pytest.mark.parametrize(
    "address",
    [None, "", "Việt Nam", "Phường Một, Tỉnh Thử, Việt Nam", "Phường Một, Bình Dương, Việt Nam"],
)
def test_province_of_unknown(address):
    assert province_of(address) is None


def test_suggest_from_tiktok_style_name():
    product = "Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu - 0.8 lít"
    suggestion = suggest_report_name([(product, "Cánh gián - 2004, 0.8 lít")])
    assert suggestion == ReportNameSuggestion(
        "Propan - ULTRAN VERNIS - V-09 - Sơn Dầu Bóng Màu", "0.8 lít", "Màu sắc:Cánh gián - 2004"
    )


def test_suggest_from_shopee_style_name_leaves_item_name_empty():
    suggestion = suggest_report_name([("V-09 VN-0.8L - Sơn dầu bóng", "Cánh gián - 2004,0.8 lít")])
    assert suggestion.item_name == ""
    assert suggestion.size == "0.8 lít"
    assert suggestion.variation == "Màu sắc:Cánh gián - 2004"


def test_suggest_takes_the_most_common_and_ignores_empty_guesses():
    tiktok = ("Propan - SƠN A - 1 lít", "Trắng, 1 lít")
    shopee = ("SƠN A VN-1L", "Trắng,1 lít")
    assert suggest_report_name([tiktok, shopee]) == ReportNameSuggestion(
        "Propan - SƠN A", "1 lít", "Màu sắc:Trắng"
    )


def test_suggest_tie_leaves_field_empty():
    suggestion = suggest_report_name([("P", "Trắng, 1 lít"), ("P", "Đen, 1 lít")])
    assert suggestion.size == "1 lít"
    assert suggestion.variation == ""


def test_suggest_variation_without_comma():
    assert suggest_report_name([("P", "0.8 lít")]) == ReportNameSuggestion("", "0.8 lít", "")
    assert suggest_report_name([("P", "Trắng")]).variation == "Màu sắc:Trắng"
    assert suggest_report_name([]) == ReportNameSuggestion()
