"""Glodia 'dlz' decompressor - port of the engine routine.

Reversed from the shared library in every Glodia EXP (DEMO2.EXP @0x1583-0x1919).

Format:

  member := 9d 89 'd' 'l' 'z' 00 | u16 comp_size | u16 decomp_size | 3 bytes | stream
  The bitstream starts at member offset 13 (the first 16-bit control word).
  comp_size counts the stream bytes (member offset 13 .. 13+comp_size).

  Control bits come from 16-bit little-endian words, LSB first; a new word is
  fetched from the byte stream after the 16th bit of the previous one is used.
  Offsets are byte-granular negative displacements from the current output
  position; they may reach below the start of the member's own output (the
  engine decompresses members back-to-back into one buffer, so earlier members
  act as a preset dictionary).

  loop:
    bit==1        -> literal: copy 1 byte from stream
    bit==0, bit==1-> LONG:  off = stream byte; esi = off-256; gamma-style header
                     builds high offset bits (see _long_offset); then unary/binary
                     length code: 3,4,5,6,7,8,9..16,(byte+17 -> 17..272);
                     copy `len` bytes from out+esi (emulating movsb/movsw/rep movsd:
                     1-, 2-, then 4-byte units, each read whole before writing)
    bit==0, bit==0-> SHORT: off = stream byte; esi = off-256
        bit==1    ->   MEDIUM: esi -= 0x100; three more bits b4,b5,b6: each ==0
                       subtracts 0x400/0x200/0x100; copy ONE 16-bit word
        bit==0    ->   if off==0xff: next bit 1 = no-op (resync), 0 = END
                       else copy ONE 16-bit word from out+esi
"""
import struct

MAGIC = b"\x9d\x89dlz\x00"
STREAM_START = 13


class _Bits:
    def __init__(self, src, pos):
        self.src = src
        self.pos = pos          # byte position of NEXT fetch
        self.val = src[pos] | (src[pos + 1] << 8)
        self.pos += 2
        self.n = 16

    def bit(self):
        b = self.val & 1
        self.val >>= 1
        self.n -= 1
        if self.n == 0:
            self.val = self.src[self.pos] | (self.src[self.pos + 1] << 8)
            self.pos += 2
            self.n = 16
        return b

    def byte(self):
        v = self.src[self.pos]
        self.pos += 1
        return v


def parse_header(member):
    if member[:6] != MAGIC:
        raise ValueError(f"bad dlz magic: {member[:6].hex()}")
    comp_size, decomp_size = struct.unpack("<HH", member[6:10])
    return comp_size, decomp_size


def decode(member, prefix=b"", max_out=1 << 22):
    """Decompress one dlz member. `prefix` = bytes already in the output buffer
    before this member (reachable by far back-references). Returns the new bytes.
    """
    bs = _Bits(member, STREAM_START)
    out = bytearray(prefix)
    base = len(prefix)

    def copy_unit(dist, size):
        # one movs unit: read `size` bytes as a whole, then append
        p = len(out) + dist
        if p < 0:
            raise ValueError(f"back-reference before buffer: dist={dist} at out+{len(out)-base}")
        chunk = bytes(out[p:p + size])
        if len(chunk) < size:        # reads past write pointer = stale RAM
            raise ValueError(f"overlapping read past output: dist={dist} size={size}")
        out.extend(chunk)

    while len(out) - base < max_out:
        if bs.bit():                                  # literal
            out.append(bs.byte())
            continue
        if bs.bit():                                  # LONG form
            esi = bs.byte() - 256
            ch = 0
            if not bs.bit():
                ch += 1
            while True:
                if bs.bit():
                    break
                esi -= 0x200
                if bs.bit():
                    break
                ch <<= 1
                if not bs.bit():
                    ch += 1
                esi -= 0x200
                if bs.bit():
                    break
                ch <<= 1
                if not bs.bit():
                    ch += 1
                esi -= 0x400
                if bs.bit():
                    break
                esi -= 0x800
                ch <<= 1
                if not bs.bit():
                    ch += 1
                break
            esi -= ch << 8
            # length: unary 3..6, then 7/8, 9..16 (3-bit), or byte+17
            if bs.bit():
                n = 3
            elif bs.bit():
                n = 4
            elif bs.bit():
                n = 5
            elif bs.bit():
                n = 6
            elif bs.bit():
                n = 8 if bs.bit() else 7
            elif bs.bit():
                n = bs.byte() + 0x11
            else:
                n = 9
                if bs.bit():
                    n += 4
                if bs.bit():
                    n += 2
                if bs.bit():
                    n += 1
            # rep-movs emulation: movsb if n&1, movsw if n&2, then n>>2 movsd
            if n & 1:
                copy_unit(esi, 1)
            if n & 2:
                copy_unit(esi, 2)
            for _ in range(n >> 2):
                copy_unit(esi, 4)
            continue
        # SHORT / MEDIUM
        esi = bs.byte() - 256
        if bs.bit():                                  # MEDIUM
            esi -= 0x100
            if not bs.bit():
                esi -= 0x400
            if not bs.bit():
                esi -= 0x200
            if not bs.bit():
                esi -= 0x100
            copy_unit(esi, 2)
        elif esi == -1:                               # escape
            if bs.bit():
                continue                              # no-op / resync
            break                                     # end of stream
        else:
            copy_unit(esi, 2)
    return bytes(out[base:])


DEST = 0x40000   # the game decompresses scenes into a buffer here; seed the output
                 # prefix to that size so far back-references resolve like on hardware.


def decode_block(member):
    """decode() with the standard 0x40000 output prefix every archive member uses."""
    return decode(member, prefix=bytes(DEST))


class _BitWriter:
    """Interleaves 16-bit LSB-first control words with data bytes, mirroring the
    engine's eager refill: the moment the 16th bit is consumed, the next control
    word is reserved at the current stream position."""

    def __init__(self):
        self.buf = bytearray()
        self._reserve()

    def _reserve(self):
        self.ctrl_pos = len(self.buf)
        self.buf += b"\x00\x00"
        self.ctrl_val = 0
        self.nbits = 0

    def bit(self, b):
        if b:
            self.ctrl_val |= 1 << self.nbits
        self.nbits += 1
        if self.nbits == 16:
            self.buf[self.ctrl_pos:self.ctrl_pos + 2] = struct.pack("<H", self.ctrl_val)
            self._reserve()

    def byte(self, v):
        self.buf.append(v)

    def finish(self, trim=False):
        # flush the partial (or freshly reserved) control word
        self.buf[self.ctrl_pos:self.ctrl_pos + 2] = struct.pack("<H", self.ctrl_val)
        if trim and self.nbits == 0 and self.ctrl_pos == len(self.buf) - 2:
            # the freshly reserved word holds no bits; the decoder's eager refill
            # still reads 2 bytes here, so only trim when padding will cover them
            return bytes(self.buf[:-2])
        return bytes(self.buf)


def _emit_long_offset(w, dist, v_low):
    """Offset-extension bit chain for the LONG form (see decode())."""
    base = 256 - v_low
    rest = dist - base                  # multiple of 0x100
    if rest < 0x200:                    # exit at B: ch in {0,1}
        ch = rest >> 8
        w.bit(0 if ch else 1)           # A: bit==0 -> ch += 1
        w.bit(1)                        # B: finish
    elif rest < 0x400:                  # exit at C: dist tier +0x200, ch in {0,1}
        ch = (rest - 0x200) >> 8
        w.bit(0 if ch else 1)
        w.bit(0)
        w.bit(1)
    elif rest < 0x800:                  # exit at E: +0x400, ch in 0..3
        ch = (rest - 0x400) >> 8
        w.bit(0 if ch & 2 else 1)       # A
        w.bit(0)                        # B cont
        w.bit(0)                        # C cont
        w.bit(0 if ch & 1 else 1)       # D
        w.bit(1)                        # E: finish
    elif rest < 0x1000:                 # exit at G: +0x800, ch in 0..7
        ch = (rest - 0x800) >> 8
        w.bit(0 if ch & 4 else 1)
        w.bit(0)
        w.bit(0)
        w.bit(0 if ch & 2 else 1)
        w.bit(0)
        w.bit(0 if ch & 1 else 1)
        w.bit(1)                        # G: finish
    else:                               # fall through H: +0x1000, ch in 0..15
        ch = (rest - 0x1000) >> 8
        w.bit(0 if ch & 8 else 1)
        w.bit(0)
        w.bit(0)
        w.bit(0 if ch & 4 else 1)
        w.bit(0)
        w.bit(0 if ch & 2 else 1)
        w.bit(0)
        w.bit(0 if ch & 1 else 1)


MAX_DIST = 8192                         # 256 + 0x1000 + 15*0x100
MAX_LEN = 272


def _emit_length(w, n):
    if n == 3:
        w.bit(1)
    elif n == 4:
        w.bit(0); w.bit(1)
    elif n == 5:
        w.bit(0); w.bit(0); w.bit(1)
    elif n == 6:
        w.bit(0); w.bit(0); w.bit(0); w.bit(1)
    elif n in (7, 8):
        for _ in range(4):
            w.bit(0)
        w.bit(1)
        w.bit(1 if n == 8 else 0)
    elif 9 <= n <= 16:
        for _ in range(6):
            w.bit(0)
        r = n - 9
        w.bit(1 if r & 4 else 0)
        w.bit(1 if r & 2 else 0)
        w.bit(1 if r & 1 else 0)
    else:                               # 17..272
        for _ in range(5):
            w.bit(0)
        w.bit(1)
        w.byte(n - 0x11)


def encode(data, dest_addr=0, pad_to=None):
    """Compress `data` into a full dlz member (header + stream).

    Greedy matcher emitting only constructs the engine decoder accepts:
    literals, SHORT word copies (dist 2..256), MEDIUM word copies (dist
    257..2304), LONG byte copies (len 3..272, dist 4..8192). References never
    reach before `data` start. `pad_to` pads the member with zero bytes after
    the terminator up to an exact member size (raises if it doesn't fit).
    """
    n = len(data)

    def long_off_bits(dist):
        rest = dist - (((dist - 1) & 0xFF) + 1)
        if rest < 0x200:
            return 2
        if rest < 0x400:
            return 3
        if rest < 0x800:
            return 5
        if rest < 0x1000:
            return 7
        return 8

    def long_len_bits(l):
        if l <= 6:
            return l - 2            # 3->1, 4->2, 5->3, 6->4
        if l <= 8:
            return 6
        if l <= 16:
            return 9
        return 6 + 8                # explicit byte

    # --- pass 1: for every position, min dist achieving each match length ---
    heads = {}
    cands = [None] * n              # pos -> list of (length, mindist) frontier
    for p in range(n - 1):
        key = data[p:p + 2]
        chain = heads.get(key)
        if chain:
            frontier = []           # (len, dist), increasing len, dist = min for >= len
            best = 0
            for cand in reversed(chain):
                dist = p - cand
                if dist > MAX_DIST:
                    break
                l = 0
                limit = min(MAX_LEN, n - p)
                while l < limit and data[cand + l] == data[p + l]:
                    l += 1
                if l > best:        # nearer cands come first, so only longer is news
                    frontier.append((l, dist))
                    best = l
                    if l >= limit:
                        break
            cands[p] = frontier or None
        heads.setdefault(key, []).append(p)

    # --- pass 2: DP over exact bit costs, right to left ---
    INF = float("inf")
    cost = [0.0] * (n + 1)
    choice = [None] * n             # None = literal, else (length, dist)
    for p in range(n - 1, -1, -1):
        best = 9 + cost[p + 1]      # literal
        pick = None
        for l, dist in cands[p] or ():
            # word copy of 2 (any frontier entry with len>=2 allows dist)
            if 2 <= dist <= 256 and dist != 1:
                c = 11 + cost[p + 2]
                if c < best:
                    best, pick = c, (2, dist)
            elif 257 <= dist <= 2304:
                c = 14 + cost[p + 2]
                if c < best:
                    best, pick = c, (2, dist)
            if dist >= 2:
                ob = long_off_bits(dist)
                # len-3 copies use movsb+movsw only -> safe from dist 2;
                # len>=4 includes movsd units -> needs dist >= 4
                top = l if dist >= 4 else min(l, 3)
                for ll in range(3, top + 1):
                    c = 10 + ob + long_len_bits(ll) + cost[p + ll]
                    if c < best:
                        best, pick = c, (ll, dist)
        cost[p] = best
        choice[p] = pick

    # --- pass 3: emit ---
    w = _BitWriter()
    pos = 0
    while pos < n:
        pick = choice[pos]
        if pick is None:
            w.bit(1)
            w.byte(data[pos])
            pos += 1
            continue
        length, dist = pick
        if length == 2:
            if 2 <= dist <= 256:
                w.bit(0); w.bit(0)
                w.byte(256 - dist)
                w.bit(0)
            else:                   # medium
                ext = (dist - 257) >> 8
                v = (0x200 - (dist - ext * 0x100)) & 0xFF
                w.bit(0); w.bit(0)
                w.byte(v)
                w.bit(1)
                w.bit(0 if ext & 4 else 1)
                w.bit(0 if ext & 2 else 1)
                w.bit(0 if ext & 1 else 1)
        else:                       # long
            v = (256 - (((dist - 1) & 0xFF) + 1)) & 0xFF
            w.bit(0); w.bit(1)
            w.byte(v)
            _emit_long_offset(w, dist, v)
            _emit_length(w, length)
        pos += length
    # terminator: SHORT form, offset byte 0xff, then bit 0 = end of stream
    w.bit(0); w.bit(0)
    w.byte(0xFF)
    w.bit(0)
    w.bit(0)
    stream = w.finish(trim=pad_to is not None)
    if len(stream) < 4:
        stream += b"\x00" * (4 - len(stream))
    member = bytearray(MAGIC)
    member += struct.pack("<HH", len(stream), min(len(data), 0xFFFF))
    member += bytes([dest_addr & 0xFF, (dest_addr >> 8) & 0xFF, (dest_addr >> 16) & 0xFF])
    member += stream
    if pad_to is not None:
        if len(member) > pad_to:
            raise ValueError(f"encoded member {len(member)} > pad_to {pad_to}")
        member += b"\x00" * (pad_to - len(member))
        member[6:8] = struct.pack("<H", pad_to - STREAM_START)
    return bytes(member)


def iter_members(archive):
    """Yield (offset, member_bytes) for each dlz member in a VAIN_*.DAT archive."""
    pos = 0
    while True:
        pos = archive.find(MAGIC, pos)
        if pos == -1:
            return
        comp, _ = parse_header(archive[pos:pos + 10])
        end = pos + STREAM_START + comp
        yield pos, archive[pos:end]
        pos = end
