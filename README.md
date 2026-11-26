# png-to-ico-windows

![tests](https://github.com/Double-Coyc/png-to-ico-windows/actions/workflows/tests.yml/badge.svg)

Batch-convert PNG/JPG/JPEG images to **256×256 ICO** files with a hard transparent white background. Tuned for the cases where Windows Explorer or a USB `autorun.inf` icon still shows a white square or a pale, semi-transparent image.

## Why this exists

Converting an image to an ICO is easy. Making Windows display it correctly is not. Three things usually go wrong:

1. **Soft or white-contaminated edges.** White-background removal creates semi-transparent pixels; Windows renders them as a white fringe or makes the whole icon look washed out.
2. **Multiple icon layers.** An ICO may contain 16×16, 32×32, 48×48 and 256×256 layers. Windows can pick a small layer produced by a poor resize and show its artifacts.
3. **The icon cache.** Windows aggressively caches icons, so even a fixed file can keep displaying the old version until it is renamed or the cache is reset.

This tool addresses the first two points and documents the third.

## What it does

- Writes exactly **one 256×256 layer** (`sizes=[(256, 256)]`).
- Stores that layer as **BMP inside the ICO** (`bitmap_format="bmp"`), not as PNG. Modern Explorer usually reads PNG-compressed layers, but some legacy shell code paths used for `autorun.inf` do not. BMP is the compatible choice; the trade-off is a larger file (about 256 KB per icon).
- Forces alpha to **0 or 255** after resizing. No semi-transparent pixels, so icons do not look pale.
- Resizes with **LANCZOS using premultiplied alpha**. Edge pixels keep the object's color instead of being blended with white, so there is no white halo.
- Removes white **only where it is connected to the image border**. White details inside the drawing (for example slots on a server icon) stay opaque. Use `--remove-all-white` to remove every near-white pixel.
- Reopens every saved ICO and validates the layer count, size, BMP encoding and alpha values.

## Requirements

- Python 3.9+
- Pillow 10+
- Windows for the default Downloads-folder detection. On other systems, pass `--input` explicitly.

## Install

```bash
git clone https://github.com/Double-Coyc/png-to-ico-windows.git
cd png-to-ico-windows
python -m pip install -r requirements.txt
```

## Usage

```bash
python make_ico.py
```

By default the script reads the **real** Downloads folder and writes to `Downloads/new`. On Windows the Downloads path is read from the registry, so relocated folders (for example `D:\Users\name\Downloads`) work correctly.

Convert a specific folder:

```bash
python make_ico.py --input ./source --output ./icons
```

Remove every near-white pixel, including white details inside the drawing:

```bash
python make_ico.py --remove-all-white
```

### Options

| Option | Default | Description |
| --- | --- | --- |
| `--input DIR` | real Downloads folder | Folder with PNG/JPG/JPEG files (non-recursive). |
| `--output DIR` | `<input>/new` | Output folder; created if missing. |
| `--threshold 0-255` | `235` | A pixel is white when R, G and B are all above this value. |
| `--remove-all-white` | off | Remove all near-white pixels instead of only the border-connected background. |
| `--version` | | Print the version. |

Output names keep the source base name: `photo.jpg` → `photo.ico`.

## Example

```text
Input:  C:\Users\name\Downloads
Output: C:\Users\name\Downloads\new

Done: images.ico
Done: server.ico

Converted: 2; failed: 0
```

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests create a synthetic image with a white background, a colored frame and an enclosed white hole, then check that:

- the ICO contains exactly one 256×256 layer;
- the background is transparent;
- the enclosed white hole stays opaque by default;
- `--remove-all-white` makes it transparent;
- the CLI writes the expected output file.

CI runs the suite on Windows and Linux with Python 3.10 and 3.12.

## Using the icons on a USB drive

1. Copy the new `.ico` files to the USB drive.
2. Rename them on the drive (for example add `_v2`), so Windows does not reuse the cached old file.
3. Update `autorun.inf`, for example:

   ```ini
   [autorun]
   icon=images_v2.ico
   label=My USB
   ```

4. Reset the icon cache: `Win+R` → `cmd` → `ie4uinit.exe -ClearIconCache`.
5. Restart Explorer: Task Manager → “Windows Explorer” → “Restart”.
6. Safely eject the drive and plug it back in.

## License

MIT. See [LICENSE](LICENSE).

Русская версия: [README.ru.md](README.ru.md).
