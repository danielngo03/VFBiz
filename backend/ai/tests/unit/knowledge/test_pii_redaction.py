import pytest

from app.modules.knowledge.infrastructure import PatternBasedTextRedactor


@pytest.fixture
def redactor() -> PatternBasedTextRedactor:
    return PatternBasedTextRedactor()


def _categories(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {finding.category for finding in result.findings}


def test_redacts_email_address(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Liên hệ khách hàng qua email an.nguyen@example.com nhé.")

    assert "an.nguyen@example.com" not in result.redacted_text
    assert "[EMAIL_REDACTED]" in result.redacted_text
    assert _categories(result) == {"email"}
    assert result.findings[0].count == 1


@pytest.mark.parametrize(
    "phone",
    [
        "0912345678",
        "+84912345678",
        "091 234 5678",
        "091-234-5678",
    ],
)
def test_redacts_vietnamese_phone_number_formats(
    redactor: PatternBasedTextRedactor, phone: str
) -> None:
    result = redactor.redact(f"Số điện thoại khách hàng là {phone} để liên hệ.")

    assert phone not in result.redacted_text
    assert "[PHONE_REDACTED]" in result.redacted_text
    assert _categories(result) == {"phone"}


def test_redacts_vin(redactor: PatternBasedTextRedactor) -> None:
    vin = "1HGCM82633A123456"[:17]
    result = redactor.redact(f"Số khung xe VIN {vin} đã được đăng ký.")

    assert vin not in result.redacted_text
    assert "[VIN_REDACTED]" in result.redacted_text
    assert _categories(result) == {"vin"}


def test_redacts_street_address(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Khách hàng sinh sống tại 123 đường Nguyễn Huệ, gần trung tâm.")

    assert "123 đường Nguyễn Huệ" not in result.redacted_text
    assert "[ADDRESS_REDACTED]" in result.redacted_text
    assert "address" in _categories(result)


def test_redacts_administrative_address_unit(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Khách hàng cư trú tại phường Bến Nghé, gần showroom.")

    assert "phường Bến Nghé" not in result.redacted_text
    assert "[ADDRESS_REDACTED]" in result.redacted_text


def test_redacts_vietnamese_full_name(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Khách hàng Nguyễn Văn An đã đặt cọc xe VF 8 hôm qua.")

    assert "Nguyễn Văn An" not in result.redacted_text
    assert "[NAME_REDACTED]" in result.redacted_text
    assert _categories(result) == {"name"}


def test_redacts_multi_word_surname_and_given_name(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Chị Trần Thị Bích Ngọc muốn đổi lịch giao xe.")

    assert "Trần Thị Bích Ngọc" not in result.redacted_text
    assert "[NAME_REDACTED]" in result.redacted_text


def test_does_not_redact_surname_without_a_following_title_case_word(
    redactor: PatternBasedTextRedactor,
) -> None:
    result = redactor.redact("Nguyễn đã mua xe điện tháng trước.")

    assert result.redacted_text == "Nguyễn đã mua xe điện tháng trước."
    assert result.findings == ()


def test_leaves_ordinary_vehicle_text_untouched(redactor: PatternBasedTextRedactor) -> None:
    text = "VF 8 có phạm vi hoạt động khoảng 420 km cho một lần sạc đầy."

    result = redactor.redact(text)

    assert result.redacted_text == text
    assert result.findings == ()


def test_redacts_multiple_categories_in_one_chunk(redactor: PatternBasedTextRedactor) -> None:
    text = (
        "Khách hàng Nguyễn Văn An, số điện thoại 0912345678, "
        "email an.nguyen@example.com, sống tại 123 đường Nguyễn Huệ."
    )

    result = redactor.redact(text)

    assert "Nguyễn Văn An" not in result.redacted_text
    assert "0912345678" not in result.redacted_text
    assert "an.nguyen@example.com" not in result.redacted_text
    categories = _categories(result)
    assert {"phone", "email", "address"}.issubset(categories)


def test_bounded_false_negative_fixture_corpus_is_fully_redacted(
    redactor: PatternBasedTextRedactor,
) -> None:
    fixtures = [
        ("Anh Trần Văn Bình đã liên hệ tổng đài để hỏi về bảo hành.", "Trần Văn Bình"),
        ("Chị Lê Thị Hoa muốn đặt lịch lái thử xe VF 9.", "Lê Thị Hoa"),
        ("Quý khách Phạm Minh Tuấn vui lòng gọi 0987654321 để xác nhận.", "0987654321"),
        ("Liên hệ chăm sóc khách hàng: support.customer@vinfast.vn", "support.customer@vinfast.vn"),
        ("Địa chỉ giao xe: 45 đường Lê Lợi, quận 1.", "45 đường Lê Lợi"),
        ("Xe có số VIN RLZFAAG60PT123456 đã được bàn giao.", "RLZFAAG60PT123456"),
    ]

    for fixture, raw_pii in fixtures:
        result = redactor.redact(fixture)
        assert result.findings, f"expected at least one finding for: {fixture!r}"
        assert raw_pii not in result.redacted_text, (
            f"raw PII {raw_pii!r} leaked through for fixture: {fixture!r}"
        )


@pytest.mark.parametrize(
    "phrase",
    [
        "VinFast hướng tới xây dựng thành phố thông minh tại nhiều đô thị.",
        "Chính sách xã hội của công ty được cập nhật hàng năm.",
        "Khách hàng cần giữ tỉnh táo khi lái xe đường dài.",
    ],
)
def test_admin_keyword_alone_does_not_redact_ordinary_prose(
    redactor: PatternBasedTextRedactor, phrase: str
) -> None:
    result = redactor.redact(phrase)

    assert result.redacted_text == phrase
    assert result.findings == ()


def test_redacts_numbered_district(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Showroom VinFast đặt tại Quận 5, gần trung tâm.")

    assert "Quận 5" not in result.redacted_text
    assert "[ADDRESS_REDACTED]" in result.redacted_text
    assert _categories(result) == {"address"}


def test_redacts_named_administrative_place_with_proper_noun(
    redactor: PatternBasedTextRedactor,
) -> None:
    result = redactor.redact("Trụ sở đặt tại thành phố Đà Nẵng, miền Trung.")

    assert "thành phố Đà Nẵng" not in result.redacted_text
    assert "[ADDRESS_REDACTED]" in result.redacted_text


def test_redacts_english_name_with_honorific(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Please contact Mr. John Smith about the delivery.")

    assert "John Smith" not in result.redacted_text
    assert "[NAME_REDACTED]" in result.redacted_text
    assert _categories(result) == {"name"}


def test_does_not_redact_bare_english_name_without_honorific(
    redactor: PatternBasedTextRedactor,
) -> None:
    # Disclosed, known gap: a bare English name with no honorific has no
    # reliable trigger and is not redacted by this heuristic.
    text = "John Smith called about the delivery."

    result = redactor.redact(text)

    assert result.redacted_text == text
    assert result.findings == ()


def test_redacts_all_caps_vietnamese_name(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("KHACH HANG: NGUYỄN VĂN AN, so dien thoai lien he sau.")

    assert "NGUYỄN VĂN AN" not in result.redacted_text
    assert "[NAME_REDACTED]" in result.redacted_text


def test_redacts_multi_label_email_domain(redactor: PatternBasedTextRedactor) -> None:
    result = redactor.redact("Gửi email tới an.nguyen@mail.example.com để được hỗ trợ.")

    assert "an.nguyen@mail.example.com" not in result.redacted_text
    assert "[EMAIL_REDACTED]" in result.redacted_text
    assert result.redacted_text.count("[EMAIL_REDACTED]") == 1
    # Confirms the whole multi-label domain is consumed, not left dangling.
    assert ".com" not in result.redacted_text
