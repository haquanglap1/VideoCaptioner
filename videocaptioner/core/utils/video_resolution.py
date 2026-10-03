"""Bound output dimensions without cropping or upscaling the source."""

PRESETS = (0, 720, 1080, 1440, 2160)


def resolution_filter(limit: int) -> str:
    if type(limit) is not int or limit not in PRESETS:
        raise ValueError("Unsupported output resolution")
    if not limit:
        return ""
    long_side = limit * 16 // 9
    return (f"scale=w='min(iw,if(gte(iw,ih),{long_side},{limit}))':"
            f"h='min(ih,if(gte(iw,ih),{limit},{long_side}))':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2")


def output_dimensions(width: int, height: int, limit: int) -> tuple[int, int]:
    resolution_filter(limit)
    if not limit:
        return width, height
    if width <= 0 or height <= 0:
        raise ValueError("Invalid source video dimensions")
    long_side = limit * 16 // 9
    box_w, box_h = (long_side, limit) if width >= height else (limit, long_side)
    factor = min(1, box_w / width, box_h / height)
    return max(2, int(width * factor) // 2 * 2), max(2, int(height * factor) // 2 * 2)
