#!/usr/bin/env python3
"""Build the current Pot & Parry rules as a one-page A4 PDF.

This script uses only the Python standard library. Run it after editing
rules_new.md; optional source and output paths may be passed on the command line.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN_X = 30.0
GUTTER = 18.0
COLUMN_WIDTH = (PAGE_WIDTH - 2 * MARGIN_X - GUTTER) / 2
BODY_TOP = 773.0
BODY_BOTTOM = 31.0


@dataclass(frozen=True)
class Block:
    kind: str
    text: str


def plain_markdown(text: str) -> str:
    """Remove the small subset of inline Markdown used by the rules."""
    text = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_markdown(path: Path) -> tuple[str, list[Block]]:
    title = "Pot & Parry"
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(Block("paragraph", plain_markdown(" ".join(paragraph))))
            paragraph.clear()

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
        elif line.startswith("# "):
            flush_paragraph()
            title = plain_markdown(line[2:])
        elif line.startswith("## "):
            flush_paragraph()
            blocks.append(Block("heading", plain_markdown(line[3:])))
        elif line.startswith("### "):
            flush_paragraph()
            blocks.append(Block("subheading", plain_markdown(line[4:])))
        elif re.match(r"^[-*]\s+", line):
            flush_paragraph()
            blocks.append(Block("bullet", plain_markdown(line[2:])))
        else:
            paragraph.append(line)

    flush_paragraph()
    return title, blocks


def text_width(text: str, size: float, bold: bool = False) -> float:
    """Approximate Helvetica metrics closely enough for conservative wrapping."""
    narrow = "fijltI.,:;!'|()[]"
    wide = "mwMW@%&Q"
    total = 0.0
    for char in text:
        if char == " ":
            units = 0.278
        elif char in narrow:
            units = 0.265
        elif char in wide:
            units = 0.79
        elif char.isupper():
            units = 0.65
        elif char.isdigit():
            units = 0.556
        else:
            units = 0.50
        total += units
    return total * size * (1.035 if bold else 1.0)


def wrap_text(text: str, width: float, size: float, bold: bool = False) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    line = words[0]
    for word in words[1:]:
        candidate = f"{line} {word}"
        if text_width(candidate, size, bold) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))


def draw_text(
    commands: list[str],
    text: str,
    x: float,
    y: float,
    size: float,
    *,
    bold: bool = False,
    color: str = "#17231f",
) -> None:
    r, g, b = rgb(color)
    font = "F2" if bold else "F1"
    commands.append(
        f"BT /{font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg "
        f"1 0 0 1 {x:.2f} {y:.2f} Tm ({pdf_escape(text)}) Tj ET"
    )


def block_metrics(block: Block, body_size: float) -> tuple[list[str], float, float, bool]:
    """Return wrapped lines, total height, leading, and bold state."""
    if block.kind == "heading":
        size = body_size + 2.3
        leading = size + 1.8
        lines = wrap_text(block.text.upper(), COLUMN_WIDTH, size, True)
        return lines, 5.5 + len(lines) * leading + 2.0, leading, True
    if block.kind == "subheading":
        size = body_size + 1.0
        leading = size + 1.5
        lines = wrap_text(block.text, COLUMN_WIDTH, size, True)
        return lines, 3.5 + len(lines) * leading + 1.5, leading, True
    if block.kind == "bullet":
        leading = body_size + 1.85
        lines = wrap_text(block.text, COLUMN_WIDTH - 12.0, body_size)
        return lines, len(lines) * leading + 1.2, leading, False

    leading = body_size + 1.85
    lines = wrap_text(block.text, COLUMN_WIDTH, body_size)
    return lines, len(lines) * leading + 3.0, leading, False


def layout(blocks: list[Block], body_size: float) -> tuple[list[str], int] | None:
    metrics = [block_metrics(block, body_size) for block in blocks]
    heights = [item[1] for item in metrics]
    available = BODY_TOP - BODY_BOTTOM

    # Choose a balanced split and strongly prefer beginning column two at a
    # section boundary. This also prevents headings and bullet lists splitting.
    candidates: list[tuple[float, int]] = []
    for split in range(1, len(blocks)):
        left_height = sum(heights[:split])
        right_height = sum(heights[split:])
        if left_height > available or right_height > available:
            continue
        if blocks[split - 1].kind in {"heading", "subheading"}:
            continue

        boundary_penalty = 0.0 if blocks[split].kind == "heading" else 28.0
        if blocks[split - 1].kind == "bullet" and blocks[split].kind == "bullet":
            boundary_penalty += 45.0
        candidates.append((abs(left_height - right_height) + boundary_penalty, split))

    if not candidates:
        return None

    _, split = min(candidates)
    commands: list[str] = []

    for column, (start, stop) in enumerate(((0, split), (split, len(blocks)))):
        y = BODY_TOP
        x = MARGIN_X + column * (COLUMN_WIDTH + GUTTER)

        for index in range(start, stop):
            block = blocks[index]
            lines, _, leading, bold = metrics[index]

            if block.kind == "heading":
                y -= 5.5
                accent_r, accent_g, accent_b = rgb("#2d7666")
                commands.append(
                    f"{accent_r:.3f} {accent_g:.3f} {accent_b:.3f} rg "
                    f"{x:.2f} {y - 1.8:.2f} 19 1.6 re f"
                )
                size = body_size + 2.3
                for line in lines:
                    y -= leading
                    draw_text(commands, line, x + 24, y + 1.8, size, bold=True, color="#17473d")
                y -= 2.0
            elif block.kind == "subheading":
                y -= 3.5
                size = body_size + 1.0
                for line in lines:
                    y -= leading
                    draw_text(commands, line, x, y + 1.5, size, bold=bold, color="#245f53")
                y -= 1.5
            elif block.kind == "bullet":
                for line_index, line in enumerate(lines):
                    y -= leading
                    if line_index == 0:
                        draw_text(commands, "•", x + 1, y + 1.45, body_size, bold=True, color="#2d7666")
                    draw_text(commands, line, x + 11, y + 1.45, body_size)
                y -= 1.2
            else:
                for line in lines:
                    y -= leading
                    draw_text(commands, line, x, y + 1.45, body_size)
                y -= 3.0

    return commands, 2


def build_content(title: str, blocks: list[Block]) -> tuple[bytes, float]:
    body_size = 8.35
    laid_out: tuple[list[str], int] | None = None
    while body_size >= 6.8:
        laid_out = layout(blocks, body_size)
        if laid_out is not None:
            break
        body_size = round(body_size - 0.15, 2)

    if laid_out is None:
        raise SystemExit(
            "The rules no longer fit legibly on one page. Shorten rules_new.md "
            "or revise the layout before rebuilding."
        )

    body_commands, _ = laid_out
    commands: list[str] = []

    # White page and a compact green title band.
    commands.append("1 1 1 rg 0 0 595.28 841.89 re f")
    header_r, header_g, header_b = rgb("#143e36")
    commands.append(f"{header_r:.3f} {header_g:.3f} {header_b:.3f} rg 0 790 595.28 51.89 re f")
    draw_text(commands, title.upper(), MARGIN_X, 812.5, 21.0, bold=True, color="#ffffff")
    draw_text(
        commands,
        "ONE-PAGE RULES  •  FOR SNOOKER PLAYERS",
        MARGIN_X,
        798.5,
        7.4,
        bold=True,
        color="#cfe5dd",
    )

    # Column divider and body.
    divider_x = PAGE_WIDTH / 2
    line_r, line_g, line_b = rgb("#d7e2dd")
    commands.append(
        f"{line_r:.3f} {line_g:.3f} {line_b:.3f} RG 0.55 w "
        f"{divider_x:.2f} {BODY_BOTTOM:.2f} m {divider_x:.2f} {BODY_TOP + 2:.2f} l S"
    )
    commands.extend(body_commands)

    draw_text(commands, "POT & PARRY  •  QUICK REFERENCE", MARGIN_X, 16, 6.8, bold=True, color="#597068")
    footer = "Generated from rules_new.md  •  1 / 1"
    footer_x = PAGE_WIDTH - MARGIN_X - text_width(footer, 6.8)
    draw_text(commands, footer, footer_x, 16, 6.8, color="#597068")

    return ("\n".join(commands) + "\n").encode("cp1252", errors="replace"), body_size


def write_pdf(path: Path, content: bytes, title: str) -> None:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
            b"/Resources << /ProcSet [/PDF /Text] /Font << /F1 5 0 R /F2 6 0 R >> >> "
            b"/Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        (
            f"<< /Title ({pdf_escape(title + ' — One-Page Rules')}) "
            f"/Creator (build_rules_pdf.py) >>"
        ).encode("cp1252", errors="replace"),
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f\r\n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n\r\n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 7 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(pdf)


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=project_dir / "rules_new.md")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=project_dir / "pot-and-parry-rules.pdf",
    )
    args = parser.parse_args()

    title, blocks = parse_markdown(args.source)
    content, body_size = build_content(title, blocks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_pdf(args.output, content, title)
    print(f"Wrote {args.output} (1 A4 page, {body_size:.2f} pt body text)")


if __name__ == "__main__":
    main()
