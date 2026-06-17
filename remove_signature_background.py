from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw

DEFAULT_OUTPUT_SUFFIX = "_transparent"


@dataclass(slots=True)
class RemovalOptions:
    method: str = "white"
    transparent_cutoff: int = 8
    opaque_cutoff: int = 100
    background_sigma: float = 31.0
    threshold_scale: float = 0.5
    min_area: int = 60
    crop: bool = False
    padding: int = 10
    output_format: str = "png"
    output_suffix: str = DEFAULT_OUTPUT_SUFFIX


@dataclass(slots=True)
class NamedRegion:
    name: str
    left: int
    top: int
    right: int
    bottom: int
    shape: str = "rect"
    points: tuple[tuple[int, int], ...] = ()
    mask_png: bytes = b""

    def normalized_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        if width <= 0 or height <= 0:
            raise ValueError("Image dimensions must be positive.")

        if self.shape_key() == "mask":
            mask = self.mask_image(width, height)
            if mask is not None:
                bbox = mask.getbbox()
                if bbox is not None:
                    left, top, right, bottom = bbox
                    left = max(0, min(left, width - 1))
                    top = max(0, min(top, height - 1))
                    right = max(left + 1, min(right, width))
                    bottom = max(top + 1, min(bottom, height))
                    return left, top, right, bottom

        if self.shape_key() == "polygon" and len(self.points) >= 3:
            normalized_points = self.normalized_points(width, height)
            xs = [point[0] for point in normalized_points]
            ys = [point[1] for point in normalized_points]
            left = max(0, min(xs))
            top = max(0, min(ys))
            right = min(width, max(xs) + 1)
            bottom = min(height, max(ys) + 1)
            return left, top, max(left + 1, right), max(top + 1, bottom)

        return self._normalized_rect_box(width, height)

    def normalized_points(self, width: int, height: int) -> list[tuple[int, int]]:
        if width <= 0 or height <= 0:
            raise ValueError("Image dimensions must be positive.")

        if self.shape_key() == "polygon" and len(self.points) >= 3:
            normalized: list[tuple[int, int]] = []
            for raw_x, raw_y in self.points:
                x = max(0, min(int(raw_x), width - 1))
                y = max(0, min(int(raw_y), height - 1))
                normalized.append((x, y))

            if len(set(normalized)) >= 3:
                return normalized

        left, top, right, bottom = self.normalized_box(width, height)
        return [
            (left, top),
            (max(left, right - 1), top),
            (max(left, right - 1), max(top, bottom - 1)),
            (left, max(top, bottom - 1)),
        ]

    def shape_key(self) -> str:
        if self.shape == "mask" and self.mask_png:
            return "mask"
        return "polygon" if self.shape == "polygon" and len(self.points) >= 3 else "rect"

    def mask_image(self, width: int, height: int) -> Image.Image | None:
        if self.shape != "mask" or not self.mask_png or width <= 0 or height <= 0:
            return None

        try:
            with Image.open(BytesIO(self.mask_png)) as image:
                mask = image.convert("L")
        except Exception:
            return None

        if mask.size != (width, height):
            mask = mask.resize((width, height), Image.Resampling.NEAREST)
        return mask

    def copy(self) -> "NamedRegion":
        return NamedRegion(
            name=self.name,
            left=self.left,
            top=self.top,
            right=self.right,
            bottom=self.bottom,
            shape=self.shape_key(),
            points=tuple((int(x), int(y)) for x, y in self.points),
            mask_png=bytes(self.mask_png),
        )

    def _normalized_rect_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        left, right = sorted((int(self.left), int(self.right)))
        top, bottom = sorted((int(self.top), int(self.bottom)))

        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))
        return left, top, right, bottom


def estimate_background_color(image: Image.Image, sample_size: int = 12) -> tuple[float, float, float]:
    width, height = image.size
    sample_size = max(1, min(sample_size, width, height))

    corners = [
        (range(0, sample_size), range(0, sample_size)),
        (range(width - sample_size, width), range(0, sample_size)),
        (range(0, sample_size), range(height - sample_size, height)),
        (range(width - sample_size, width), range(height - sample_size, height)),
    ]

    pixels: list[tuple[int, int, int]] = []
    for xs, ys in corners:
        for x in xs:
            for y in ys:
                pixels.append(image.getpixel((x, y)))

    count = max(1, len(pixels))
    red = sum(pixel[0] for pixel in pixels) / count
    green = sum(pixel[1] for pixel in pixels) / count
    blue = sum(pixel[2] for pixel in pixels) / count
    return red, green, blue


def estimate_border_gray_std(image: Image.Image) -> float:
    rgb = np.array(image.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape
    margin = max(4, min(height, width) // 20)

    border = np.concatenate(
        [
            rgb[:margin, :, :].reshape(-1, 3),
            rgb[height - margin :, :, :].reshape(-1, 3),
            rgb[margin : height - margin, :margin, :].reshape(-1, 3),
            rgb[margin : height - margin, width - margin :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    gray = border.mean(axis=1)
    return float(gray.std())


def clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def remove_flat_background(
    image: Image.Image,
    transparent_cutoff: int = 8,
    opaque_cutoff: int = 100,
) -> Image.Image:
    background_r, background_g, background_b = estimate_background_color(image)
    source = image.convert("RGBA")
    width, height = source.size
    result = Image.new("RGBA", source.size, (0, 0, 0, 0))

    source_pixels = source.load()
    result_pixels = result.load()
    alpha_span = max(1, opaque_cutoff - transparent_cutoff)

    for y in range(height):
        for x in range(width):
            red, green, blue, _ = source_pixels[x, y]
            delta = max(background_r - red, background_g - green, background_b - blue)

            if delta <= transparent_cutoff:
                result_pixels[x, y] = (0, 0, 0, 0)
                continue

            alpha = (delta - transparent_cutoff) * 255.0 / alpha_span
            alpha = max(0.0, min(255.0, alpha))
            alpha_ratio = alpha / 255.0

            recovered_red = clamp_channel((red - background_r * (1.0 - alpha_ratio)) / alpha_ratio)
            recovered_green = clamp_channel((green - background_g * (1.0 - alpha_ratio)) / alpha_ratio)
            recovered_blue = clamp_channel((blue - background_b * (1.0 - alpha_ratio)) / alpha_ratio)

            result_pixels[x, y] = (
                recovered_red,
                recovered_green,
                recovered_blue,
                clamp_channel(alpha),
            )

    return result


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    cleaned = np.zeros_like(mask)

    for index in range(1, component_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area >= min_area:
            cleaned[labels == index] = 255

    return cleaned


def remove_textured_light_background(
    image: Image.Image,
    background_sigma: float = 31.0,
    threshold_scale: float = 0.5,
    min_area: int = 60,
) -> Image.Image:
    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    background = cv2.GaussianBlur(gray, (0, 0), background_sigma)
    ink = cv2.subtract(background, gray)

    otsu_threshold, _ = cv2.threshold(ink, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    low_threshold = max(6.0, otsu_threshold * threshold_scale)
    high_threshold = max(low_threshold + 12.0, otsu_threshold * 1.25)

    edge_mask = np.where(ink >= low_threshold, 255, 0).astype(np.uint8)
    core_mask = np.where(ink >= high_threshold, 255, 0).astype(np.uint8)

    edge_mask = remove_small_components(edge_mask, min_area=min_area)
    core_mask = remove_small_components(core_mask, min_area=min_area)

    alpha = np.clip(
        (ink.astype(np.float32) - low_threshold) * 255.0 / max(1.0, high_threshold - low_threshold),
        0,
        255,
    )
    alpha = 255.0 * np.power(alpha / 255.0, 0.65)
    alpha = np.where(edge_mask > 0, alpha, 0)
    alpha = np.maximum(alpha, core_mask.astype(np.float32))
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.7)
    alpha = np.where(alpha >= 20, alpha, 0)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    rgba = np.zeros((alpha.shape[0], alpha.shape[1], 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, "RGBA")


def connected_border_mask(candidate_mask: np.ndarray) -> np.ndarray:
    if candidate_mask.ndim != 2:
        raise ValueError("candidate_mask must be a single-channel image.")

    mask = np.where(candidate_mask > 0, 255, 0).astype(np.uint8)
    component_count, labels, _, _ = cv2.connectedComponentsWithStats(mask, 8)
    if component_count <= 1:
        return np.zeros_like(mask)

    border_labels = set(int(value) for value in labels[0, :])
    border_labels.update(int(value) for value in labels[-1, :])
    border_labels.update(int(value) for value in labels[:, 0])
    border_labels.update(int(value) for value in labels[:, -1])
    border_labels.discard(0)

    if not border_labels:
        return np.zeros_like(mask)

    return np.isin(labels, list(border_labels)).astype(np.uint8) * 255


def estimate_light_background_color(rgb: np.ndarray) -> np.ndarray:
    height, width, _ = rgb.shape
    margin = max(2, min(height, width) // 30)
    border = np.concatenate(
        [
            rgb[:margin, :, :].reshape(-1, 3),
            rgb[height - margin :, :, :].reshape(-1, 3),
            rgb[margin : height - margin, :margin, :].reshape(-1, 3),
            rgb[margin : height - margin, width - margin :, :].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.float32)

    if border.size == 0:
        return np.array([255.0, 255.0, 255.0], dtype=np.float32)

    brightness = border.mean(axis=1)
    channel_spread = border.max(axis=1) - border.min(axis=1)
    light_neutral = border[(brightness >= 180) & (channel_spread <= 48)]
    if len(light_neutral) >= 12:
        return np.median(light_neutral, axis=0).astype(np.float32)

    return np.median(border, axis=0).astype(np.float32)


def remove_white_icon_background(
    image: Image.Image,
    transparent_cutoff: int = 18,
    opaque_cutoff: int = 96,
) -> Image.Image:
    source = image.convert("RGBA")
    rgb = np.array(source.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape

    background = estimate_light_background_color(rgb)
    distance = np.linalg.norm(rgb - background.reshape(1, 1, 3), axis=2)
    brightness = rgb.mean(axis=2)
    channel_spread = rgb.max(axis=2) - rgb.min(axis=2)

    core_candidate = ((distance <= transparent_cutoff) | ((brightness >= 246) & (channel_spread <= 20))).astype(np.uint8)
    soft_candidate = ((distance <= opaque_cutoff) & (brightness >= 168)).astype(np.uint8)

    core_background = connected_border_mask(core_candidate)
    soft_background = connected_border_mask(soft_candidate)

    alpha = np.full((height, width), 255.0, dtype=np.float32)
    alpha[soft_background > 0] = np.clip(
        (distance[soft_background > 0] - transparent_cutoff) * 255.0 / max(1, opaque_cutoff - transparent_cutoff),
        0,
        255,
    )
    alpha[core_background > 0] = 0

    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.45)
    alpha[core_background > 0] = 0
    alpha = np.where(alpha < 8, 0, alpha)
    alpha = np.where(alpha > 248, 255, alpha)
    alpha_uint8 = np.clip(alpha, 0, 255).astype(np.uint8)

    recovered = rgb.copy()
    partial_mask = (alpha_uint8 > 0) & (alpha_uint8 < 255) & (soft_background > 0)
    if np.any(partial_mask):
        alpha_ratio = alpha_uint8[partial_mask].astype(np.float32)[:, None] / 255.0
        recovered[partial_mask] = np.clip(
            (rgb[partial_mask] - background.reshape(1, 3) * (1.0 - alpha_ratio)) / np.maximum(alpha_ratio, 1e-3),
            0,
            255,
        )

    rgba = np.dstack([recovered.astype(np.uint8), alpha_uint8])
    return Image.fromarray(rgba, "RGBA")


def crop_to_visible_area(image: Image.Image, padding: int = 10, alpha_threshold: int = 8) -> Image.Image:
    alpha = image.getchannel("A").point(lambda value: 255 if value > alpha_threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        return image

    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def resolve_method(image: Image.Image, requested_method: str) -> str:
    if requested_method != "auto":
        return requested_method

    border_gray_std = estimate_border_gray_std(image)
    if border_gray_std >= 5.0:
        return "adaptive"
    return "flat"


def normalize_output_format(output_format: str) -> str:
    normalized = output_format.lower().strip()
    if normalized not in {"png", "jpeg", "jpg"}:
        raise ValueError(f"Unsupported output format: {output_format}")
    if normalized == "jpg":
        return "jpeg"
    return normalized


def sanitize_filename_component(value: str, fallback: str = "region") -> str:
    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value.strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def sanitize_output_stem(value: str, fallback: str = "image") -> str:
    allowed = {" ", "-", "_", "(", ")"}
    cleaned = "".join(character if character.isalnum() or character in allowed else "_" for character in value.strip())
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" ._")
    return cleaned or fallback


def make_unique_output_path(path: Path, used_paths: set[str] | None = None) -> Path:
    used_paths = used_paths if used_paths is not None else set()
    candidate = path
    counter = 1

    while candidate.exists() or str(candidate).lower() in used_paths:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1

    used_paths.add(str(candidate).lower())
    return candidate


def apply_polygon_mask(image: Image.Image, polygon_points: list[tuple[int, int]]) -> Image.Image:
    masked = image.convert("RGBA")
    alpha_mask = Image.new("L", masked.size, 0)
    ImageDraw.Draw(alpha_mask).polygon(polygon_points, fill=255)
    combined_alpha = ImageChops.multiply(masked.getchannel("A"), alpha_mask)
    masked.putalpha(combined_alpha)
    return masked


def apply_alpha_mask(image: Image.Image, alpha_mask: Image.Image) -> Image.Image:
    masked = image.convert("RGBA")
    local_mask = alpha_mask.convert("L")
    if local_mask.size != masked.size:
        local_mask = local_mask.resize(masked.size, Image.Resampling.NEAREST)

    combined_alpha = ImageChops.multiply(masked.getchannel("A"), local_mask)
    masked.putalpha(combined_alpha)
    return masked


def remove_background_from_image(image: Image.Image, options: RemovalOptions | None = None) -> tuple[Image.Image, str]:
    options = options or RemovalOptions()
    rgb_image = image.convert("RGB")
    requested_method = options.method.lower().strip()

    if requested_method in {"white", "icon", "background"}:
        result = remove_white_icon_background(
            rgb_image,
            transparent_cutoff=max(18, options.transparent_cutoff),
            opaque_cutoff=max(96, options.opaque_cutoff),
        )
        method = "white"
    elif requested_method == "scan":
        scan_method = resolve_method(rgb_image, "auto")
        if scan_method == "adaptive":
            result = remove_textured_light_background(
                rgb_image,
                background_sigma=options.background_sigma,
                threshold_scale=options.threshold_scale,
                min_area=options.min_area,
            )
        else:
            result = remove_flat_background(
                rgb_image,
                transparent_cutoff=options.transparent_cutoff,
                opaque_cutoff=options.opaque_cutoff,
            )
        method = f"scan-{scan_method}"
    else:
        method = resolve_method(rgb_image, requested_method)

        if method == "adaptive":
            result = remove_textured_light_background(
                rgb_image,
                background_sigma=options.background_sigma,
                threshold_scale=options.threshold_scale,
                min_area=options.min_area,
            )
        else:
            result = remove_flat_background(
                rgb_image,
                transparent_cutoff=options.transparent_cutoff,
                opaque_cutoff=options.opaque_cutoff,
            )

    if options.crop:
        result = crop_to_visible_area(result, padding=options.padding)

    return result, method


def convert_result_for_output(image: Image.Image, output_format: str) -> Image.Image:
    normalized = normalize_output_format(output_format)
    if normalized == "png":
        return image.convert("RGBA")

    white_background = Image.new("RGB", image.size, (255, 255, 255))
    white_background.paste(image.convert("RGBA"), mask=image.getchannel("A"))
    return white_background


def build_output_path(
    input_path: Path,
    output_path: Path | None = None,
    output_dir: Path | None = None,
    output_format: str = "png",
    suffix: str = DEFAULT_OUTPUT_SUFFIX,
    output_stem: str | None = None,
) -> Path:
    normalized_format = normalize_output_format(output_format)
    extension = ".png" if normalized_format == "png" else ".jpg"

    if output_path is not None:
        return output_path

    target_dir = output_dir if output_dir is not None else input_path.parent
    stem = sanitize_output_stem(output_stem, fallback=input_path.stem) if output_stem else input_path.stem
    return target_dir / f"{stem}{suffix}{extension}"


def process_image_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    options: RemovalOptions | None = None,
    output_stem: str | None = None,
) -> tuple[Path, str]:
    options = options or RemovalOptions()
    source_path = Path(input_path)
    explicit_output_path = Path(output_path) if output_path is not None else None
    explicit_output_dir = Path(output_dir) if output_dir is not None else None

    if not source_path.exists():
        raise FileNotFoundError(f"Input file not found: {source_path}")

    output_file_path = build_output_path(
        source_path,
        output_path=explicit_output_path,
        output_dir=explicit_output_dir,
        output_format=options.output_format,
        suffix=options.output_suffix,
        output_stem=output_stem,
    )
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path = make_unique_output_path(output_file_path)

    with Image.open(source_path) as image:
        result, method = remove_background_from_image(image, options=options)

    final_image = convert_result_for_output(result, options.output_format)
    save_format = "PNG" if normalize_output_format(options.output_format) == "png" else "JPEG"
    final_image.save(output_file_path, save_format)
    return output_file_path, method


def process_image_regions(
    input_path: str | Path,
    regions: list[NamedRegion],
    output_dir: str | Path | None = None,
    options: RemovalOptions | None = None,
    output_stem: str | None = None,
) -> tuple[list[Path], list[str]]:
    options = options or RemovalOptions()
    source_path = Path(input_path)
    explicit_output_dir = Path(output_dir) if output_dir is not None else source_path.parent

    if not source_path.exists():
        raise FileNotFoundError(f"Input file not found: {source_path}")
    if not regions:
        raise ValueError("At least one region must be provided.")

    explicit_output_dir.mkdir(parents=True, exist_ok=True)
    normalized_format = normalize_output_format(options.output_format)
    extension = ".png" if normalized_format == "png" else ".jpg"
    save_format = "PNG" if normalized_format == "png" else "JPEG"

    output_paths: list[Path] = []
    methods: list[str] = []
    used_paths: set[str] = set()
    region_options = replace(options, crop=False)

    with Image.open(source_path) as image:
        rgb_image = image.convert("RGB")
        rgba_image = image.convert("RGBA")
        width, height = rgb_image.size

        for index, region in enumerate(regions, start=1):
            left, top, right, bottom = region.normalized_box(width, height)
            region_shape = region.shape_key()

            if region_shape == "mask":
                mask_image = region.mask_image(width, height)
                if mask_image is not None:
                    region_image = rgba_image.crop((left, top, right, bottom))
                    local_mask = mask_image.crop((left, top, right, bottom))
                    result = apply_alpha_mask(region_image, local_mask)
                    method = "mask"
                else:
                    region_image = rgb_image.crop((left, top, right, bottom))
                    result, method = remove_background_from_image(region_image, options=region_options)
            else:
                region_image = rgb_image.crop((left, top, right, bottom))
                result, method = remove_background_from_image(region_image, options=region_options)

            if region_shape == "polygon":
                polygon_points = region.normalized_points(width, height)
                local_points = [(x - left, y - top) for x, y in polygon_points]
                result = apply_polygon_mask(result, local_points)

            if options.crop:
                result = crop_to_visible_area(result, padding=options.padding)

            final_image = convert_result_for_output(result, options.output_format)

            base_name = sanitize_filename_component(region.name, fallback=f"region_{index}")
            source_stem = sanitize_output_stem(output_stem, fallback=source_path.stem) if output_stem else source_path.stem
            output_file_stem = f"{source_stem}_{base_name}{options.output_suffix}"
            output_path = make_unique_output_path(explicit_output_dir / f"{output_file_stem}{extension}", used_paths)
            final_image.save(output_path, save_format)
            output_paths.append(output_path)
            methods.append(method)

    return output_paths, methods


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove a white image background or create a scan-style transparent image."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="image/Signiture1.png",
        help="Input image path. Default: image/Signiture1.png",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file path. Default: <input>_transparent.<ext>",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory. Ignored when --output is set.",
    )
    parser.add_argument(
        "--output-format",
        choices=["png", "jpeg"],
        default="png",
        help="Export format. PNG keeps transparency; JPEG uses a white background.",
    )
    parser.add_argument(
        "--suffix",
        default=DEFAULT_OUTPUT_SUFFIX,
        help="Suffix added to the output filename when --output is not provided.",
    )
    parser.add_argument(
        "--method",
        choices=["white", "scan", "auto", "flat", "adaptive"],
        default="white",
        help="Processing method. white removes only border-connected light backgrounds; scan keeps the old scan-style extraction.",
    )
    parser.add_argument(
        "--transparent-cutoff",
        type=int,
        default=8,
        help="Difference from the flat background that still counts as fully transparent.",
    )
    parser.add_argument(
        "--opaque-cutoff",
        type=int,
        default=100,
        help="Difference from the flat background that counts as fully opaque.",
    )
    parser.add_argument(
        "--background-sigma",
        type=float,
        default=31.0,
        help="Blur strength for adaptive mode. Larger values handle broader paper texture.",
    )
    parser.add_argument(
        "--threshold-scale",
        type=float,
        default=0.5,
        help="Adaptive mode sensitivity. Lower values keep more faint strokes.",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=60,
        help="Remove tiny isolated background specks smaller than this many pixels in adaptive mode.",
    )
    parser.add_argument(
        "--crop",
        action="store_true",
        help="Crop empty transparent margin after background removal.",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=10,
        help="Transparent padding to keep when --crop is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    options = RemovalOptions(
        method=args.method,
        transparent_cutoff=args.transparent_cutoff,
        opaque_cutoff=args.opaque_cutoff,
        background_sigma=args.background_sigma,
        threshold_scale=args.threshold_scale,
        min_area=args.min_area,
        crop=args.crop,
        padding=args.padding,
        output_format=args.output_format,
        output_suffix=args.suffix,
    )

    output_path, method = process_image_file(
        input_path=args.input,
        output_path=args.output,
        output_dir=args.output_dir,
        options=options,
    )
    print(f"Saved result to: {output_path} (method: {method})")


if __name__ == "__main__":
    main()
