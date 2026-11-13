"""
Photos and files: checking what was uploaded, and making the small copy of a photo for the lists.

Only photos (JPEG, PNG, WebP, GIF) and PDF files are kept. A file is recognised by what is inside it, not by its name,
so a renamed program or web page is refused. A photo is turned the right way up for its small copy (phones store
"rotate this" as a note in the photo); the photo itself is kept exactly as it came, with its date and other details.
"""
import io

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps

from .models import Attachment

IMAGES = {"JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
MOST = 20                                                           # files in one upload


class Refused(Exception):
    """A file that cannot be kept, with the reason to show."""


def kind_of(data):
    """The type of a file from what is inside it: ("image/jpeg", the photo) or ("application/pdf", None)."""
    if data[:5] == b"%PDF-":
        return "application/pdf", None
    try:
        Image.open(io.BytesIO(data)).verify()                       # a damaged or fake picture fails here
        image = Image.open(io.BytesIO(data))
    except Exception:                                               # anything Pillow cannot read is not a photo
        return None, None
    return IMAGES.get(image.format), image


def small_copy(image):
    """A JPEG about 480 pixels wide, the right way up."""
    image = ImageOps.exif_transpose(image)
    image.thumbnail((480, 480))
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=80)
    return out.getvalue()


def keep(upload, *, account, user, category, job=None, change_order=None, caption=""):
    """Check one uploaded file and keep it. Returns the Attachment, or raises Refused with the reason."""
    if upload.size > settings.MAX_FILE_SIZE:
        raise Refused(_("%(name)s is larger than 25 MB.") % {"name": upload.name})
    data = upload.read()
    content_type, image = kind_of(data)
    if not content_type:
        raise Refused(_("%(name)s is not a photo or a PDF. Only photos (JPEG, PNG, WebP) and PDF files can be added.") % {"name": upload.name})
    attachment = Attachment(account=account, job=job, change_order=change_order, category=category, caption=caption[:200],
                            name=upload.name[:200], content_type=content_type, size=len(data), uploaded_by=user, actor=user.label)
    attachment.file.save(upload.name, ContentFile(data), save=False)
    if image is not None:
        attachment.thumb.save("small.jpg", ContentFile(small_copy(image)), save=False)
    attachment.save()
    return attachment
