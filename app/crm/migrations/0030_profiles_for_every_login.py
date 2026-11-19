"""Nov 16, 2026: profiles with one tick list (the user's item 7). The three profiles a business starts with are made with the ticks
that do exactly what Admin, Office and Crew did before, and every login keeps what it could do:

  - every login stays on the profile it had (its key is the same: admin, office, crew);
  - before this, an Office login had its own list of the kinds of record it could edit. Edit is now a tick of the profile, so an
    Office login whose list was not "every kind" moves onto a copy of Office made for it, with only those Edit ticks
    ("Office - glenda"). Logins with the same list share one copy.

The tick lists are written out here, not read from permissions.py, so this migration does the same thing whenever it runs.
"""
from django.db import migrations

ADMIN = [
    "lead.see", "lead.create", "lead.edit", "lead.delete", "account.see", "account.create", "account.edit", "account.delete",
    "contact.see", "contact.create", "contact.edit", "contact.delete", "property.see", "property.create", "property.edit", "property.delete",
    "note.see", "note.create", "note.edit", "note.delete", "opportunity.see", "opportunity.create", "opportunity.edit", "opportunity.delete",
    "job.see", "job.create", "job.edit", "job.delete", "change_order.see", "change_order.create", "change_order.edit", "change_order.delete",
    "payment.see", "payment.create", "payment.edit", "payment.delete", "file.see", "file.create", "file.delete", "money.see",
    "money.edit", "costs.see", "email.see", "email.edit", "job_notes.see", "job_notes.edit", "history.see", "today",
    "dashboard", "reports", "schedule", "search", "price_book", "data_editor", "export_data", "import_data",
    "company", "setup", "setup_history", "status", "users", "admin_site", "convert_lead", "send_proposal",
    "close_opps", "send_invoice", "job_steps", "job_workers", "confirm_changes", "change_stages", "inspect", "purge",
    ]
OFFICE = [
    "lead.see", "lead.create", "lead.edit", "account.see", "account.create", "account.edit", "contact.see", "contact.create",
    "contact.edit", "property.see", "property.create", "property.edit", "note.see", "note.create", "note.edit", "opportunity.see",
    "opportunity.create", "opportunity.edit", "job.see", "job.create", "job.edit", "change_order.see", "change_order.create", "change_order.edit",
    "payment.see", "payment.create", "payment.edit", "file.see", "file.create", "money.see", "money.edit", "email.see",
    "email.edit", "job_notes.see", "job_notes.edit", "history.see", "today", "reports", "schedule", "search",
    "convert_lead", "send_proposal", "close_opps", "send_invoice", "job_steps", "job_workers",
    ]
CREW = [
    "job.see", "change_order.see", "payment.see", "file.see", "file.create", "own_jobs", "money.see", "job_notes.see",
    "job_notes.edit", "history.see", "search", "my_day",
    ]
EDIT_KINDS = ["lead", "account", "contact", "property", "note", "opportunity", "job", "change_order", "payment"]


def make_profiles(apps, schema_editor):
    Profile, User = apps.get_model("crm", "Profile"), apps.get_model("crm", "User")
    for key, name_en, name_es, ticks in [("admin", "Administrator", "Administrador", ADMIN), ("office", "Office", "Oficina", OFFICE),
                                         ("crew", "Crew", "Equipo", CREW)]:
        Profile.objects.update_or_create(key=key, defaults={"name_en": name_en, "name_es": name_es, "ticks": ticks})
    # an administrator had every permission set already, so a set switched on for one added nothing. It would now (the job-done
    # email only ever went to Office logins), so it is switched off.
    User.objects.filter(profile="admin").update(can_price_book=False, can_costs=False, can_billing=False, can_data_editor=False,
                                                can_inspect=False, can_delete=False, can_change_stages=False)
    # Office logins that could not edit every kind of record: a copy of Office for each different list
    copies = {}
    for user in User.objects.filter(profile="office").order_by("username"):
        allowed = tuple(kind for kind in EDIT_KINDS if kind in (user.edit_objects or []))
        if len(allowed) == len(EDIT_KINDS):
            continue
        if allowed not in copies:
            ticks = [tick for tick in OFFICE if not (tick.endswith(".edit") and tick[:-5] in EDIT_KINDS and tick[:-5] not in allowed)]
            number = len(copies) + 1
            copies[allowed] = Profile.objects.create(key=f"office-{number}", name_en=f"Office - {user.username}",
                                                     name_es=f"Oficina - {user.username}", ticks=ticks)
        user.profile = copies[allowed].key
        user.save(update_fields=["profile"])


def back(apps, schema_editor):
    """Undo: the logins on a copy of Office go back to Office, with that copy's Edit ticks as their own list."""
    Profile, User = apps.get_model("crm", "Profile"), apps.get_model("crm", "User")
    for profile in Profile.objects.exclude(key__in=["admin", "office", "crew"]):
        kinds = [kind for kind in EDIT_KINDS if f"{kind}.edit" in profile.ticks]
        User.objects.filter(profile=profile.key).update(profile="office", edit_objects=kinds)
    Profile.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0029_profiles_with_one_tick_list"),
    ]

    operations = [
        migrations.RunPython(make_profiles, back),
    ]
