# bodn/qr.py — Minimal QR code encoder for short URLs
#
# Supports Version 1 (21×21, up to 17 bytes) and Version 2 (25×25, up to 32 bytes)
# with error correction level L (7% recovery).
# Byte mode encoding only — sufficient for URLs.
#
# Usage:
#   from bodn.qr import encode
#   matrix = encode("http://192.168.4.1")  # returns list of lists (0/1)

# GF(256) arithmetic for Reed-Solomon
_EXP = [0] * 256
_LOG = [0] * 256
_v = 1
for _i in range(255):
    _EXP[_i] = _v
    _LOG[_v] = _i
    _v <<= 1
    if _v >= 256:
        _v ^= 0x11D
_EXP[255] = _EXP[0]


def _rs_encode(data, n_ecc):
    """Reed-Solomon error correction codewords."""
    # Generator polynomial coefficients
    gen = [0] * (n_ecc + 1)
    gen[0] = 1
    for i in range(n_ecc):
        for j in range(i + 1, -1, -1):
            gen[j] = gen[j - 1] if j > 0 else 0
            if j > 0:
                gen[j] ^= _gf_mul(gen[j], _EXP[i])
            else:
                gen[j] = _gf_mul(gen[j], _EXP[i])
    # Wait, simpler approach for generator:
    gen = [1]
    for i in range(n_ecc):
        new_gen = [0] * (len(gen) + 1)
        for j in range(len(gen)):
            new_gen[j] ^= gen[j]
            new_gen[j + 1] ^= _gf_mul(gen[j], _EXP[i])
        gen = new_gen

    # Polynomial division
    msg = list(data) + [0] * n_ecc
    for i in range(len(data)):
        if msg[i] == 0:
            continue
        log_m = _LOG[msg[i]]
        for j in range(1, len(gen)):
            msg[i + j] ^= _EXP[(log_m + _LOG[gen[j]]) % 255]
    return msg[len(data) :]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[(_LOG[a] + _LOG[b]) % 255]


# Format info strings (15 bits) for mask 0-7, ECC level L
_FORMAT_INFO = [
    0x77C4,
    0x72F3,
    0x7DAA,
    0x789D,
    0x662F,
    0x6318,
    0x6C41,
    0x6976,
]

# Version info — not needed for V1-V2


def encode(text):
    """Encode text as a QR code. Returns 2D list of 0 (white) / 1 (black)."""
    data = text.encode("utf-8") if isinstance(text, str) else text
    n = len(data)

    # Choose version
    if n <= 17:
        ver, size, n_ecc = 1, 21, 7
        total_codewords = 26
    elif n <= 32:
        ver, size, n_ecc = 2, 25, 10
        total_codewords = 44
    else:
        raise ValueError("Data too long for QR V1-V2")

    # Encode data: byte mode (0100), length, data, terminator, padding
    bits = []
    _add_bits(bits, 0b0100, 4)  # mode indicator: byte
    _add_bits(bits, n, 8)  # character count (8 bits for V1-9 byte mode)
    for b in data:
        _add_bits(bits, b, 8)

    # Terminator
    data_cw = total_codewords - n_ecc
    max_bits = data_cw * 8
    term_len = min(4, max_bits - len(bits))
    _add_bits(bits, 0, term_len)

    # Pad to byte boundary
    while len(bits) % 8:
        bits.append(0)

    # Pad codewords
    pad_bytes = [0xEC, 0x11]
    pi = 0
    while len(bits) < max_bits:
        _add_bits(bits, pad_bytes[pi], 8)
        pi ^= 1

    # Convert to bytes
    codewords = []
    for i in range(0, len(bits), 8):
        b = 0
        for j in range(8):
            b = (b << 1) | bits[i + j]
        codewords.append(b)

    # Add ECC
    ecc = _rs_encode(codewords, n_ecc)
    all_cw = codewords + ecc

    # Create matrix
    matrix = [[0] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    # Place finder patterns
    _place_finder(matrix, reserved, 0, 0)
    _place_finder(matrix, reserved, size - 7, 0)
    _place_finder(matrix, reserved, 0, size - 7)

    # Timing patterns
    for i in range(8, size - 8):
        v = 1 if i % 2 == 0 else 0
        matrix[6][i] = v
        matrix[i][6] = v
        reserved[6][i] = True
        reserved[i][6] = True

    # Alignment pattern (V2 only, at position 18,18)
    if ver >= 2:
        _place_alignment(matrix, reserved, 18, 18)

    # Dark module
    matrix[size - 8][8] = 1
    reserved[size - 8][8] = True

    # Reserve format info areas
    for i in range(9):
        reserved[8][i] = True
        reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True

    # Place data bits
    _place_data(matrix, reserved, all_cw, size)

    # Apply best mask
    best_mask = 0
    best_score = 999999
    for mask_id in range(8):
        test = [row[:] for row in matrix]
        _apply_mask(test, reserved, mask_id, size)
        _place_format(test, _FORMAT_INFO[mask_id], size)
        score = _penalty(test, size)
        if score < best_score:
            best_score = score
            best_mask = mask_id

    _apply_mask(matrix, reserved, best_mask, size)
    _place_format(matrix, _FORMAT_INFO[best_mask], size)

    return matrix


def _add_bits(bits, val, n):
    for i in range(n - 1, -1, -1):
        bits.append((val >> i) & 1)


def _place_finder(matrix, reserved, row, col):
    for r in range(-1, 8):
        for c in range(-1, 8):
            rr, cc = row + r, col + c
            if 0 <= rr < len(matrix) and 0 <= cc < len(matrix):
                if 0 <= r <= 6 and 0 <= c <= 6:
                    if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                        matrix[rr][cc] = 1
                    else:
                        matrix[rr][cc] = 0
                else:
                    matrix[rr][cc] = 0
                reserved[rr][cc] = True


def _place_alignment(matrix, reserved, row, col):
    for r in range(-2, 3):
        for c in range(-2, 3):
            rr, cc = row + r, col + c
            if abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0):
                matrix[rr][cc] = 1
            else:
                matrix[rr][cc] = 0
            reserved[rr][cc] = True


def _place_data(matrix, reserved, codewords, size):
    bit_idx = 0
    total_bits = len(codewords) * 8
    col = size - 1
    going_up = True

    while col >= 0:
        if col == 6:
            col -= 1  # skip timing column
            continue
        for row_offset in range(size):
            row = (size - 1 - row_offset) if going_up else row_offset
            for dc in (0, -1):
                cc = col + dc
                if cc < 0 or reserved[row][cc]:
                    continue
                if bit_idx < total_bits:
                    cw_idx = bit_idx // 8
                    bit_pos = 7 - (bit_idx % 8)
                    matrix[row][cc] = (codewords[cw_idx] >> bit_pos) & 1
                    bit_idx += 1
        col -= 2
        going_up = not going_up


def _apply_mask(matrix, reserved, mask_id, size):
    for r in range(size):
        for c in range(size):
            if reserved[r][c]:
                continue
            mask = False
            if mask_id == 0:
                mask = (r + c) % 2 == 0
            elif mask_id == 1:
                mask = r % 2 == 0
            elif mask_id == 2:
                mask = c % 3 == 0
            elif mask_id == 3:
                mask = (r + c) % 3 == 0
            elif mask_id == 4:
                mask = (r // 2 + c // 3) % 2 == 0
            elif mask_id == 5:
                mask = (r * c) % 2 + (r * c) % 3 == 0
            elif mask_id == 6:
                mask = ((r * c) % 2 + (r * c) % 3) % 2 == 0
            elif mask_id == 7:
                mask = ((r + c) % 2 + (r * c) % 3) % 2 == 0
            if mask:
                matrix[r][c] ^= 1


def _place_format(matrix, fmt, size):
    bits = []
    for i in range(14, -1, -1):
        bits.append((fmt >> i) & 1)

    # Around top-left finder
    positions_h = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8)]
    positions_v = [(7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for i, (r, c) in enumerate(positions_h):
        matrix[r][c] = bits[i]
    for i, (r, c) in enumerate(positions_v):
        matrix[r][c] = bits[8 + i]

    # Around other finders
    for i in range(7):
        matrix[size - 1 - i][8] = bits[i]
    for i in range(8):
        matrix[8][size - 8 + i] = bits[7 + i]


def _penalty(matrix, size):
    """Simplified penalty score for mask selection."""
    score = 0
    # Rule 1: runs of same color
    for r in range(size):
        run = 1
        for c in range(1, size):
            if matrix[r][c] == matrix[r][c - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    for c in range(size):
        run = 1
        for r in range(1, size):
            if matrix[r][c] == matrix[r - 1][c]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    return score
