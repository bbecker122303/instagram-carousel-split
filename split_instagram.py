#!/usr/bin/env python3
"""Split a wide 3-panel video into 2 Instagram PNGs and 1 cropped MP4."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

SLIDE_W = 1080
SLIDE_H = 1350
PANEL_COUNT = 3
MIN_WIDTH = SLIDE_W * PANEL_COUNT

# Keep Rec.709 limited-range tags attached after crop/scale. Filters often drop them.
SET_BT709_TV = (
    "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
)
# Keep limited-range codes (Y=16 black, ~39 charcoal). Expanding TV→full
# crushes that gray to ~26 and the PNG background looks black vs the MP4.
TO_RGB = (
    "scale=in_color_matrix=bt709:in_range=pc:out_color_matrix=bt709:out_range=pc,"
    "format=rgb24"
)


class SplitError(Exception):
    """User-facing failure from ffmpeg or invalid input."""


def _tool_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass))
        dirs.append(exe_dir / "_internal")
        contents = exe_dir.parent
        dirs.append(contents / "Frameworks")
        dirs.append(contents / "Resources")
    dirs.append(Path(__file__).resolve().parent / "bin")
    return dirs


def tool(name: str) -> str:
    for folder in _tool_search_dirs():
        candidate = folder / name
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise SplitError(
        f"{name} not found. Install ffmpeg (macOS: brew install ffmpeg) "
        f"or use the packaged .app."
    )


def require_tools() -> None:
    tool("ffmpeg")
    tool("ffprobe")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SplitError(f"Error running {' '.join(cmd[:3])}:\n{detail}")
    return result


def probe_size(path: Path) -> tuple[int, int]:
    result = run(
        [
            tool("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ]
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise SplitError(f"No video stream found in {path}")
    width = int(streams[0]["width"])
    height = int(streams[0]["height"])
    return width, height


def even_floor(value: float) -> int:
    return 2 * int(value // 2)


def preprocess_and_width(width: int, height: int) -> tuple[str | None, int]:
    """Return an optional scale/crop filter and the width after it is applied."""
    if height < SLIDE_H:
        new_width = even_floor(width * SLIDE_H / height)
        return (
            f"scale={new_width}:{SLIDE_H}:in_color_matrix=bt709:out_color_matrix=bt709:"
            f"in_range=tv:out_range=tv",
            new_width,
        )
    if height > SLIDE_H:
        y = (height - SLIDE_H) // 2
        return f"crop={width}:{SLIDE_H}:0:{y}", width
    return None, width


def vf_parts(preprocess: str | None, x: int) -> list[str]:
    parts: list[str] = []
    if preprocess:
        parts.append(preprocess)
    parts.append(f"crop={SLIDE_W}:{SLIDE_H}:{x}:0")
    parts.append(SET_BT709_TV)
    return parts


def png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def embed_srgb_profile(path: Path) -> None:
    """Tag the PNG as sRGB so Preview and Instagram treat it as a still, not Rec.709 video."""
    raw = path.read_bytes()
    sig = b"\x89PNG\r\n\x1a\n"
    if not raw.startswith(sig):
        return

    out = bytearray(sig)
    pos = 8
    inserted = False
    while pos < len(raw):
        length = int.from_bytes(raw[pos : pos + 4], "big")
        tag = raw[pos + 4 : pos + 8]
        chunk = raw[pos : pos + 12 + length]
        pos += 12 + length
        if tag in {b"sRGB", b"gAMA", b"cHRM", b"iCCP"}:
            continue
        out.extend(chunk)
        if tag == b"IHDR" and not inserted:
            # Perceptual sRGB + gamma 1/2.2 + Rec.709/sRGB primaries
            out.extend(png_chunk(b"sRGB", b"\x00"))
            out.extend(png_chunk(b"gAMA", struct.pack(">I", 45455)))
            out.extend(
                png_chunk(
                    b"cHRM",
                    struct.pack(
                        ">8I",
                        31270,
                        32900,
                        64000,
                        33000,
                        30000,
                        60000,
                        15000,
                        6000,
                    ),
                )
            )
            inserted = True
    path.write_bytes(bytes(out))


def export_png(src: Path, dest: Path, preprocess: str | None, x: int) -> None:
    print(f"Writing {dest.name}...")
    run(
        [
            tool("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            ",".join(vf_parts(preprocess, x) + [TO_RGB]),
            "-frames:v",
            "1",
            "-color_range",
            "pc",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            str(dest),
        ]
    )
    embed_srgb_profile(dest)


def export_mp4(src: Path, dest: Path, preprocess: str | None, x: int) -> None:
    print(f"Writing {dest.name}...")
    run(
        [
            tool("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            ",".join(vf_parts(preprocess, x)),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-x264-params",
            "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def split_video(src: Path, out_dir: Path, log=print) -> list[Path]:
    require_tools()
    src = src.expanduser().resolve()
    if not src.is_file():
        raise SplitError(f"Input file not found: {src}")

    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    width, height = probe_size(src)
    preprocess, ready_width = preprocess_and_width(width, height)
    if ready_width < MIN_WIDTH:
        raise SplitError(
            f"Video is {width}x{height}, which becomes {ready_width}x{SLIDE_H} "
            f"after fitting height. Need at least {MIN_WIDTH}px width for "
            f"{PANEL_COUNT} slides of {SLIDE_W}px."
        )

    outputs = [
        out_dir / "slide_01.png",
        out_dir / "slide_02.png",
        out_dir / "slide_03.mp4",
    ]
    log(f"Input: {src} ({width}x{height})")
    log(f"Output: {out_dir}")
    export_png(src, outputs[0], preprocess, 0)
    export_png(src, outputs[1], preprocess, SLIDE_W)
    export_mp4(src, outputs[2], preprocess, SLIDE_W * 2)
    log("Done:")
    for path in outputs:
        log(f"  {path}")
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split a wide 3-panel video into two 1080x1350 PNGs "
            "(first two slides) and one 1080x1350 MP4 (last slide). "
            "Run with no arguments to open the GUI."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Path to the source video (omit to open the GUI)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output directory (default: output/ next to the input file)",
    )
    parser.add_argument("--gui", action="store_true", help="Open the file-picker window")
    return parser.parse_args()


def launch_gui() -> None:
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Instagram 3-panel splitter")
    root.minsize(560, 220)
    root.geometry("640x240")

    input_var = tk.StringVar()
    output_var = tk.StringVar()
    status_var = tk.StringVar(value="Select a video and an output folder.")

    def pick_input() -> None:
        path = filedialog.askopenfilename(
            title="Select video",
            filetypes=[
                ("Video", "*.mp4 *.mov *.m4v *.mkv *.webm *.avi"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        input_var.set(path)
        if not output_var.get().strip():
            output_var.set(str(Path(path).parent / "output"))

    def pick_output() -> None:
        start = output_var.get().strip() or input_var.get().strip()
        initial = str(Path(start).expanduser()) if start else None
        path = filedialog.askdirectory(title="Select output folder", initialdir=initial)
        if path:
            output_var.set(path)

    def set_status(text: str) -> None:
        root.after(0, status_var.set, text)

    def finish(ok: bool, message: str) -> None:
        def _done() -> None:
            status_var.set(message)
            split_btn.configure(state=tk.NORMAL)
            if ok:
                messagebox.showinfo("Done", message)
            else:
                messagebox.showerror("Split failed", message)

        root.after(0, _done)

    def start_split() -> None:
        src = input_var.get().strip()
        dest = output_var.get().strip()
        if not src:
            messagebox.showwarning("Missing input", "Choose a video file first.")
            return
        if not dest:
            dest = str(Path(src).parent / "output")
            output_var.set(dest)
        split_btn.configure(state=tk.DISABLED)
        status_var.set("Working… this can take a minute for the MP4.")

        def worker() -> None:
            try:
                outputs = split_video(Path(src), Path(dest), log=set_status)
                names = "\n".join(p.name for p in outputs)
                finish(True, f"Saved to:\n{outputs[0].parent}\n\n{names}")
            except SplitError as exc:
                finish(False, str(exc))
            except Exception as exc:  # noqa: BLE001
                finish(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    pad = {"padx": 12, "pady": 6}
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text="Input video").grid(row=0, column=0, sticky=tk.W, **pad)
    ttk.Entry(frame, textvariable=input_var).grid(row=0, column=1, sticky=tk.EW, **pad)
    ttk.Button(frame, text="Browse…", command=pick_input).grid(row=0, column=2, **pad)

    ttk.Label(frame, text="Output folder").grid(row=1, column=0, sticky=tk.W, **pad)
    ttk.Entry(frame, textvariable=output_var).grid(row=1, column=1, sticky=tk.EW, **pad)
    ttk.Button(frame, text="Browse…", command=pick_output).grid(row=1, column=2, **pad)

    split_btn = ttk.Button(frame, text="Split", command=start_split)
    split_btn.grid(row=2, column=1, sticky=tk.E, **pad)

    ttk.Label(frame, textvariable=status_var, wraplength=580).grid(
        row=3, column=0, columnspan=3, sticky=tk.W, **pad
    )

    root.mainloop()


def main() -> None:
    # Finder passes -psn_XXXX when launching a .app
    sys.argv = [a for a in sys.argv if not a.startswith("-psn_")]
    args = parse_args()
    if args.gui or args.input is None or getattr(sys, "frozen", False):
        launch_gui()
        return

    try:
        out_dir = args.output if args.output else args.input.expanduser().resolve().parent / "output"
        split_video(args.input, out_dir)
    except SplitError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
