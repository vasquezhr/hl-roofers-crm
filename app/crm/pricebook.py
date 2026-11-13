"""
The Price Book: reading a price spreadsheet and working out what it would change.

A price file is an Excel sheet (.xlsx) with a row of column names and then one row for each item.
The column names can be in English or Spanish, in any order. The reader looks for:

    code            "Code", "SKU", "Item #", "Part #", "Código"
    item            "Item", "Description", "Product", "Name", "Descripción", "Material"
    unit            "Unit", "UOM", "Unidad"                      (optional)
    cost            "Cost", "Our cost", "Costo"
    selling price   "Price", "Selling price", "Sell", "Precio", "Precio de venta"

Nothing is saved while reading. The review page shows what would change; Confirm saves it.
"""
import logging
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import Workbook, load_workbook

from .models import PriceEntry, PriceItem, PriceUpload

logger = logging.getLogger(__name__)
MOST_ROW_WARNINGS = 20                  # a file with a hundred bad rows must not fill the log

COLUMNS = {
    "code": ["code", "sku", "item #", "item no", "item number", "part #", "part no", "part number", "product code", "codigo", "código"],
    "name": ["item", "description", "product", "name", "descripcion", "descripción", "material", "producto", "nombre"],
    "unit": ["unit", "uom", "u/m", "unidad", "per"],
    "cost": ["cost", "our cost", "unit cost", "costo", "costo unitario"],
    "price": ["price", "selling price", "sell price", "sell", "retail", "precio", "precio de venta", "venta"],
}


class PriceFileProblem(Exception):
    """The file could not be used. The message is shown to the administrator."""


def tidy(cell):
    return re.sub(r"\s+", " ", str(cell if cell is not None else "")).strip()


def amount(cell):
    """35.5, '35.50' or '$1,035.50' -> Decimal. An empty cell is None."""
    text = tidy(cell).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def find_columns(row):
    """Which column holds what, from a row of column names: {"name": 1, "cost": 3, ...}"""
    found = {}
    for index, cell in enumerate(row):
        title = tidy(cell).lower().rstrip(":.")
        for field, names in COLUMNS.items():
            if field not in found and title in names:
                found[field] = index
    return found


def read_price_file(upload, who=""):
    """The rows of a price spreadsheet: [{"code", "name", "unit", "cost", "price"}, ...]
    A file that cannot be used, and every row that is left out, is written to errors.log with the file's name and the row
    number. `who` says which login uploaded it."""
    file_name = getattr(upload, "name", "the file")
    try:
        sheet = load_workbook(upload, read_only=True, data_only=True).worksheets[0]
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    except Exception as problem:
        logger.warning("Price file %r could not be read as an Excel file (.xlsx), uploaded by %s: %s: %s", file_name, who, type(problem).__name__, problem)
        raise PriceFileProblem(_("This file could not be read. Upload an Excel file (.xlsx)."))
    # the row of column names is somewhere near the top
    at, columns = next(((i, find_columns(row)) for i, row in enumerate(rows[:20]) if {"name", "cost", "price"} <= set(find_columns(row))), (None, None))
    if columns is None:
        logger.warning("Price file %r has no row of column names with Item, Cost and Price in its first 20 rows (uploaded by %s)", file_name, who)
        raise PriceFileProblem(_("The sheet needs a row of column names with at least: Item, Cost and Price. A blank file with the right columns is on the Price Book page."))
    items, seen, warned = [], set(), 0
    for number, row in enumerate(rows[at + 1:], at + 2):                # number: the row's place in the sheet, as Excel numbers it
        problem = ""
        cell = lambda field: row[columns[field]] if field in columns and columns[field] < len(row) else None      # noqa: E731
        name, cost, price = tidy(cell("name")), amount(cell("cost")), amount(cell("price"))
        if not name or cost is None or price is None:
            if name and (cost is not None or price is not None or cell("cost") or cell("price")):
                problem = "the cost or the price is missing or is not a number"       # a heading or a subtotal has neither, and is not reported
        else:
            code = tidy(cell("code")) or re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")[:40]
            if code in seen:
                problem = f"the code {code} is already used by an earlier row"
        if problem:
            warned += 1
            if warned <= MOST_ROW_WARNINGS:
                logger.warning("Price file %r, row %s left out: %s (uploaded by %s)", file_name, number, problem, who)
        if problem or not name or cost is None or price is None:
            continue                                                  # an empty row, a heading, a subtotal, or a row that was reported
        seen.add(code)
        items.append({"code": code[:40], "name": name[:200], "unit": tidy(cell("unit"))[:20], "cost": str(cost), "price": str(price)})
    if warned > MOST_ROW_WARNINGS:
        logger.warning("Price file %r: %s more rows were left out and are not listed (uploaded by %s)", file_name, warned - MOST_ROW_WARNINGS, who)
    if not items:
        logger.warning("Price file %r has no rows with an item, a cost and a price (uploaded by %s)", file_name, who)
        raise PriceFileProblem(_("No rows with an item, a cost and a price were found in the sheet."))
    return items


def percent(before, after):
    """How much a cost moved, in percent: 35.50 -> 39.40 is 11.0"""
    return round(float((after - before) / before * 100), 1) if before else 0.0


def compare(rows, supplier, line):
    """What a file would do to the Price Book. Nothing is saved here."""
    have = {item.code: item for item in PriceItem.objects.filter(supplier__iexact=supplier)}
    added, changed, same = [], [], 0
    for row in rows:
        item, cost, price = have.get(row["code"]), Decimal(row["cost"]), Decimal(row["price"])
        if item is None:
            added.append(row)
        elif (item.cost, item.price) != (cost, price):
            change = percent(item.cost, cost)
            changed.append({"item": item, "row": row, "cost": cost, "price": price, "percent": change, "big": abs(change) > 10})
        else:
            same += 1
    codes = {row["code"] for row in rows}
    missing = sum(1 for item in have.values() if item.line.lower() == line.lower() and item.code not in codes)
    return {"added": added, "changed": changed, "same": same, "missing": missing}


@transaction.atomic
def apply(rows, file_name, supplier, line, user):
    """Save a reviewed file: one new line of history for each new or changed item. Returns the PriceUpload."""
    found = compare(rows, supplier, line)
    upload = PriceUpload.objects.create(file_name=file_name[:200], supplier=supplier, line=line, uploaded_by=user, actor=user.label,
                                        added=len(found["added"]), changed=len(found["changed"]), same=found["same"])
    for change in found["changed"]:
        change["item"].set_price(change["cost"], change["price"], upload, actor=user.label)
    for row in found["added"]:
        item = PriceItem.objects.create(code=row["code"], name=row["name"], unit=row["unit"], supplier=supplier, line=line,
                                        cost=row["cost"], price=row["price"], added_by=upload)
        PriceEntry.objects.create(item=item, upload=upload, cost=row["cost"], price=row["price"], actor=user.label)
    return upload


@transaction.atomic
def roll_back(upload):
    """Undo an upload: its new items go, and its changed items return to the price before. The upload stays in the list."""
    PriceItem.objects.filter(added_by=upload).delete()
    for item in PriceItem.objects.filter(history__upload=upload).distinct():
        item.history.filter(upload=upload).delete()
        last = item.history.order_by("effective_on", "id").last()
        if last:
            item.cost, item.price, item.changed_on = last.cost, last.price, last.effective_on
            item.save()
    upload.rolled_back_at = timezone.now()
    upload.save()


def blank_file():
    """An empty price sheet with the right column names, for the business to fill in."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Prices"
    sheet.append(["Code", "Item", "Unit", "Cost", "Price"])
    sheet.append(["GAF-HDZ", "GAF Timberline HDZ shingles", "bundle", 35.50, 43.00])
    for column, width in zip("ABCDE", (14, 44, 10, 10, 10)):
        sheet.column_dimensions[column].width = width
    return book
