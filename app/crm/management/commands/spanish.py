"""
python manage.py spanish

Keeps the Spanish wording complete. The app's labels are written in English in the code and the
templates; their Spanish is in one file:  crm/locale/es/LC_MESSAGES/django.po

This command:
  1. finds every label in the templates and the Python files;
  2. checks that each one has Spanish in django.po, and lists what is missing;
  3. writes django.mo, the compiled copy that Django reads.

After adding or changing a label:
    python manage.py spanish --add      adds the new labels to django.po with empty Spanish
    (type the Spanish after msgstr in django.po)
    python manage.py spanish            checks again and rebuilds django.mo

It does the job of Django's makemessages and compilemessages without needing the GNU gettext
programs, which are a separate install on Windows.
"""
import ast
import re
from pathlib import Path

import polib
from django.core.management.base import BaseCommand, CommandError

APP = Path(__file__).resolve().parent.parent.parent                 # the crm folder
PO = APP / "locale" / "es" / "LC_MESSAGES" / "django.po"
IN_TEMPLATE = re.compile(r"""{%\s*(?:trans|translate|trf)\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")
IN_PYTHON = {"_", "gettext", "gettext_lazy"}
PLACEHOLDER = re.compile(r"%\(\w+\)s")


def labels_in_use():
    """Every label marked for translation: {label: [files it is in]}"""
    found = {}
    for path in sorted(APP.rglob("*.html")):
        for double, single in IN_TEMPLATE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(double or single, []).append(path.relative_to(APP).as_posix())
    for path in sorted(APP.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in IN_PYTHON
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, []).append(path.relative_to(APP).as_posix())
    return found


def problems():
    """What is wrong with the Spanish file, as a list of lines. An empty list means it is complete."""
    used, po = labels_in_use(), polib.pofile(str(PO), wrapwidth=0)
    spanish = {entry.msgid: entry.msgstr for entry in po if not entry.obsolete}
    out = []
    for label, files in used.items():
        if not spanish.get(label):
            out.append(f"No Spanish for: {label!r}   (in {files[0]})")
        elif sorted(PLACEHOLDER.findall(label)) != sorted(PLACEHOLDER.findall(spanish[label])):
            out.append(f"The %(...)s parts differ between English and Spanish: {label!r}")
    out += [f"In django.po but not used any more: {label!r}" for label in spanish if label not in used]
    return out


class Command(BaseCommand):
    help = "Check that every label has Spanish, and rebuild the compiled file Django reads."

    def add_arguments(self, parser):
        parser.add_argument("--add", action="store_true", help="Add the labels that are missing to django.po, with empty Spanish.")

    def handle(self, *args, **options):
        po = polib.pofile(str(PO), wrapwidth=0)
        if options["add"]:
            have = {entry.msgid for entry in po}
            new = [label for label in labels_in_use() if label not in have]
            for label in new:
                po.append(polib.POEntry(msgid=label, msgstr=""))
            po.save(str(PO))
            self.stdout.write(f"Added {len(new)} labels to {PO.name}. Type their Spanish after msgstr, then run this command again.")
            return
        found = problems()
        for line in found:
            self.stdout.write(line)
        if found:
            raise CommandError(f"{len(found)} problems in the Spanish file. Nothing was rebuilt.")
        po.save_as_mofile(str(PO.with_suffix(".mo")))
        self.stdout.write(self.style.SUCCESS(f"Spanish is complete: {len(po)} labels. Rebuilt {PO.with_suffix('.mo').name}."))
