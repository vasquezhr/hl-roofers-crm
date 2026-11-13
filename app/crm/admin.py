"""
Django's built-in admin site, at /admin/. Only the administrator uses it:
to add logins and crews, and to look at or correct raw records.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _

from .models import (Account, Activity, ChangeOrder, Company, Contact, Crew, ImportBatch, ImportedNote, Job, Lead, Note, Opportunity, Payment,
                     PriceEntry, PriceItem, PriceUpload, Property, ProposalLine, Sequence, User, Worker)

def site_name():
    """The admin site's title: the business's name from Company details, read each time a page is drawn."""
    return f"{Company.load().name} CRM"


admin.site.site_header = admin.site.site_title = lazy(site_name, str)()


@admin.register(User)
class LoginAdmin(UserAdmin):
    """A login. The profile (Admin, Office or Crew) is the only access setting, so Django's own
    staff, superuser, group and permission boxes are left off this page."""
    list_display = ("username", "first_name", "last_name", "profile", "crew", "is_active", "last_login")
    list_filter = ("profile", "is_active")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Who it is"), {"fields": ("first_name", "last_name", "email")}),
        (_("Profile in the app"), {"fields": ("profile", "crew", "is_active")}),
        (_("Dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + ((_("Profile in the app"), {"fields": ("profile", "crew")}),)


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


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "job_type", "status", "source", "owner", "received_at")
    list_filter = ("status", "source")
    search_fields = ("name", "phone", "email", "street")


class ProposalLineInline(admin.TabularInline):
    model = ProposalLine
    extra = 0


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("number", "account", "job_type", "stage", "total", "created_at")
    list_filter = ("stage", "job_type")
    search_fields = ("number", "account__name")
    readonly_fields = ("number",)
    inlines = [ProposalLineInline]


class ChangeOrderInline(admin.TabularInline):
    model = ChangeOrder
    extra = 0


class PaymentInline(admin.TabularInline):
    """Correct or remove a payment that was recorded by mistake."""
    model = Payment
    extra = 0
    fields = ("paid_on", "amount", "method", "check_number", "kind", "actor")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("number", "account", "job_type", "stage", "crew", "first_day", "price")
    list_filter = ("stage", "crew", "job_type")
    search_fields = ("number", "account__name", "ref_number")
    readonly_fields = ("number",)
    inlines = [ChangeOrderInline, PaymentInline]


class PriceEntryInline(admin.TabularInline):
    model = PriceEntry
    extra = 0


@admin.register(PriceItem)
class PriceItemAdmin(admin.ModelAdmin):
    list_display = ("name", "supplier", "line", "unit", "cost", "price", "changed_on")
    list_filter = ("supplier", "line")
    search_fields = ("name", "code")
    inlines = [PriceEntryInline]


@admin.register(PriceUpload)
class PriceUploadAdmin(admin.ModelAdmin):
    list_display = ("file_name", "supplier", "line", "uploaded_at", "actor", "added", "changed", "rolled_back_at")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """One row. It is easier to edit under Admin › Company details in the app itself."""

    def has_add_permission(self, request):
        return not Company.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


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
