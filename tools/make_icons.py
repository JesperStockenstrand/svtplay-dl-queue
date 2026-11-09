#!/usr/bin/env python3
"""Generate the extension icons (a download arrow on a rounded square).

Pure standard library, so anyone can regenerate them:
    python3 tools/make_icons.py
"""

import os
import struct
import zlib

BG = (43, 108, 176)
FG = (255, 255, 255)
SAMPLES = 4  # supersampling per axis for anti-aliasing


def inside_rounded_square(x, y, r=0.22):
    # Unit square [0,1]^2 with rounded corners of radius r.
    cx = min(max(x, r), 1 - r)
    cy = min(max(y, r), 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def inside_arrow(x, y):
    # Shaft
    if 0.43 <= x <= 0.57 and 0.18 <= y <= 0.52:
        return True
    # Head: triangle with tip at (0.5, 0.70), base from 0.24..0.76 at y=0.46
    if 0.46 <= y <= 0.70:
        half = 0.26 * (0.70 - y) / 0.24
        if abs(x - 0.5) <= half:
            return True
    # Tray
    if 0.22 <= x <= 0.78 and 0.76 <= y <= 0.84:
        return True
    return False


def pixel(px, py, size):
    bg = fg = 0
    n = SAMPLES * SAMPLES
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            x = (px + (sx + 0.5) / SAMPLES) / size
            y = (py + (sy + 0.5) / SAMPLES) / size
            if inside_rounded_square(x, y):
                if inside_arrow(x, y):
                    fg += 1
                else:
                    bg += 1
    cover = bg + fg
    if not cover:
        return (0, 0, 0, 0)
    color = tuple(round((BG[i] * bg + FG[i] * fg) / cover) for i in range(3))
    return color + (round(255 * cover / n),)


def png(size):
    rows = b""
    for y in range(size):
        rows += b"\x00" + b"".join(bytes(pixel(x, y, size)) for x in range(size))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension", "icons")
    os.makedirs(out, exist_ok=True)
    for size in (16, 32, 48, 128):
        with open(os.path.join(out, "icon%d.png" % size), "wb") as f:
            f.write(png(size))
    print("Icons written to", os.path.normpath(out))


if __name__ == "__main__":
    main()
