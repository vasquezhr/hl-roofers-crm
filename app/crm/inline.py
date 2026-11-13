"""
Editing a section of a record page in place (the pencil at the top right of a section).

The pencil is a link to the record's own Edit page with ?section=customer (or contact, scope ...). Without JavaScript that
page opens and shows only that section's fields. With JavaScript (hl.js, part 14) the same page is asked for just its form
(?partial=1), and the form is shown in the section itself, with Save and Cancel. Save posts the form to the same Edit page
(with section=...), so every rule stays in one place: who may edit (`may_edit`), what is written in the history (`changes`),
the customer's comments that cannot be changed, and every check on the fields.

A form says which of its fields belong to which section in its `SECTIONS`; `Bootstrap.prune` keeps only those. The section
asked for comes from the web address or the posted form, and is carried here by SectionMiddleware, so the views need no change.
"""
from contextvars import ContextVar

current = ContextVar("section", default="")


class SectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current.set((request.GET.get("section") or request.POST.get("section") or "")[:20])
        try:
            return self.get_response(request)
        finally:
            current.reset(token)
