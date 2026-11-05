"""qr.py — QR encoder (byte mode, ECC level M, versions 1–10) checked against ISO/IEC 18004 values and a real decoder."""
import re

import pytest

from app import qr

# byte-mode capacity at level M (ISO/IEC 18004 table 7)
CAPACITY_M = {1: 14, 2: 26, 3: 42, 4: 62, 5: 84, 6: 106, 7: 122, 8: 152, 9: 180, 10: 213}


def test_reed_solomon_reference_vector():
    # thonky.com QR tutorial, version 1-M "HELLO WORLD"
    ecc = qr._rs_remainder([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236], qr._rs_divisor(13))
    assert ecc == [168, 72, 22, 82, 217, 54, 156, 0, 46, 15, 180, 122, 16]


def test_format_and_version_information_bits():
    expected = ["101010000010010", "101000100100101", "101111001111100", "101101101001011",
                "100010111111001", "100000011001110", "100111110010111", "100101010100000"]
    assert [format(qr._format_bits(m), "015b") for m in range(8)] == expected
    assert format(qr._version_bits(7), "018b") == "000111110010010100"
    assert format(qr._version_bits(10), "018b") == "001010010011010011"


def test_data_codeword_counts_match_the_standard():
    assert [qr._data_codewords(v) for v in range(1, 11)] == [16, 28, 44, 64, 86, 108, 124, 154, 182, 216]


@pytest.mark.parametrize("version, cap", CAPACITY_M.items())
def test_smallest_version_is_chosen(version, cap):
    assert qr.QR("a" * cap).ver == version
    if version < 10:
        assert qr.QR("a" * (cap + 1)).ver == version + 1


def test_text_too_long_raises():
    with pytest.raises(ValueError):
        qr.QR("a" * 214)
    assert qr.QR("ə" * 106).ver == 10            # UTF-8: two bytes per character


def _finder_ok(m, x0, y0):
    for dy in range(7):
        for dx in range(7):
            ring = max(abs(dx - 3), abs(dy - 3))
            if m[y0 + dy][x0 + dx] != (ring != 2):
                return False
    return True


@pytest.mark.parametrize("text", ["A", "https://zeka.example.az/verify/ABCD-EFGH", "x" * 150])
def test_function_patterns(text):
    q = qr.QR(text)
    n, m = q.size, q.modules
    assert n == q.ver * 4 + 17 and len(m) == n and all(len(row) == n for row in m)
    assert _finder_ok(m, 0, 0) and _finder_ok(m, n - 7, 0) and _finder_ok(m, 0, n - 7)
    assert all(m[6][i] == (i % 2 == 0) for i in range(8, n - 8))        # timing patterns
    assert all(m[i][6] == (i % 2 == 0) for i in range(8, n - 8))
    assert m[n - 8][8] is True                                           # the dark module
    assert 0 <= q.mask < 8


def test_output_is_deterministic():
    assert qr.qr_svg("https://x/verify/AAAA-BBBB") == qr.qr_svg("https://x/verify/AAAA-BBBB")


def test_svg_markup():
    q = qr.QR("hello")
    svg = q.svg(scale=3, border=2)
    dim = q.size + 4
    assert svg.startswith("<svg") and f'viewBox="0 0 {dim} {dim}"' in svg and f'width="{dim * 3}"' in svg
    assert 'role="img"' in svg and 'aria-label="QR kod"' in svg
    assert len(re.findall(r"M\d+,\d+h1v1h-1z", svg)) == sum(map(sum, q.modules))


def _image(q, scale=4, border=4):
    np = pytest.importorskip("numpy")
    n = q.size
    img = np.full(((n + 2 * border) * scale,) * 2, 255, np.uint8)
    for y in range(n):
        for x in range(n):
            if q.modules[y][x]:
                img[(y + border) * scale:(y + border + 1) * scale, (x + border) * scale:(x + border + 1) * scale] = 0
    return img


@pytest.mark.parametrize("text", [
    "A", "https://zeka-aztu.onrender.com/verify/K7QM-2HXP", "http://127.0.0.1:5070/verify/" + "Z" * 100,
    "Aysel Məmmədova — arayış", "x" * 213,
] + ["v" * cap for cap in CAPACITY_M.values()])
def test_codes_decode_with_an_independent_reader(text):
    """zxing-cpp (installed in CI via requirements-dev.txt) must read back exactly the encoded text."""
    zxingcpp = pytest.importorskip("zxingcpp")
    q = qr.QR(text)
    results = zxingcpp.read_barcodes(_image(q))
    assert [r.text for r in results] == [text]
    assert str(results[0].format) == "QR Code" or "QR" in str(results[0].format)
