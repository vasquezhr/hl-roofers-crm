"""
The business's logo on its documents. Admin › Company details sets it.

A logo is a PNG, JPEG or WebP picture at least 200 pixels wide and no larger than 5 MB. It is not kept as it came: it is
turned the right way up and saved as a PNG (at most 900 pixels wide) in MEDIA_ROOT/logo/, under a name made from its own
content (logo/3f9a1c07b2de.png). So the same picture is always the same file, and a different picture never replaces
another one.

Every proposal, change order, invoice and receipt shows it at the top left, above the business's name: on the page and
in the PDF. A copy that was kept (documents.keep) remembers the name of the logo it was made with, and that file is never
deleted while a kept copy uses it, so an old document still shows the logo it was signed or sent with.
The customer's Accept pages are public, so the logo is served to anyone (company_logo in admin_views.py), under its own
content-based name, which can be cached for ever.
"""
import hashlib
import io
import logging
import re

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024         # the largest file that is accepted
SMALLEST = 200                      # the picture must be at least this many pixels wide
WIDEST = 900                        # a wider picture is made smaller: enough for a sharp print, light for the PDF
FORMATS = {"PNG", "JPEG", "MPO", "WEBP"}      # MPO is how a phone's JPEG may be labelled
NAME = re.compile(r"logo/([0-9a-f]{12})\.png")


def check(upload):
    """Checks an uploaded logo and returns it ready to keep: PNG bytes. Raises ValidationError with the reason."""
    if upload.size > MAX_BYTES:
        raise ValidationError(_("The logo is larger than 5 MB."))
    upload.seek(0)
    image = Image.open(upload)
    if image.format not in FORMATS:
        raise ValidationError(_("The logo must be a PNG, JPEG or WebP picture."))
    image.load()
    if image.width < SMALLEST:
        raise ValidationError(_("The logo is too small: it needs to be at least 200 pixels wide."))
    image = ImageOps.exif_transpose(image).convert("RGBA")
    if image.width > WIDEST:
        image = image.resize((WIDEST, max(1, round(image.height * WIDEST / image.width))), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def store(company, png):
    """Keep this logo as the company's. Returns the name of the logo it replaces (or "")."""
    old = company.logo.name or ""
    name = f"logo/{hashlib.sha1(png).hexdigest()[:12]}.png"
    if not default_storage.exists(name):
        name = default_storage.save(name, ContentFile(png))
    company.logo = name
    company.save(update_fields=["logo"])
    return old


def drop(company):
    """Stop using the logo. Returns the name of the one that was used (or "")."""
    old = company.logo.name or ""
    company.logo = ""
    company.save(update_fields=["logo"])
    return old


def discard(name):
    """Delete a logo's file once nothing needs it: not the company's current logo, and not any kept copy of a document."""
    from .models import Company, KeptDocument
    if not name or Company.load().logo.name == name or KeptDocument.objects.filter(company__logo=name).exists():
        return False
    try:
        default_storage.delete(name)
    except OSError:
        logger.exception("The old logo file %s could not be deleted", name)
        return False
    return True


# ---------------------------------------------------------------- on a document
def name_of(firm):
    """The logo's file name for a company, or for the business's details kept with a copy (where it is plain text). "" when there is none."""
    logo = getattr(firm, "logo", "") or ""
    name = getattr(logo, "name", logo) or ""
    return name if NAME.fullmatch(str(name)) else ""


def url_of(firm):
    """The public address of the logo, or "" when the business has none. It changes whenever the picture does."""
    found = NAME.fullmatch(name_of(firm))
    return reverse("company_logo", args=[found.group(1)]) if found else ""


def read(firm):
    """The logo's PNG bytes, or None (no logo, or its file is missing)."""
    name = name_of(firm)
    if not name:
        return None
    try:
        with default_storage.open(name, "rb") as stored:
            return stored.read()
    except OSError:
        logger.warning("The logo file %s is missing from the photos and files folder", name)
        return None


def pdf_image(firm, width, height):
    """The logo as a picture for the PDF, as large as fits in width × height (in points) and no larger than it is. None when there is none."""
    from reportlab.platypus import Image as Picture
    data = read(firm)
    if data is None:
        return None
    try:
        wide, high = Image.open(io.BytesIO(data)).size
        scale = min(width / wide, height / high)
        picture = Picture(io.BytesIO(data), width=wide * scale, height=high * scale, mask="auto")
    except Exception:
        logger.exception("The logo %s could not be put in a PDF", name_of(firm))
        return None
    picture.hAlign = "LEFT"
    return picture
