from io import BytesIO
from uuid import uuid4
import warnings

from django.core.files.base import ContentFile
from PIL import Image, ImageOps
from rest_framework.exceptions import ValidationError


MAX_IMAGE_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def prepare_image(upload):
    """Decode and re-encode pixels; never retain client filenames or metadata."""
    if upload.size > MAX_IMAGE_SIZE:
        raise ValidationError("Images must be 10 MB or smaller.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                image_format = image.format
                if image_format not in IMAGE_EXTENSIONS:
                    raise ValidationError("Upload a JPEG, PNG or WebP image.")
                image.verify()

            upload.seek(0)
            with Image.open(upload) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                transparent = "A" in oriented.getbands() or "transparency" in oriented.info
                mode = "RGBA" if transparent and image_format != "JPEG" else "RGB"
                pixels = oriented.convert(mode)
                # A fresh image retains pixels only, including no EXIF/GPS data.
                clean = Image.new(mode, pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format=image_format)
    except (OSError, ValueError, TypeError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError("Upload a valid, undamaged JPEG, PNG or WebP image.")

    if output.tell() > MAX_IMAGE_SIZE:
        raise ValidationError("The processed image must be 10 MB or smaller.")
    return ContentFile(
        output.getvalue(), name=f"{uuid4().hex}.{IMAGE_EXTENSIONS[image_format]}",
    )
