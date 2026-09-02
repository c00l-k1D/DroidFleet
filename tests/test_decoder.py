from PIL import Image
from app.video.decoder import decode_preview


def test_decode_preview_has_fixed_canvas():
    source = Image.new("RGB", (20, 10), "red")
    import io
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    result = decode_preview(buffer.getvalue(), 180, 300)
    assert result.size == (180, 300)
