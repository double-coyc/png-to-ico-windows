from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import make_ico  # noqa: E402


def make_donut(path: Path) -> None:
    """White canvas, colored square, enclosed white hole."""
    image = Image.new("RGBA", (128, 128), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, 103, 103), fill=(30, 90, 140, 255))
    draw.rectangle((48, 48, 79, 79), fill=(255, 255, 255, 255))
    image.save(path)


class MakeIcoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _convert(self, *, name: str = "donut.png", **kwargs) -> Path:
        src = self.root / name
        dst = self.root / f"{Path(name).stem}.ico"
        make_donut(src)
        make_ico.convert(src, dst, **kwargs)
        return dst

    def test_ico_layout_and_alpha(self) -> None:
        dst = self._convert()

        # idCount == 1
        self.assertEqual(dst.read_bytes()[4:6], b"\x01\x00")

        with Image.open(dst) as image:
            self.assertEqual(image.ico.sizes(), {(256, 256)})
            rgba = image.convert("RGBA")

        hist = rgba.getchannel("A").histogram()
        self.assertEqual(sum(hist[1:255]), 0, "semi-transparent pixels found")

        self.assertEqual(rgba.getpixel((0, 0))[3], 0, "background is not transparent")
        self.assertEqual(rgba.getpixel((128, 128))[3], 255, "inner white was removed")
        self.assertEqual(rgba.getpixel((64, 128))[3], 255, "colored frame was removed")

    def test_remove_all_white(self) -> None:
        dst = self._convert(keep_inner_white=False)

        with Image.open(dst) as image:
            rgba = image.convert("RGBA")

        self.assertEqual(rgba.getpixel((0, 0))[3], 0)
        self.assertEqual(rgba.getpixel((128, 128))[3], 0)
        self.assertEqual(rgba.getpixel((64, 128))[3], 255)

    def test_cli(self) -> None:
        in_dir = self.root / "in"
        out_dir = self.root / "out"
        in_dir.mkdir()
        make_donut(in_dir / "donut.png")

        rc = make_ico.main(
            ["--input", str(in_dir), "--output", str(out_dir)]
        )

        self.assertEqual(rc, 0)
        self.assertTrue((out_dir / "donut.ico").is_file())


if __name__ == "__main__":
    unittest.main()
