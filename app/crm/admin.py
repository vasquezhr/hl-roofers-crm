"""
Django's built-in admin site, at /admin/. Only the administrator uses it:
to add logins and crews, and to look at or correct raw records.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Account, Activity, Contact, Crew, ImportBatch, ImportedNote, Job, Note, Opportunity, Property, Sequence, User, Worker

admin.site.site_header = "H & L Roofers CRM"
admin.site.site_title = "H & L Roofers CRM"


@admin.register(User)
class LoginAdmin(UserAdmin):
    """A login. The profile (Admin, Office or Crew) is the only access setting, so Django's own
    staff, superuser, group and permission boxes are left off this page."""
    list_display = ("username", "first_name", "last_name", "profile", "crew", "is_active", "last_login")
    list_filter = ("profile", "is_active")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Who it is"), {"fields": ("first_name", "last_name", "email")}),
        (_("H & L profile"), {"fields": ("profile", "crew", "is_active")}),
        (_("Dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + ((_("H & L profile"), {"fields": ("profile", "crew")}),)


class WorkerInline(admin.TabularInline):
    model = Worker
    extra = 1


@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    list_display = ("name", "lead_name", "phone", "active")
    inlines = [WorkerInline]


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "crew", "active")
    list_filter = ("crew", "active")


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0


class PropertyInline(admin.TabularInline):
    model = Property
    extra = 0


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "language", "customer_since")
    list_filter = ("kind",)
    search_fields = ("name", "contacts__name", "contacts__phone", "properties__street")
    inlines = [ContactInline, PropertyInline]


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("number", "account", "job_type", "stage", "total", "created_at")
    list_filter = ("stage", "job_type")
    search_fields = ("number", "account__name")
    readonly_fields = ("number",)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("number", "account", "job_type", "stage", "crew", "first_day", "price")
    list_filter = ("stage", "crew", "job_type")
    search_fields = ("number", "account__name", "ref_number")
    readonly_fields = ("number",)


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    """The numbers given to opportunities and jobs. Change "last number used" to carry on from the business's own numbering."""
    list_display = ("year", "last")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "account", "noted_on", "source")
    list_filter = ("source",)
    search_fields = ("title", "text", "account__name")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("at", "actor", "kind", "account", "opportunity", "job")
    list_filter = ("kind",)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("file_name", "uploaded_at", "uploaded_by", "notes_read", "set_aside", "duplicates")


@admin.register(ImportedNote)
class ImportedNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "proposal", "status", "account", "batch")
    list_filter = ("status", "proposal")
    exclude = ("digest",)
