#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-convert PNG/JPG/JPEG to 256x256 ICO with a transparent white background.

The output is tuned for Windows Explorer and USB ``autorun.inf`` icons:

* exactly one 256x256 layer is written (``sizes=[(256, 256)]``), so Windows
  cannot pick a small resized layer with edge artifacts;
* the layer is stored as BMP (``bitmap_format="bmp"``), not PNG inside the ICO.
  Modern Explorer usually reads PNG-compressed layers, but some legacy shell
  code paths used for autorun icons do not. BMP is the compatible choice;
* alpha is forced to 0 or 255 after resizing, so icons never look pale or
  semi-transparent;
* LANCZOS resizing uses premultiplied alpha, so edge pixels keep the object's
  color instead of being blended with white (no white fringe);
* white is removed only where it is connected to the image border. White
  details inside the drawing (for example slots on a server icon) stay opaque.
  Use ``--remove-all-white`` to remove every near-white pixel instead.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageOps
except ImportError:
    sys.exit("Pillow is not installed. Run: pip install Pillow")

__version__ = "1.0.0"

DEFAULT_THRESHOLD = 235
TARGET_SIZE = (256, 256)
ICO_SIZES = [(256, 256)]
INPUT_EXTS = (".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def get_downloads_dir() -> Path:
    """Return the user's real Downloads folder.

    Windows allows the folder to be relocated, so the known-folder path is
    read from the registry first. On other systems, fall back to
    ``~/Downloads``.
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(
                key, "{374DE290-123F-4565-9164-39C4925E467B}"
            )
        if value:
            path = Path(os.path.expandvars(value))
            if path.is_dir():
                return path
    except Exception:
        pass

    path = Path.home() / "Downloads"
    if path.is_dir():
        return path

    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads"


def near_white_mask(img: Image.Image, threshold: int) -> Image.Image:
    """Return an L mask: 255 where the pixel is near-white, 0 elsewhere."""
    r, g, b = img.convert("RGB").split()
    mask = r.point(lambda v: 255 if v > threshold else 0)
    mask = ImageChops.multiply(
        mask, g.point(lambda v: 255 if v > threshold else 0)
    )
    mask = ImageChops.multiply(
        mask, b.point(lambda v: 255 if v > threshold else 0)
    )
    return mask


def background_mask(
    img: Image.Image, threshold: int, keep_inner_white: bool
) -> Image.Image:
    """Return an L mask: 255 where the background should be removed.

    With ``keep_inner_white`` (default), only near-white areas connected to
    the image border are treated as background. Enclosed white details stay
    part of the icon.
    """
    white = near_white_mask(img, threshold)

    if not keep_inner_white:
        return white

    work = white.copy()
    w, h = work.size
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if work.getpixel(seed) == 255:
            # 128 marks the border-connected background. thresh=0 keeps the
            # flood fill inside pixels that already passed the white test.
            ImageDraw.floodfill(work, seed, 128, thresh=0)

    return work.point(lambda v: 255 if v == 128 else 0)


def add_hard_alpha(
    img: Image.Image, threshold: int, keep_inner_white: bool
) -> Image.Image:
    """Make the background transparent and every visible pixel opaque."""
    img = img.convert("RGBA")
    bg = background_mask(img, threshold, keep_inner_white)

    # Visible = not background and not already transparent in the source.
    src_alpha = img.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    alpha = ImageChops.multiply(ImageChops.invert(bg), src_alpha)

    r, g, b, _ = img.split()
    white = Image.new("L", img.size, 255)
    # Transparent pixels get a white RGB value, as required for a clean ICO.
    r = Image.composite(r, white, alpha)
    g = Image.composite(g, white, alpha)
    b = Image.composite(b, white, alpha)
    return Image.merge("RGBA", (r, g, b, alpha))


def resize_premultiplied(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize with LANCZOS without pulling white into the edges.

    1. Multiply RGB by alpha (premultiplied alpha).
    2. Resize RGBA with LANCZOS.
    3. Un-premultiply the color.
    4. Force alpha to exactly 0 or 255.
    """
    r, g, b, a = img.split()
    prem = Image.merge(
        "RGBA",
        (
            ImageChops.multiply(r, a),
            ImageChops.multiply(g, a),
            ImageChops.multiply(b, a),
            a,
        ),
    )
    prem = prem.resize(size, Image.Resampling.LANCZOS)
    pr, pg, pb, pa = prem.split()

    # color = premultiplied_color * 255 / alpha
    inv_lut = [0] + [min(255, round(255 * 255 / v)) for v in range(1, 256)]
    inv = pa.point(inv_lut)

    r = ImageChops.multiply(pr, inv)
    g = ImageChops.multiply(pg, inv)
    b = ImageChops.multiply(pb, inv)

    # No semi-transparent pixels: this is what makes icons look pale in Windows.
    pa = pa.point(lambda v: 255 if v >= 128 else 0)

    white = Image.new("L", size, 255)
    r = Image.composite(r, white, pa)
    g = Image.composite(g, white, pa)
    b = Image.composite(b, white, pa)
    return Image.merge("RGBA", (r, g, b, pa))


def validate_ico(path: Path) -> None:
    """Check the structure that Windows actually sees inside the file."""
    with open(path, "rb") as fh:
        header = fh.read(22)
        if len(header) < 22:
            raise RuntimeError(f"{path.name}: file is too short")

        count = struct.unpack_from("<H", header, 4)[0]
        if count != 1:
            raise RuntimeError(f"{path.name}: {count} layers, expected exactly 1")

        bit_count = struct.unpack_from("<H", header, 12)[0]
        if bit_count != 32:
            raise RuntimeError(f"{path.name}: {bit_count}-bit layer, expected 32-bit")

        data_offset = struct.unpack_from("<I", header, 18)[0]
        fh.seek(data_offset)
        signature = fh.read(4)

    if signature != b"\x28\x00\x00\x00":
        raise RuntimeError(f"{path.name}: layer is not BMP-encoded")

    with Image.open(path) as ico:
        sizes = set(ico.ico.sizes())
        if sizes != set(ICO_SIZES):
            raise RuntimeError(f"{path.name}: expected layer 256x256, got {sizes}")

        rgba = ico.convert("RGBA")
        if rgba.size != TARGET_SIZE:
            raise RuntimeError(f"{path.name}: size is {rgba.size}, not 256x256")

        hist = rgba.getchannel("A").histogram()
        partial = sum(hist[1:255])
        if partial:
            raise RuntimeError(
                f"{path.name}: {partial} semi-transparent pixels remain"
            )


def convert(
    src: Path,
    dst: Path,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    keep_inner_white: bool = True,
) -> None:
    """Convert one image to a 256x256 ICO and validate the result."""
    if not 0 <= threshold <= 255:
        raise ValueError("threshold must be between 0 and 255")

    with Image.open(src) as opened:
        img = ImageOps.exif_transpose(opened).convert("RGBA")

    img = add_hard_alpha(img, threshold, keep_inner_white)
    img = resize_premultiplied(img, TARGET_SIZE)

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format="ICO", sizes=ICO_SIZES, bitmap_format="bmp")
    validate_ico(dst)


def iter_sources(folder: Path) -> list[Path]:
    """Return supported files directly inside *folder*, sorted by name."""
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in INPUT_EXTS
        ),
        key=lambda path: path.name.lower(),
    )


def threshold_arg(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 255") from exc
    if not 0 <= number <= 255:
        raise argparse.ArgumentTypeError("must be between 0 and 255")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_ico.py",
        description=(
            "Convert PNG/JPG/JPEG to one-layer 256x256 ICO files with a "
            "transparent white background, tuned for Windows Explorer and "
            "USB autorun.inf icons."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        metavar="DIR",
        help="folder with PNG/JPG/JPEG files (default: the real Downloads folder)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help="output folder (default: <input>/new)",
    )
    parser.add_argument(
        "--threshold",
        type=threshold_arg,
        default=DEFAULT_THRESHOLD,
        metavar="0-255",
        help=(
            "a pixel is considered white when R, G and B are all above this "
            "value (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--remove-all-white",
        action="store_true",
        help=(
            "remove every near-white pixel, including white details inside "
            "the drawing (default: keep enclosed white details)"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    input_dir = (args.input or get_downloads_dir()).expanduser()
    if not input_dir.is_dir():
        print(f"Input folder not found: {input_dir}", file=sys.stderr)
        return 1

    output_dir = (args.output or (input_dir / "new")).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = iter_sources(input_dir)
    if not files:
        print(f"No PNG/JPG/JPEG files in {input_dir}")
        return 0

    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")
    print()

    ok = 0
    failed = 0

    for src in files:
        dst = output_dir / f"{src.stem}.ico"
        try:
            convert(
                src,
                dst,
                threshold=args.threshold,
                keep_inner_white=not args.remove_all_white,
            )
        except Exception as exc:
            failed += 1
            print(f"ERROR: {src.name}: {exc}", file=sys.stderr)
            continue

        ok += 1
        print(f"Done: {dst.name}")

    print()
    print(f"Converted: {ok}; failed: {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
