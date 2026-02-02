from __future__ import annotations

from typing import Iterable, List, Sequence


def bytes_to_bits(data: bytes) -> List[int]:
    bits: List[int] = []
    for b in data:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits


def bits_to_bytes(bits: Sequence[int]) -> bytes:
    if not bits:
        return b""
    length = len(bits) // 8 * 8
    bits = bits[:length]
    out = bytearray()
    for i in range(0, length, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | (bits[i + j] & 1)
        out.append(byte)
    return bytes(out)


def pack_bitstream(chunks: Iterable[bytes]) -> bytes:
    return b"".join(chunks)


def unpack_bitstream(data: bytes, lengths: Sequence[int]) -> list[bytes]:
    res = []
    pos = 0
    for L in lengths:
        res.append(data[pos : pos + L])
        pos += L
    res.append(data[pos:])
    return res
