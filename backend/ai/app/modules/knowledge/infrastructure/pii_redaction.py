import re

from app.modules.knowledge.domain import RedactionCategory, RedactionFinding, RedactionResult

_PLACEHOLDERS: dict[RedactionCategory, str] = {
    "email": "[EMAIL_REDACTED]",
    "phone": "[PHONE_REDACTED]",
    "vin": "[VIN_REDACTED]",
    "address": "[ADDRESS_REDACTED]",
    "name": "[NAME_REDACTED]",
}

# Multi-label domains fully consumed (user@mail.example.com), not just the
# final label.
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@(?:[\w-]+\.)+[a-zA-Z]{2,}")

# Vietnamese mobile prefixes after the 2018 renumbering (03/05/07/08/09),
# optionally +84/0084-prefixed, tolerant of space/dot/dash grouping. Landline
# (02x) numbers are a known, disclosed gap — see PatternBasedTextRedactor.
_PHONE_PATTERN = re.compile(
    r"(?:\+84[-.\s]?|0084[-.\s]?|0)(?:3|5|7|8|9)(?:[-.\s]?\d){8}\b"
)

# 17-character VIN alphanumeric alphabet excludes I, O, Q (ISO 3779). This
# will also match any other 17-char alphanumeric token (e.g. an unrelated
# identifier) — deliberately biased toward over-redaction over a missed VIN.
_VIN_PATTERN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")

_PUNCTUATION_CHARS = ".,;:!?()[]{}\"'"
_TOKEN_PATTERN = re.compile(r"\S+")


def _looks_like_proper_noun(word: str) -> bool:
    """Title-case (Nguyễn) or ALL-CAPS (NGUYỄN) — not a lowercase common word."""
    return bool(word) and (word.istitle() or (word.isalpha() and word.isupper()))


# A leading house number is itself a strong signal, so the street branch is
# not further gated on capitalization — a numbered street ("123 đường số 5")
# is still a real address even if "số 5" isn't a proper noun.
_STREET_KEYWORDS = (
    r"đường|phố|ngõ|hẻm|quốc lộ|tỉnh lộ|street|avenue|ave\.?|road|rd\.?|"
    r"boulevard|blvd\.?"
)
_STREET_ADDRESS_PATTERN = re.compile(
    rf"\b\d{{1,4}}[A-Za-z]?(?:[/\-]\d{{1,4}})?\s+(?:{_STREET_KEYWORDS})\s+"
    rf"[^\d,.\n]{{2,40}}?(?=[,.\n]|$)",
    re.IGNORECASE,
)

# The admin-unit branch has no house number to anchor on, so "phường"/"xã"/
# "thành phố" etc. are themselves ordinary Vietnamese words in other
# contexts ("thành phố thông minh" = "smart city", "xã hội" = "society",
# "tỉnh táo" = "alert"). Requiring the following word to look like a proper
# noun (see _looks_like_proper_noun) is what separates a real place name
# ("phường Bến Nghé") from ordinary prose using the same keyword.
_ADMIN_KEYWORDS = r"phường|xã|quận|huyện|thị xã|thành phố|tỉnh|district|ward|province"
_ADMIN_ADDRESS_PATTERN = re.compile(
    rf"\b(?:{_ADMIN_KEYWORDS})\s+(?P<place>[^\d,.\n]{{2,40}}?)(?=[,.\n]|$)",
    re.IGNORECASE,
)

# "Quận 5" / "District 3": a numbered district is an unambiguous location
# reference in Vietnamese addressing (unlike the named-place branch above,
# a number here is never an ordinary-prose false positive), so this is
# always redacted without a proper-noun gate.
_NUMBERED_DISTRICT_PATTERN = re.compile(
    r"\b(?:quận|district)\s+\d{1,3}\b", re.IGNORECASE
)

# Covers the ~26 most common Vietnamese family names (~90%+ of the
# population per published demographic estimates), matched case-insensitively
# so an ALL-CAPS transcript ("NGUYỄN VĂN AN") is still caught. Uncommon
# surnames remain a known false-negative gap.
_VIETNAMESE_SURNAMES_CASEFOLDED = frozenset(
    name.casefold()
    for name in (
        "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ",
        "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đinh", "Đoàn",
        "Vương", "Trịnh", "Đàm", "Tô", "Tạ", "Lương", "Mai", "Kiều",
    )
)
# English has no small, high-recall surname list; an honorific is a precise,
# low-false-positive trigger instead. A bare English given+family name with
# no honorific is a known, disclosed false-negative gap.
_ENGLISH_HONORIFICS_CASEFOLDED = frozenset({"mr", "mrs", "ms", "miss", "dr"})
_NAME_TRIGGERS_CASEFOLDED = _VIETNAMESE_SURNAMES_CASEFOLDED | _ENGLISH_HONORIFICS_CASEFOLDED
_MAX_NAME_FOLLOWERS = 3

_PATTERN_CATEGORIES: tuple[tuple[re.Pattern[str], RedactionCategory], ...] = (
    (_EMAIL_PATTERN, "email"),
    (_PHONE_PATTERN, "phone"),
    (_VIN_PATTERN, "vin"),
    (_STREET_ADDRESS_PATTERN, "address"),
    (_NUMBERED_DISTRICT_PATTERN, "address"),
)


def _redact_pattern(
    text: str,
    pattern: re.Pattern[str],
    category: RedactionCategory,
) -> tuple[str, int]:
    count = sum(1 for _ in pattern.finditer(text))
    if count == 0:
        return text, 0
    return pattern.sub(_PLACEHOLDERS[category], text), count


def _redact_admin_address(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        place = match.group("place").strip()
        first_word = place.split(maxsplit=1)[0].strip(_PUNCTUATION_CHARS) if place else ""
        if not _looks_like_proper_noun(first_word):
            return match.group(0)
        count += 1
        return _PLACEHOLDERS["address"]

    return _ADMIN_ADDRESS_PATTERN.sub(replace, text), count


def _redact_names(text: str) -> tuple[str, int]:
    tokens = list(_TOKEN_PATTERN.finditer(text))
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(tokens):
        word = tokens[index].group().strip(_PUNCTUATION_CHARS)
        if word.casefold() not in _NAME_TRIGGERS_CASEFOLDED:
            index += 1
            continue
        end_index = index
        look_ahead = index + 1
        while look_ahead < len(tokens) and look_ahead <= index + _MAX_NAME_FOLLOWERS:
            candidate = tokens[look_ahead].group().strip(_PUNCTUATION_CHARS)
            if not _looks_like_proper_noun(candidate):
                break
            end_index = look_ahead
            look_ahead += 1
        if end_index > index:
            spans.append((tokens[index].start(), tokens[end_index].end()))
            index = end_index + 1
        else:
            index += 1
    if not spans:
        return text, 0
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(text[cursor:start])
        parts.append(_PLACEHOLDERS["name"])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), len(spans)


class PatternBasedTextRedactor:
    """Deterministic rule-based PII redaction for Vietnamese/English text.

    A safety gate, not a compliance-certified scrubber:
    - Address detection matches Vietnamese/English street or administrative
      keywords; the admin-unit branch additionally requires the following
      word to look like a proper noun, so common phrases sharing the same
      keyword ("thành phố thông minh") are not redacted as if they were a
      place name.
    - Name detection triggers on a curated list of common Vietnamese
      surnames or an English honorific (Mr/Mrs/Ms/Miss/Dr), followed by
      1-3 proper-noun-shaped words (title-case or ALL-CAPS). Uncommon
      Vietnamese surnames and bare English names without an honorific are
      known false-negative gaps, not claims of complete coverage.
    - Both address and name detection can still over-redact benign proper
      nouns (e.g. a street named after a historical figure sharing a common
      surname). This is a deliberate bias: masking non-PII costs nothing
      here, missing real PII does.
    - Vietnamese landline (02x) numbers are not matched (mobile numbers are);
      a disclosed, not-yet-closed gap.
    """

    def redact(self, text: str) -> RedactionResult:
        working = text
        findings: list[RedactionFinding] = []
        for pattern, category in _PATTERN_CATEGORIES:
            working, count = _redact_pattern(working, pattern, category)
            if count:
                findings.append(RedactionFinding(category=category, count=count))
        working, admin_count = _redact_admin_address(working)
        if admin_count:
            findings.append(RedactionFinding(category="address", count=admin_count))
        working, name_count = _redact_names(working)
        if name_count:
            findings.append(RedactionFinding(category="name", count=name_count))
        return RedactionResult(redacted_text=working, findings=tuple(findings))
