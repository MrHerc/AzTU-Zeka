"""Minimal QR code encoder (byte mode, error correction level M, versions 1-10).

Dependency-free; renders to SVG. Enough for verification URLs (<= 213 bytes).
"""

ECC_PER_BLOCK = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
NUM_BLOCKS = [None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
ALIGN_POS = [None, [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34],
             [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]]
ECL_M_BITS = 0  # format bits for level M


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _raw_modules(ver):
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver):
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[ver] * NUM_BLOCKS[ver]


def _format_bits(mask):
    data = ECL_M_BITS << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


def _version_bits(ver):
    rem = ver
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return ver << 12 | rem


class QR:
    def __init__(self, text: str):
        data = text.encode("utf-8")
        for ver in range(1, 11):
            count_bits = 8 if ver < 10 else 16
            if 4 + count_bits + 8 * len(data) <= _data_codewords(ver) * 8:
                break
        else:
            raise ValueError("QR: mətn çox uzundur")
        self.ver = ver
        self.size = ver * 4 + 17
        bits = []

        def put(val, n):
            bits.extend((val >> i) & 1 for i in reversed(range(n)))

        put(0b0100, 4)
        put(len(data), count_bits)
        for b in data:
            put(b, 8)
        cap = _data_codewords(ver) * 8
        put(0, min(4, cap - len(bits)))
        put(0, (8 - len(bits) % 8) % 8)
        pad = 0xEC
        while len(bits) < cap:
            put(pad, 8)
            pad ^= 0xEC ^ 0x11
        codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
        self.codewords = self._add_ecc(codewords)
        n = self.size
        self.modules = [[False] * n for _ in range(n)]
        self.isfunc = [[False] * n for _ in range(n)]
        self._draw_function_patterns()
        self._draw_codewords()
        best, best_pen = 0, None
        for mask in range(8):
            self._apply_mask(mask)
            self._draw_format(mask)
            pen = self._penalty()
            if best_pen is None or pen < best_pen:
                best, best_pen = mask, pen
            self._apply_mask(mask)  # undo (XOR)
        self._apply_mask(best)
        self._draw_format(best)
        self.mask = best

    # --- construction -------------------------------------------------
    def _add_ecc(self, data):
        ver = self.ver
        nblocks, ecc_len = NUM_BLOCKS[ver], ECC_PER_BLOCK[ver]
        raw = _raw_modules(ver) // 8
        n_short = nblocks - raw % nblocks
        short_len = raw // nblocks
        div = _rs_divisor(ecc_len)
        blocks, k = [], 0
        for i in range(nblocks):
            dlen = short_len - ecc_len + (0 if i < n_short else 1)
            dat = data[k:k + dlen]
            k += dlen
            ecc = _rs_remainder(dat, div)
            if i < n_short:
                dat = dat + [0]
            blocks.append(dat + ecc)
        result = []
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                if i != short_len - ecc_len or j >= n_short:
                    result.append(blk[i])
        return result

    def _set_func(self, x, y, dark):
        self.modules[y][x] = dark
        self.isfunc[y][x] = True

    def _draw_function_patterns(self):
        n = self.size
        for i in range(n):
            self._set_func(6, i, i % 2 == 0)
            self._set_func(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self._set_func(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = ALIGN_POS[self.ver]
        last = len(pos) - 1
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set_func(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0)
        if self.ver >= 7:
            vb = _version_bits(self.ver)
            for i in range(18):
                bit = (vb >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self._set_func(a, b, bit)
                self._set_func(b, a, bit)

    def _draw_format(self, mask):
        n = self.size
        bits = _format_bits(mask)
        g = lambda i: (bits >> i) & 1 == 1
        for i in range(6):
            self._set_func(8, i, g(i))
        self._set_func(8, 7, g(6))
        self._set_func(8, 8, g(7))
        self._set_func(7, 8, g(8))
        for i in range(9, 15):
            self._set_func(14 - i, 8, g(i))
        for i in range(8):
            self._set_func(n - 1 - i, 8, g(i))
        for i in range(8, 15):
            self._set_func(8, n - 15 + i, g(i))
        self._set_func(8, n - 8, True)

    def _draw_codewords(self):
        n = self.size
        data = self.codewords
        i = 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (n - 1 - vert) if upward else vert
                    if not self.isfunc[y][x] and i < len(data) * 8:
                        self.modules[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def _apply_mask(self, mask):
        conds = [
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        ]
        c = conds[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.isfunc[y][x] and c(x, y):
                    self.modules[y][x] = not self.modules[y][x]

    def _penalty(self):
        n, m = self.size, self.modules
        pen = 0
        lines = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
        pat1 = [True, False, True, True, True, False, True, False, False, False, False]
        pat2 = pat1[::-1]
        for line in lines:
            run, prev = 0, None
            for v in line:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        pen += 3 + run - 5
                    run, prev = 1, v
            if run >= 5:
                pen += 3 + run - 5
            for i in range(n - 10):
                seg = line[i:i + 11]
                if seg == pat1 or seg == pat2:
                    pen += 40
        for y in range(n - 1):
            for x in range(n - 1):
                v = m[y][x]
                if v == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    pen += 3
        dark = sum(v for row in m for v in row)
        total = n * n
        k = int(abs(dark * 20 - total * 10) / total)
        pen += k * 10
        return pen

    # --- output ---------------------------------------------------------
    def svg(self, scale=4, border=4, dark="#0f172a", light="#ffffff"):
        n = self.size
        dim = (n + border * 2)
        parts = []
        for y in range(n):
            for x in range(n):
                if self.modules[y][x]:
                    parts.append(f"M{x + border},{y + border}h1v1h-1z")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
            f'width="{dim * scale}" height="{dim * scale}" shape-rendering="crispEdges" role="img" aria-label="QR kod">'
            f'<rect width="100%" height="100%" fill="{light}"/>'
            f'<path d="{"".join(parts)}" fill="{dark}"/></svg>'
        )


def qr_svg(text: str, scale: int = 4) -> str:
    return QR(text).svg(scale=scale)
