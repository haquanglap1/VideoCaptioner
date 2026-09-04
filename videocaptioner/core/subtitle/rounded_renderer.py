"""Rounded background subtitle renderer"""

import os
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from PIL import Image, ImageDraw

from videocaptioner.core.entities import SubtitleLayoutEnum
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.subprocess_helper import child_environment

from .font_utils import FontType, get_font
from .styles import RoundedBgStyle
from .text_utils import hex_to_rgba, wrap_text

if TYPE_CHECKING:
    from videocaptioner.core.asr.asr_data import ASRData

logger = setup_logger("subtitle.rounded")


def _get_video_info(video_path: str) -> Tuple[int, int, float]:
    """Video resolution and duration."""
    result = subprocess.run(
        ["ffmpeg", "-i", video_path], env=child_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
    )

    # Parse resolution
    width, height = 0, 0
    if match := re.search(r"Stream.*Video:.* (\d{2,5})x(\d{2,5})", result.stderr):
        width, height = int(match.group(1)), int(match.group(2))
    else:
        raise ValueError(f"Cannot get video resolution: {video_path}")

    # Parse duration
    duration = 0.0
    if match := re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr):
        h, m, s = match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    return width, height, duration


def render_text_block(
    draw: ImageDraw.ImageDraw,
    texts: List[str],
    font: FontType,
    center_x: int,
    top_y: float,
    style: RoundedBgStyle,
) -> float:
    """
    Render a multi-line text block over one shared rounded background.

    Args:
        draw: PIL ImageDraw object
        texts: text lines
        font: font object
        center_x: horizontal centre
        top_y: top y coordinate
        style: style configuration

    Returns:
        Height of the background box
    """
    if not texts:
        return 0

    bg_color = hex_to_rgba(style.bg_color)
    text_color = hex_to_rgba(style.text_color)

    # Measure every line and its vertical offset
    line_sizes = []
    line_offsets = []
    for text in texts:
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        # Letter spacing adds extra width
        if style.letter_spacing > 0 and len(text) > 1:
            text_width += style.letter_spacing * (len(text) - 1)
        line_sizes.append((text_width, bbox[3] - bbox[1]))
        line_offsets.append(bbox[1])  # Keep the vertical offset for centring

    max_width = max(w for w, _ in line_sizes)
    line_height = max(h for _, h in line_sizes)
    total_height = line_height * len(texts) + style.line_spacing * (len(texts) - 1)

    # Draw the shared background
    bg_width = max_width + style.padding_h * 2
    bg_height = total_height + style.padding_v * 2
    bg_left = center_x - bg_width // 2
    bg_top = top_y

    draw.rounded_rectangle(
        [bg_left, bg_top, bg_left + bg_width, bg_top + bg_height],
        radius=style.corner_radius,
        fill=bg_color,
    )

    # Draw text, compensating the font's vertical offset
    y = bg_top + style.padding_v
    for i, text in enumerate(texts):
        w, _ = line_sizes[i]
        x = center_x - w // 2
        y_offset = line_offsets[i]
        text_y = y - y_offset  # Compensate the vertical offset so text looks centred

        # With letter spacing, draw character by character
        if style.letter_spacing > 0 and len(text) > 1:
            current_x = x
            for char in text:
                draw.text((current_x, text_y), char, font=font, fill=text_color)
                char_width = font.getbbox(char)[2] - font.getbbox(char)[0]
                current_x += char_width + style.letter_spacing
        else:
            # No letter spacing: draw in one call (faster)
            draw.text((x, text_y), text, font=font, fill=text_color)

        y += line_height + style.line_spacing

    return bg_height


def render_subtitle_image(
    primary_text: str,
    secondary_text: str,
    width: int,
    height: int,
    style: RoundedBgStyle,
) -> Image.Image:
    """
    Render one subtitle frame on a transparent background.

    Args:
        primary_text: primary subtitle text
        secondary_text: secondary subtitle text
        width: image width
        height: image height
        style: style configuration

    Returns:
        PIL Image in RGBA
    """
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = get_font(style.font_size, style.font_name)

    # Wrap lines (extra 40px margin keeps text off the edge)
    extra_margin = int(width * 0.1)
    primary_lines = (
        wrap_text(primary_text, font, width, style.padding_h, extra_margin=extra_margin)
        if primary_text
        else []
    )
    secondary_lines = (
        wrap_text(secondary_text, font, width, style.padding_h, extra_margin=extra_margin)
        if secondary_text
        else []
    )

    center_x = width // 2

    # Total height
    def calc_block_height(lines: List[str]) -> float:
        if not lines:
            return 0
        bbox = font.getbbox("测试Ag")
        line_h = bbox[3] - bbox[1]
        return line_h * len(lines) + style.line_spacing * (len(lines) - 1) + style.padding_v * 2

    primary_height = calc_block_height(primary_lines)
    secondary_height = calc_block_height(secondary_lines)
    gap = style.line_spacing if primary_lines and secondary_lines else 0
    total_height = primary_height + gap + secondary_height

    # Start position measured from the bottom
    bottom_y = height - style.margin_bottom
    start_y = bottom_y - total_height

    # Render the text blocks
    current_y = start_y
    if primary_lines:
        h = render_text_block(draw, primary_lines, font, center_x, current_y, style)
        current_y += h + gap
    if secondary_lines:
        render_text_block(draw, secondary_lines, font, center_x, current_y, style)

    return image


def render_preview(
    primary_text: str,
    secondary_text: str = "",
    width: Optional[int] = None,
    height: Optional[int] = None,
    style: Optional[RoundedBgStyle] = None,
    bg_image_path: Optional[str] = None,
    reference_height: int = 720,
) -> str:
    """
    Render a rounded-background subtitle preview image.

    Args:
        primary_text: primary subtitle text
        secondary_text: secondary subtitle text
        width: image width (None = read from bg_image_path)
        height: image height (None = read from bg_image_path)
        style: rounded-background style (720p reference, scaled to height)
        bg_image_path: background image path
        reference_height: reference height (fixed 720p)
    Returns:
        Path of the generated preview image
    """
    if style is None:
        style = RoundedBgStyle()

    # Load or create the background
    if bg_image_path and Path(bg_image_path).exists():
        background = Image.open(bg_image_path).convert("RGB")
        # Take the size from the image when not given
        if width is None or height is None:
            width, height = background.size
    else:
        # No background image: use the given or default size
        if width is None:
            width = 1920
        if height is None:
            height = 1080
        background = Image.new("RGB", (width, height), (20, 20, 20))

    # Narrow width/height away from None for the type checker
    assert width is not None and height is not None

    # Scale the style from its reference height to the image height
    scale_factor = height / reference_height

    if scale_factor != 1.0:
        style = replace(
            style,
            font_size=int(style.font_size * scale_factor),
            corner_radius=int(style.corner_radius * scale_factor),
            padding_h=int(style.padding_h * scale_factor),
            padding_v=int(style.padding_v * scale_factor),
            margin_bottom=int(style.margin_bottom * scale_factor),
            line_spacing=int(style.line_spacing * scale_factor),
            letter_spacing=int(style.letter_spacing * scale_factor),
        )

    # Render the subtitle and composite it
    subtitle_img = render_subtitle_image(primary_text, secondary_text, width, height, style)
    background.paste(subtitle_img, (0, 0), subtitle_img)

    # Save into the temp directory
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as tmp_file:
        background.save(tmp_file, "PNG")
        return tmp_file.name


def render_rounded_video(
    video_path: str,
    asr_data: "ASRData",
    output_path: str,
    rounded_style: Optional[dict] = None,
    layout: SubtitleLayoutEnum = SubtitleLayoutEnum.ONLY_ORIGINAL,
    crf: int = 23,
    preset: str = "medium",
    progress_callback: Optional[Callable] = None,
    reference_height: int = 720,
) -> None:
    """
    Render rounded-background subtitles into a video (batched overlay).

    Core flow: overlay subtitle PNGs directly onto the source video in
    batches of 50 to stay under FFmpeg's input-file limit.

    Args:
        video_path: input video path
        asr_data: subtitle data
        output_path: output video path
        rounded_style: rounded-background style dict
        layout: subtitle layout
        crf: video quality
        preset: FFmpeg encoding preset
        progress_callback: progress callback (progress: int, message: str)
        reference_height: reference height (fixed 720p)
    """
    # Check subtitle data
    if not asr_data or not asr_data.segments:
        raise ValueError("Empty subtitle data, cannot render video")

    # Sanity-check the layout
    if layout == SubtitleLayoutEnum.ONLY_TRANSLATE:
        has_translation = any(
            seg.translated_text and seg.translated_text.strip() for seg in asr_data.segments
        )
        if not has_translation:
            layout = SubtitleLayoutEnum.ONLY_ORIGINAL
    elif (
        layout == SubtitleLayoutEnum.TRANSLATE_ON_TOP
        or layout == SubtitleLayoutEnum.ORIGINAL_ON_TOP
    ):
        has_translation = any(
            seg.translated_text and seg.translated_text.strip() for seg in asr_data.segments
        )
        if not has_translation:
            layout = SubtitleLayoutEnum.ONLY_ORIGINAL

    # Video info
    width, height, video_duration = _get_video_info(video_path)

    # Build and scale the style
    style_config = rounded_style or {}
    style_config["layout"] = layout
    style = RoundedBgStyle(**style_config)

    scale_factor = height / reference_height
    if scale_factor != 1.0:
        style = replace(
            style,
            font_size=int(style.font_size * scale_factor),
            corner_radius=int(style.corner_radius * scale_factor),
            padding_h=int(style.padding_h * scale_factor),
            padding_v=int(style.padding_v * scale_factor),
            margin_bottom=int(style.margin_bottom * scale_factor),
            line_spacing=int(style.line_spacing * scale_factor),
            letter_spacing=int(style.letter_spacing * scale_factor),
        )

    with tempfile.TemporaryDirectory(prefix="rounded_subtitle_") as temp_dir:
        temp_path = Path(temp_dir)

        # Step 1: render every subtitle PNG (0-30%)
        logger.debug(
            f"Generating subtitle PNGs (total: {len(asr_data.segments)}, layout: {layout.value})"
        )
        subtitle_frames = []

        for i, seg in enumerate(asr_data.segments):
            # Primary/secondary text per layout
            if layout == SubtitleLayoutEnum.ONLY_ORIGINAL:
                primary, secondary = seg.text, ""
            elif layout == SubtitleLayoutEnum.ONLY_TRANSLATE:
                primary, secondary = seg.translated_text or "", ""
            elif layout == SubtitleLayoutEnum.ORIGINAL_ON_TOP:
                primary, secondary = seg.text, seg.translated_text or ""
            else:  # TRANSLATE_ON_TOP
                primary, secondary = seg.translated_text or "", seg.text

            # Render the subtitle image
            img = render_subtitle_image(primary, secondary, width, height, style)
            png_path = temp_path / f"subtitle_{i:06d}.png"
            img.save(png_path, "PNG")

            # Record timestamps
            start_time = seg.start_time / 1000.0
            end_time = seg.end_time / 1000.0
            subtitle_frames.append((start_time, end_time, png_path))

            # Progress callback
            if progress_callback:
                progress = int((i + 1) / len(asr_data.segments) * 30)
                progress_callback(progress, f"Tạo ảnh phụ đề {i + 1}/{len(asr_data.segments)}")

        if not subtitle_frames:
            raise ValueError("No valid subtitle images generated")

        # Step 2: overlay onto the video in batches (30-100%)
        logger.debug("Overlaying subtitle batches onto video")
        BATCH_SIZE = 50
        current_video = video_path
        total_batches = (len(subtitle_frames) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_idx in range(total_batches):
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min((batch_idx + 1) * BATCH_SIZE, len(subtitle_frames))
            batch_frames = subtitle_frames[start_idx:end_idx]

            # Build the overlay filter chain
            input_args = ["-i", current_video]
            filter_parts = []

            for local_idx, (start, end, png_path) in enumerate(batch_frames):
                input_args.extend(["-i", str(png_path)])
                prev = f"[v{local_idx}]" if local_idx > 0 else "[0:v]"
                curr = f"[{local_idx + 1}:v]"
                out = f"[v{local_idx + 1}]"
                filter_parts.append(
                    f"{prev}{curr}overlay=0:0:enable='between(t,{start},{end})'{out}"
                )

            filter_complex = ";".join(filter_parts)
            final_output = f"[v{len(batch_frames)}]"

            # Is this the last batch?
            is_last_batch = batch_idx == total_batches - 1
            batch_output = (
                output_path if is_last_batch else temp_path / f"batch_{batch_idx:03d}.mp4"
            )

            logger.debug(f"Processing batch {batch_idx + 1}/{total_batches}（{len(batch_frames)}个字幕）")
            # Build the ffmpeg command
            # -t keeps the source duration so an ended overlay cannot truncate the video
            cmd = [
                "ffmpeg",
                "-y",
                *input_args,
                "-filter_complex",
                filter_complex,
                "-map",
                final_output,
                "-map",
                "0:a?",
                "-t",
                str(video_duration),  # Keep the source duration
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast" if not is_last_batch else preset,
                "-crf",
                "18" if not is_last_batch else str(crf),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                str(batch_output),
            ]

            if batch_idx == 0 or is_last_batch:
                cmd_str = subprocess.list2cmdline(cmd)
                logger.debug(f"FFmpeg cmd: {cmd_str}")

            result = subprocess.run(
                cmd, env=child_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=(
                    getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                ),
            )

            if result.returncode != 0:
                logger.error(f"Lo batch {batch_idx + 1} that bai: {result.stderr}")
                raise RuntimeError(f"Xu ly phu de that bai (batch {batch_idx + 1})")

            # Update progress (30-100%)
            if progress_callback:
                progress = 30 + int((batch_idx + 1) / total_batches * 70)
                progress_callback(progress, f"Ghép video {batch_idx + 1}/{total_batches}")

            # The batch output becomes the next input
            current_video = str(batch_output)

        logger.debug("Video synthesis complete")
