import io
from PIL import Image


def decode_preview(data: bytes, width: int, height: int) -> Image.Image:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "#000000")
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas
