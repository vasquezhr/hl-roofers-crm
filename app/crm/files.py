"""
Photos and files: checking what was uploaded, and making the small copy of a photo for the lists.

Only photos (JPEG, PNG, WebP, GIF) and PDF files are kept. A file is recognised by what is inside it, not by its name,
so a renamed program or web page is refused. A photo is turned the right way up for its small copy (phones store
"rotate this" as a note in the photo); the photo itself is kept exactly as it came, with its date and other details.
"""
import io
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps

from .models import Attachment

logger = logging.getLogger(__name__)

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
    """Check one uploaded file and keep it. Returns the Attachment, or raises Refused with the reason.
    A refused file and a file that could not be saved are written to errors.log: which file, who, and why."""
    where = f"job {job.number}" if job else f"account {account.pk}"
    if upload.size > settings.MAX_FILE_SIZE:
        logger.warning("File refused: %r is %s MB, over the limit (%s, by %s)", upload.name, upload.size // (1024 * 1024), where, user.label)
        raise Refused(_("%(name)s is larger than 25 MB.") % {"name": upload.name})
    data = upload.read()
    content_type, image = kind_of(data)
    if not content_type:
        logger.warning("File refused: %r is not a photo or a PDF (%s, by %s)", upload.name, where, user.label)
        raise Refused(_("%(name)s is not a photo or a PDF. Only photos (JPEG, PNG, WebP) and PDF files can be added.") % {"name": upload.name})
    attachment = Attachment(account=account, job=job, change_order=change_order, category=category, caption=caption[:200],
                            name=upload.name[:200], content_type=content_type, size=len(data), uploaded_by=user, actor=user.label)
    try:
        attachment.file.save(upload.name, ContentFile(data), save=False)
        if image is not None:
            attachment.thumb.save("small.jpg", ContentFile(small_copy(image)), save=False)
        attachment.save()
    except Exception:                                               # a full disk, a folder that cannot be written, a database error
        logger.exception("File could not be saved: %r, %s bytes (%s, by %s, into %s)", upload.name, len(data), where, user.label, settings.MEDIA_ROOT)
        for stored in (attachment.file, attachment.thumb):          # what was already written to the disk is taken away again
            try:
                if stored and stored.name:
                    stored.storage.delete(stored.name)
            except Exception:
                logger.exception("A half-saved file could not be removed: %s", stored.name)
        raise Refused(_("%(name)s could not be saved. The reason is in the error log (Admin, System status).") % {"name": upload.name})
    return attachment
