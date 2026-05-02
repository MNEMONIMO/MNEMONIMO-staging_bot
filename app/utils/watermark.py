import io
from PIL import Image, ImageDraw, ImageFont
from loguru import logger


def add_watermark(image_bytes: bytes, text: str = "AI Preview • Staging Bot") -> bytes:
    """Add a diagonal watermark to an image."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        watermark = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)

        width, height = img.size

        # Try to use a font, fall back to default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except Exception:
            font = ImageFont.load_default()

        # Draw semi-transparent text diagonally
        text_color = (255, 255, 255, 100)
        step_x = width // 3
        step_y = height // 3

        for row in range(3):
            for col in range(3):
                x = col * step_x
                y = row * step_y
                draw.text((x, y), text, font=font, fill=text_color)

        combined = Image.alpha_composite(img, watermark).convert("RGB")
        output = io.BytesIO()
        combined.save(output, format="JPEG", quality=90)
        return output.getvalue()

    except Exception as e:
        logger.error(f"Watermark failed: {e}")
        return image_bytes  # Return original if watermark fails
