"""Run and render the reproducible polyglot tour as a small walkthrough GIF.

The GIF is deliberately a source-and-output walkthrough. It is not a screen
recording, and it does not claim a runtime or speed result.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1280, 720
BACKGROUND = "#101827"
PANEL = "#182337"
PANEL_DARK = "#131d2d"
TEXT = "#ecf3ff"
MUTED = "#9cadc5"
ACCENT = "#72e0c2"
ORANGE = "#f6b86b"
BLUE = "#89b4ff"


def _font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cour.ttf"]
        if mono
        else [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]
    )
    candidates += ["DejaVuSansMono.ttf" if mono else "DejaVuSans.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _parse_blocks(source: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    marker: str | None = None
    body: list[str] = []
    for line in source.splitlines():
        if line.startswith("@"):
            if marker is not None:
                blocks.append((marker, body))
            marker, body = line, []
        elif marker is not None:
            body.append(line)
    if marker is not None:
        blocks.append((marker, body))
    return blocks


def _run_and_capture(root: Path, source_path: Path) -> str:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    # Rust is installed locally on the demo machine. Only this child process
    # receives the extra PATH entry; the user's shell is left untouched.
    rust_bin = Path.home() / ".cargo" / "bin"
    if rust_bin.is_dir():
        env["PATH"] = str(rust_bin) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "conflate.cli", "--run-source", str(source_path)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        raise RuntimeError(f"tour execution failed with exit code {result.returncode}:\n{details}")
    output = result.stdout.strip()
    expected = "Python -> C++ -> Rust -> Java -> Go -> Python: 40, 42, 43, 44, 45"
    if output != expected:
        raise RuntimeError(f"tour output did not match the checked result:\n{output}")
    return output


def _rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, radius: int = 16) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, font: ImageFont.ImageFont, fill: str = TEXT) -> None:
    draw.text(xy, value, font=font, fill=fill)


def _base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 8), fill=ACCENT)
    _text(draw, (58, 34), "CONFLATE", _font(24), ACCENT)
    _text(draw, (220, 37), "POLYGLOT TOUR", _font(18), MUTED)
    badge = "WALKTHROUGH  •  NOT A SCREEN RECORDING"
    badge_font = _font(16)
    badge_width = draw.textbbox((0, 0), badge, font=badge_font)[2]
    draw.rounded_rectangle((WIDTH - badge_width - 86, 29, WIDTH - 58, 62), radius=14, fill="#20344a")
    _text(draw, (WIDTH - badge_width - 72, 37), badge, badge_font, BLUE)
    return image, draw


def _title_frame() -> Image.Image:
    image, draw = _base()
    _text(draw, (72, 142), "One typed value,", _font(58))
    _text(draw, (72, 211), "six language blocks.", _font(58), ACCENT)
    _text(draw, (76, 317), "Python  →  C++  →  Rust  →  Java  →  Go  →  Python", _font(25), ORANGE)
    _text(draw, (76, 382), "A concise source walkthrough generated after a real local run.", _font(22), MUTED)
    _rounded(draw, (76, 500, 532, 584), PANEL)
    _text(draw, (102, 522), "typed boundaries", _font(22), TEXT)
    _text(draw, (102, 553), "seed:int → ... → go_value:int", _font(18), MUTED)
    _text(draw, (76, 654), "Source: examples/polyglot-tour.confl", _font(18), MUTED)
    return image


def _stage_frame(index: int, marker: str, body: list[str]) -> Image.Image:
    image, draw = _base()
    language = re.match(r"@([a-z]+)", marker, re.IGNORECASE)
    language_name = language.group(1).upper() if language else marker
    _text(draw, (72, 118), f"STEP {index} / 6", _font(18), ORANGE)
    _text(draw, (72, 156), f"The {language_name} block", _font(42))
    _text(draw, (72, 219), "The source below is read directly from the tour file.", _font(20), MUTED)
    _rounded(draw, (72, 286, 1208, 592), PANEL_DARK, 18)
    code_font = _font(27, mono=True)
    widest = max(draw.textlength(line, font=code_font) for line in [marker, *body])
    if widest > 1060:
        code_font = _font(max(14, int(27 * 1060 / widest)), mono=True)
    _text(draw, (108, 320), marker, code_font, ACCENT)
    y = 376
    for line in body:
        if not line.strip():
            y += 18
            continue
        _text(draw, (108, y), line, code_font, TEXT)
        y += 43
    _text(draw, (72, 648), "Explicit in/out contracts keep the handoff visible and checkable.", _font(18), MUTED)
    return image


def _output_frame(output: str) -> Image.Image:
    image, draw = _base()
    _text(draw, (72, 126), "Verified output", _font(48), ACCENT)
    _text(draw, (74, 204), "Captured from the executed tour command:", _font(22), MUTED)
    _rounded(draw, (72, 288, 1208, 442), PANEL_DARK, 18)
    _text(draw, (108, 346), output, _font(25, mono=True), TEXT)
    _text(draw, (74, 518), "Every number is checked by the final Python block.", _font(22), ORANGE)
    _text(draw, (74, 565), "Walkthrough only • no runtime or speed claim", _font(21), MUTED)
    return image


def render(source_path: Path, output_path: Path) -> None:
    root = source_path.parents[1]
    source = source_path.read_text(encoding="utf-8")
    output = _run_and_capture(root, source_path)
    blocks = _parse_blocks(source)
    if len(blocks) != 6:
        raise RuntimeError(f"expected six blocks, found {len(blocks)}")

    frames = [_title_frame()]
    frames.extend(_stage_frame(index, marker, body) for index, (marker, body) in enumerate(blocks, 1))
    frames.append(_output_frame(output))
    durations = [2400, *([2800] * len(blocks)), 3400]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"verified: {output}")
    print(f"wrote: {output_path} ({sum(durations) / 1000:.1f}s loop)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and render the Conflate polyglot tour walkthrough.")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=root / "examples" / "polyglot-tour.confl")
    parser.add_argument("--output", type=Path, default=root / "assets" / "polyglot-tour.gif")
    args = parser.parse_args()
    render(args.source.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
