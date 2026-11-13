"""
The business's look: its two colors and the app's icon. Admin › Colors and icon sets them.

H & L's colors are the defaults. hl.css has every shade of them, picked by hand, so H & L's pages need
nothing from here. For other colors, this works out the shades the way Bootstrap works out its own, and
each page gets them as a short list of CSS variables that take the place of H & L's.

The app's icon (on the Mac's Dock, a phone's home screen and the browser tab) is, in this order:
  - the picture uploaded under Admin › Colors and icon, fitted on a white square;
  - while the name and both colors are still H & L's, H & L's own icon (static/crm/icon.png);
  - otherwise one drawn here: the name's initials in white on the top bar's color.
"""
import hashlib
import io
import re
from functools import lru_cache
from pathlib import Path

import reportlab
from django.core.exceptions import ValidationError
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageDraw, ImageFont, ImageOps

ACCENT, BAR, NAME = "#b05a22", "#1f3a5f", "H & L Roofers"       # H & L's: what every database starts with
COLOR = re.compile(r"#[0-9a-f]{6}")
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
DARK_CARD = (43, 48, 53)            # a card on the dark theme (Bootstrap's #2b3035): the lighter of its two backgrounds
READABLE = 4.5                      # the contrast ordinary writing needs (WCAG 2, level AA)
SIZE = 512                          # the icon is a square this many pixels across
SMALLEST = 180                      # an uploaded picture must be at least this many pixels across (the iPhone's icon size)
FONT = Path(reportlab.__file__).parent / "fonts" / "VeraBd.ttf"     # Bitstream Vera Sans Bold, which comes with ReportLab
HL_ICON = Path(__file__).parent / "static" / "crm" / "icon.png"
NOT_INITIALS = {"llc", "inc", "co", "corp", "ltd", "the", "and", "y", "de", "del", "la", "el", "los", "las"}


# ---------------------------------------------------------------- colors
def rgb(color):
    """#b05a22 → (176, 90, 34)"""
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def hex_of(color):
    """(176, 90, 34) → #b05a22"""
    return "#%02x%02x%02x" % tuple(round(part) for part in color)


def mix(color, other, share):
    """`color` with `share` of `other` mixed in: 0.2 is 80 % color and 20 % other."""
    return tuple(part + (to - part) * share for part, to in zip(color, other))


def luminance(color):
    """How bright a color looks, from 0 (black) to 1 (white), as WCAG 2 measures it."""
    def linear(part):
        part /= 255
        return part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4
    red, green, blue = (linear(part) for part in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(one, other):
    """How easy writing in one color is to read on the other: from 1 (the same color) to 21 (black on white)."""
    light, dark = sorted((luminance(one), luminance(other)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def readable(color):
    """True when white writing on this color is easy to read."""
    return bool(COLOR.fullmatch(color or "")) and contrast(rgb(color), WHITE) >= READABLE


def readable_color(value):
    """The check on both color fields: a color written like #1f3a5f, dark enough for white writing."""
    if not COLOR.fullmatch(value or ""):
        raise ValidationError(_("Pick a color, or type one like #1f3a5f."))
    if not readable(value):
        raise ValidationError(_("White writing is hard to read on this color. Pick a darker one."))


def lighter_until(color, background, start=0.0):
    """The color, mixed with white a step at a time until writing in it reads well on the background.
    Each step is checked as it will be written in the page: in whole numbers."""
    for step in range(round(start * 20), 21):
        lighter = tuple(round(part) for part in mix(color, WHITE, step / 20))
        if contrast(lighter, background) >= READABLE:
            return lighter
    return WHITE


def shades(accent, bar):
    """The CSS variables for a business's two colors: {name: value}, with the names hl.css uses."""
    main, top = rgb(accent), rgb(bar)
    dark = lighter_until(main, DARK_CARD)          # the main color on the dark theme: light enough to read on it
    whole = lambda color: ", ".join(str(round(part)) for part in color)     # whole numbers, in any language
    return {
        "--hl-bar": bar,
        "--hl-amp": hex_of(lighter_until(main, top, start=0.5)),
        "--hl-accent": accent, "--hl-accent-rgb": whole(main),
        "--hl-accent-hover": hex_of(mix(main, BLACK, .15)),
        "--hl-accent-active": hex_of(mix(main, BLACK, .2)),
        "--hl-accent-active-border": hex_of(mix(main, BLACK, .25)),
        "--hl-accent-text": hex_of(mix(main, BLACK, .4)),
        "--hl-accent-subtle": hex_of(mix(main, WHITE, .8)),
        "--hl-accent-border": hex_of(mix(main, WHITE, .6)),
        "--hl-accent-focus": hex_of(mix(main, WHITE, .5)),
        "--hl-accent-dark": hex_of(dark), "--hl-accent-dark-rgb": whole(dark),
        "--hl-accent-dark-text": hex_of(mix(dark, WHITE, .4)),
        "--hl-accent-dark-subtle": hex_of(mix(main, BLACK, .8)),
        "--hl-accent-dark-border": hex_of(mix(main, BLACK, .4)),
        "--hl-chart-dark": hex_of(dark),
    }


def style(accent, bar):
    """The CSS that puts these colors in place of H & L's, or "" when both are H & L's.
    Only what differs is replaced, so H & L's hand-picked shades stay wherever its color stays."""
    if not (COLOR.fullmatch(accent or "") and COLOR.fullmatch(bar or "")):
        return ""                                   # never write anything but a checked color into the page
    every = shades(accent, bar)
    names = []
    if accent != ACCENT:
        names += [name for name in every if name != "--hl-bar"]
    if bar != BAR:
        names += ["--hl-bar"] + ([] if "--hl-amp" in names else ["--hl-amp"])
    return ":root{" + ";".join(f"{name}:{every[name]}" for name in names) + "}" if names else ""


# ---------------------------------------------------------------- the icon
def initials(name):
    """The letters on a drawn icon: H & L Roofers → H&L · Garcia & Sons Roofing → G&S · Acme Gutters LLC → AG"""
    letters = ""
    for word in re.findall(r"&|[^\s,.&]+", name or ""):
        if word == "&":
            letters += "&"
        elif word.lower() not in NOT_INITIALS:
            letters += next((letter for letter in word if letter.isalnum()), "").upper()
    return letters[:3].strip("&") or "?"


def is_hl(company):
    """True while the business still has H & L's name and colors and no icon of its own."""
    return (company.name, company.accent_color, company.bar_color) == (NAME, ACCENT, BAR) and not company.icon


def version(company):
    """A short code that changes whenever the icon does, so phones and computers fetch the new one."""
    words = f"{company.name}|{company.accent_color}|{company.bar_color}|{company.icon.name}"
    return hashlib.sha1(words.encode()).hexdigest()[:10]


@lru_cache(maxsize=8)
def drawn_icon(name, accent, bar):
    """The icon when none was uploaded: the name's initials in white, an "&" in the light main color, on the top bar's color.
    PNG, SIZE pixels square."""
    text = initials(name)
    background = rgb(bar) if COLOR.fullmatch(bar or "") else rgb(BAR)
    amp = lighter_until(rgb(accent) if COLOR.fullmatch(accent or "") else rgb(ACCENT), background, start=0.5)
    picture = Image.new("RGB", (SIZE, SIZE), background)
    draw = ImageDraw.Draw(picture)
    size = 300
    while True:                                     # the largest letters that fit: 72 % of the width, 42 % of the height
        font = ImageFont.truetype(str(FONT), size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        if (right - left <= SIZE * 0.72 and bottom - top <= SIZE * 0.42) or size <= 40:
            break
        size -= 4
    x, y = (SIZE - (right - left)) / 2 - left, (SIZE - (bottom - top)) / 2 - top
    for letter in text:                             # one letter at a time, so the "&" can have its own color
        draw.text((x, y), letter, font=font, fill=amp if letter == "&" else WHITE)
        x += draw.textlength(letter, font=font)
    out = io.BytesIO()
    picture.save(out, "PNG")
    return out.getvalue()


def fitted_icon(image):
    """An uploaded picture as the icon: the right way up, on a white square, the whole picture showing. PNG bytes.
    A square picture fills the icon; a wider or taller one (a logo) sits in the middle with a white border."""
    image = ImageOps.exif_transpose(image).convert("RGBA")
    width, height = image.size
    room = SIZE if abs(width - height) <= max(width, height) * 0.02 else round(SIZE * 0.84)
    scale = room / max(width, height)
    image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
    square = Image.new("RGBA", (SIZE, SIZE), WHITE + (255,))
    square.alpha_composite(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2))   # see-through parts become white
    out = io.BytesIO()
    square.convert("RGB").save(out, "PNG")
    return out.getvalue()


def icon_bytes(company):
    """The icon itself, as PNG bytes."""
    if company.icon:
        try:
            with company.icon.open("rb") as stored:
                return stored.read()
        except OSError:                             # the file is missing (a copy of the database without its files)
            pass
    if (company.name, company.accent_color, company.bar_color) == (NAME, ACCENT, BAR):
        return HL_ICON.read_bytes()
    return drawn_icon(company.name, company.accent_color, company.bar_color)


# ---------------------------------------------------------------- what each page needs
def of(company):
    """{"style": the CSS for the colors, or "", "bar": the color for the phone's bar, "icon": the icon's address}"""
    bar = company.bar_color if COLOR.fullmatch(company.bar_color or "") else BAR
    icon = static("crm/icon.png") if is_hl(company) else f"{reverse('app_icon')}?v={version(company)}"
    return {"style": style(company.accent_color, company.bar_color), "bar": bar, "icon": icon}
