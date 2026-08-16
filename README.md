# Instagram 3-panel splitter

Turn one wide 3-panel video into an Instagram carousel: **2 photos + 1 video**.

Designed for exports that are three 1080×1350 slides sitting side by side (about **3240×1350**). The first two panels become stills; the last panel stays a cropped video.

```
|  1080 × 1350  |  1080 × 1350  |  1080 × 1350  |
|  slide_01.png |  slide_02.png |  slide_03.mp4 |
|  first frame  |  first frame  |  full video   |
```

## Output

| File | What it is |
| --- | --- |
| `slide_01.png` | Left panel, first frame |
| `slide_02.png` | Middle panel, first frame |
| `slide_03.mp4` | Right panel, cropped video (H.264, audio kept if present) |

If the source is taller than 1350, height is center-cropped. If it is shorter, it is scaled up to 1350 (width scales with it). Extra width past 3240 is ignored (leftmost three panels). Anything narrower than 3240 after that is rejected.

PNGs keep the video’s limited-range levels so dark charcoal backgrounds don’t crush to black, and they are tagged sRGB for Instagram stills. The MP4 stays Rec.709 limited-range.

## Requirements

- Python 3.8+ (tkinter is used for the GUI; it ships with most desktop Pythons)
- [ffmpeg](https://ffmpeg.org/) and `ffprobe` on your PATH

```bash
brew install ffmpeg
```

No Python packages are required to run the tool.

## Usage

### GUI

```bash
python split_instagram.py
```

Pick an input video, pick an output folder, then **Split**. If you skip the output folder, files go to `output/` next to the video.

### Command line

```bash
python split_instagram.py input.mp4
python split_instagram.py input.mp4 -o ./out
```

## macOS app

To wrap the GUI into **Instagram Splitter.app** (ffmpeg is downloaded and bundled):

```bash
chmod +x build_app.sh
./build_app.sh
```

The app lands in `dist/Instagram Splitter.app`. First launch may need right-click → **Open**.

`build/`, `dist/`, and `bin/` are not in git; they are produced locally.

## License

MIT
