"""Tach cau, so vi-VN, marker so sanh/nhan qua. Xem docs/08-anti-hallucination.md
muc 8.3/8.5 va docs/11-module-spec.md muc 11.4.

`parse_vi_number` la ham DE VIET SAI NHAT trong ca du an: tieng Viet dung `.`
lam dau phan nghin va `,` lam dau phan thap phan - NGUOC voi mac dinh cua
Python/tieng Anh. Vi vay "1.234" (vi-VN) = 1234 (nguyen), con "1,234" (vi-VN)
= 1.234 (thap phan) - hai chuoi trong GIONG NHAU voi tieng Anh nhung nghia
NGUOC HAN.
"""

from __future__ import annotations

import re
import unicodedata

# Cung mau voi app.semantic.evidence._REF_PATTERN - the du lieu dang {{F1.r1.romi}}.
TAG_RE = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")

# So dang vi-VN, co the kem hau to don vi tieng Viet. Xem docs/08 muc 8.3.
# Nhom 1: "1.234.567,89" hoac "1.234.567" (phan nghin dung '.', tung nhom DUNG 3 so).
# Nhom 2: "6,20" hoac "1234" (khong co phan nghin - so nguyen thuan hoac
#         "so_nguyen,phan_thap_phan").
_VI_NUMBER_CORE = re.compile(
    r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?"   # co phan nghin: 1.234.567(,89)?
    r"|-?\d+(?:,\d+)?"                  # khong phan nghin: 1234 hoac 6,20
)

_UNIT_SUFFIXES_NO_MULTIPLIER = ("vnd", "đ", "d")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

# Chuoi dinh danh (CMP-*, CUS-*...) khong duoc tinh la so du chua chu so.
_ID_LIKE_RE = re.compile(r"[A-Za-z]{2,}-[A-Za-z0-9-]*\d")


def parse_vi_number(
    s: str, unit_aliases: dict[str, float] | None = None,
) -> float | None:
    """'392.498.500' -> 392498500.0 ; '6,20' -> 6.2 ; '48,8%' -> 0.488 ;
    '1,2 tỷ' -> 1200000000.0 ; 'CMP-FB-001' -> None (khong phai so)."""
    if s is None:
        return None
    text = s.strip()
    if not text:
        return None
    if _ID_LIKE_RE.fullmatch(text):
        return None

    unit_aliases = unit_aliases or {}
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()

    multiplier = 1.0
    lower = text.lower()
    for alias in sorted(unit_aliases, key=len, reverse=True):
        alias_lower = alias.lower()
        if lower.endswith(alias_lower) and (
            len(text) == len(alias) or text[-len(alias) - 1].isspace()
        ):
            text = text[: len(text) - len(alias)].strip()
            lower = text.lower()
            multiplier = unit_aliases[alias]
            break
    else:
        for suffix in _UNIT_SUFFIXES_NO_MULTIPLIER:
            if lower.endswith(suffix) and (
                len(text) == len(suffix) or text[-len(suffix) - 1].isspace()
            ):
                text = text[: len(text) - len(suffix)].strip()
                break

    text = text.replace(chr(0x20), "").replace(chr(0xA0), "")  # xoa khoang trang ASCII va NBSP (dung chr() de tranh nhung ky tu an trong source)
    if not text:
        return None

    value = _parse_core_number(text)
    if value is None:
        return None

    value *= multiplier
    if is_percent:
        value /= 100.0
    return value


def _parse_core_number(text: str) -> float | None:
    negative = text.startswith("-")
    body = text[1:] if negative else text

    # Dang vi-VN co phan nghin: MOI nhom sau dau '.' phai DUNG 3 so.
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", body):
        int_part, _, dec_part = body.partition(",")
        digits = int_part.replace(".", "")
        num_str = f"{digits}.{dec_part}" if dec_part else digits
        value = float(num_str)
    elif re.fullmatch(r"\d+(,\d+)?", body):
        # Khong co phan nghin: so nguyen thuan, hoac "so,thap_phan" (vi-VN).
        value = float(body.replace(",", "."))
    elif re.fullmatch(r"\d+\.\d{1,2}", body):
        # ASSUMPTION: fallback cho so kieu Anh lot vao van ban (vi du model
        # hallucinate "6.20" thay vi dung the) - CHI khi phan sau dau cham co
        # 1-2 so (khac voi nhom phan nghin luon DUNG 3 so o tren), de van bat
        # duoc "chu so tran" kieu Anh thay vi bo qua no.
        value = float(body)
    else:
        return None

    return -value if negative else value


def strip_substituted_spans(text: str) -> str:
    """Bo qua cac doan da the vao tu Cell.formatted khi quet so tran - vi du
    khong quet lai chinh con so vua duoc dien tu the. Trien khai don gian:
    khong the phan biet duoc doan nao la "the vua thay" chi tu chuoi cuoi
    cung (thong tin do da mat sau khi thay the), nen ham nay hien tai la
    identity - viec loai tru dua vao EvidenceSet.matches_any_cell() o buoc
    sau: mot so tran KHOP mot o van duoc coi la "co can cu" (chi la khong
    dung dinh dang the), khong bi chan."""
    return text


def extract_evidence_refs(text: str) -> list[str]:
    return [m.group(1) for m in TAG_RE.finditer(text)]


def find_bare_numbers(
    text: str, unit_suffixes: tuple[str, ...] = (),
) -> list[str]:
    """Tim moi chuoi TRONG GIONG so vi-VN trong `text`, LOAI TRU nhung gi nam
    trong ma dinh danh (CMP-FB-001) hay trong chinh mot the {{...}}.

    Ket qua la CHUOI DAY DU, KE CA hau to '%' hoac don vi tieng Viet ('tỷ',
    'triệu', ... - truyen vao qua `unit_suffixes`, thuong la cfg.unit_aliases)
    di NGAY SAU so - neu chi tra ve phan chu so se mat het thong tin ve bac
    do lon truoc khi toi parse_vi_number() (vi du "1,2" thay vi "1,2 tỷ" lam
    mat he so nhan 10^9)."""
    text_without_tags = TAG_RE.sub(" ", text)
    all_suffixes = sorted(
        {s.lower() for s in unit_suffixes} | set(_UNIT_SUFFIXES_NO_MULTIPLIER),
        key=len, reverse=True,
    )
    results: list[str] = []
    for m in _VI_NUMBER_CORE.finditer(text_without_tags):
        start, end = m.span()
        # Bo qua neu ngay truoc/sau la mot phan cua ma dinh danh dang CMP-FB-001.
        context = text_without_tags[max(0, start - 6) : end + 6]
        if _ID_LIKE_RE.search(context):
            continue
        end = _extend_with_unit_suffix(text_without_tags, end, all_suffixes)
        results.append(text_without_tags[start:end])
    return results


def _extend_with_unit_suffix(text: str, end: int, suffixes_longest_first: list[str]) -> int:
    """Neu ngay sau vi tri `end` la '%' (khong khoang trang) hoac mot khoang
    trang roi mot tu trong `suffixes_longest_first`, mo rong `end` de gom no
    vao. Sap xep dai truoc de "trieu" khong bi "tr" khop truoc mat phan con lai."""
    if end < len(text) and text[end] == "%":
        return end + 1
    rest = text[end:]
    stripped = rest.lstrip(chr(0x20) + chr(0xA0))  # space + NBSP - dung chr() de tranh ky tu an
    gap = len(rest) - len(stripped)
    if gap == 0:
        return end
    for suf in suffixes_longest_first:
        if stripped[: len(suf)].lower() == suf and (
            len(stripped) == len(suf) or not stripped[len(suf)].isalnum()
        ):
            return end + gap + len(suf)
    return end


def split_sentences_vi(text: str) -> list[str]:
    """Tach cau don gian theo dau cham/hoi/than/xuong dong. Khong xu ly viet
    tat (vi du "TP.HCM") - du an nay khong can do chinh xac cap do NLP, chi
    can nhom du "the/marker nao nam trong cung mot phat bieu"."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def normalize_vi(text: str) -> str:
    """Ha thuong + bo dau, dung cho so sanh marker/fuzzy khong phan biet hoa-thuong."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def contains_any_marker(sentence: str, markers: tuple[str, ...]) -> list[str]:
    norm = normalize_vi(sentence)
    return [m for m in markers if normalize_vi(m) in norm]


# CHU Y: KHONG dung character-class dang [A-ZÀ-Ỵ] de kiem tra "chu hoa" -
# khoi Unicode Latin Extended Additional (chua cac ky tu tieng Viet co dau)
# DAN CHU HOA/THUONG THEO CAP LIEN TIEP (vi du U+1EA0 'Ạ' hoa, U+1EA1 'ạ'
# thuong, U+1EA2 'Ả' hoa, U+1EA3 'ả' thuong, ...) nen mot khoang code-point
# tu chu hoa nay den chu hoa khac se VO TINH khop luon ca cac chu thuong nam
# giua - da tung gay bug thuc te: "chiến dịch đang lỗ" bi cat nham thanh
# "ịch đang" vi 'ị' (U+1ECB) nam trong khoang À(U+00C0)-Ỵ(U+1EF4) du la chu
# thuong. Dung `str.isupper()` (Unicode-aware, dung dan) cho tung tu thay vi
# doan mot khoang code-point.
_WORD_RE = re.compile(r"\w+")
_GAP_ONLY_SPACE_OR_HYPHEN_RE = re.compile(r"^[\s-]+$")


def _find_title_sequences(text: str) -> list[str]:
    """Tim CHUOI >= 2 tu lien tiep DEU viet hoa chu dau, chi duoc noi nhau
    bang khoang trang/gach ngang (khong phai dau cau khac nhu ':' hay ',').
    Vi du "Vay Tieu Dung - Broker Network" -> mot chuoi; "ROMI" dung mot minh
    (khong co tu viet hoa lien ke) thi BO QUA co y (xem docstring goi ham)."""
    words = list(_WORD_RE.finditer(text))
    result: list[str] = []
    i = 0
    n = len(words)
    while i < n:
        if not words[i].group()[0].isupper():
            i += 1
            continue
        j = i
        while j + 1 < n:
            gap = text[words[j].end() : words[j + 1].start()]
            if _GAP_ONLY_SPACE_OR_HYPHEN_RE.match(gap) and words[j + 1].group()[0].isupper():
                j += 1
            else:
                break
        if j > i:
            result.append(text[words[i].start() : words[j].end()])
            i = j + 1
        else:
            i += 1
    return result


def extract_proper_nouns_vi(text: str, id_patterns: tuple[str, ...] = ()) -> set[str]:
    """Trich TEN RIENG co the la thuc the can kiem tra (L3). Tieng Viet
    KHONG viet hoa danh tu chung nhu tieng Anh, nen heuristic o day khac han:
    thay vi "moi chu viet hoa la nghi ngo", chi bat (a) ma dinh danh dang
    CMP-*/CUS-*/... va (b) CHUOI >= 2 tu lien tiep DEU viet hoa chu dau (vi
    du "Broker Network", "Zalo Remarketing") - mot tu viet hoa DON LE (thuong
    la dau cau hoac dau ten rieng mot tu, kho phan biet voi dau cau thong
    thuong trong tieng Viet) bi BO QUA co y, danh doi recall thap de precision
    cao (xem docs/08 muc 8.6 ve trade-off nay)."""
    found: set[str] = set()

    text_no_tags = TAG_RE.sub(" ", text)

    for pattern in id_patterns:
        for m in re.finditer(pattern.strip("^$"), text_no_tags):
            found.add(m.group())

    for seq in _find_title_sequences(text_no_tags):
        found.add(seq.strip())

    return found


__all__ = [
    "TAG_RE", "parse_vi_number", "strip_substituted_spans", "extract_evidence_refs",
    "find_bare_numbers", "split_sentences_vi", "normalize_vi", "contains_any_marker",
    "extract_proper_nouns_vi",
]
