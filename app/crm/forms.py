"""The forms people fill in. Each one gets Bootstrap's form styling automatically."""
from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _
from PIL import Image

from . import logo, look
from .dates import days_off_text, work_days_text
from .models import (EDIT_OBJECTS, LANGS, Account, ChangeOrder, Company, Contact, Crew, Job, Lead, Note, Opportunity, Payment,
                     PriceItem, Property, User, Worker, WorkType, home_state, is_day_off, type_choices, work_types)



def type_box():
    """The type of work, picked from the business's own list (Admin > Types of work)."""
    return forms.ChoiceField(label=_("Type of work"), choices=type_choices)


class Bootstrap:
    """Adds Bootstrap's classes to every field."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = (widget.attrs.get("class", "") + " " + css).strip()


def date_box():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def days_off_help():
    return str(_("Days off: %(days)s. Tick this only when the work really has to be on one of them.")) % {"days": days_off_text()}


def day_off_box():
    return forms.BooleanField(label=_("Work on a day off"), required=False, help_text=lazy(days_off_help, str)())


def check_day(form, field):
    """Jobs and inspections go on work days, unless "Work on a day off" is ticked."""
    day = form.cleaned_data.get(field)
    if day and is_day_off(day) and not form.cleaned_data.get("day_off_ok"):
        form.add_error(field, _("Pick a work day (%(days)s). To use a day off, tick “Work on a day off”.") % {"days": work_days_text()})


class LoginForm(Bootstrap, AuthenticationForm):
    """The sign-in form: user name and password."""


# ---------- accounts ----------
class NewAccountForm(Bootstrap, forms.Form):
    """One form creates the account, its first contact and its first property."""
    kind = forms.ChoiceField(label=_("Type of account"), choices=Account.Kind.choices)
    name = forms.CharField(label=_("Name"), max_length=160)
    phone = forms.CharField(label=_("Phone"), max_length=30, required=False)
    email = forms.EmailField(label=_("Email"), required=False)
    language = forms.ChoiceField(label=_("Language"), choices=LANGS, help_text=_("The customer's language. Texts to them start in this language."))
    street = forms.CharField(label=_("Street address"), max_length=160)
    city = forms.CharField(label=_("City"), max_length=80, required=False)
    state = forms.CharField(label=_("State"), max_length=2, required=False, initial=home_state)
    zip_code = forms.CharField(label=_("ZIP"), max_length=10, required=False)

    def save(self):
        d = self.cleaned_data
        account = Account.objects.create(name=d["name"], kind=d["kind"], language=d["language"])
        role = Contact.Role.OWNER if d["kind"] == Account.Kind.HOMEOWNER else Contact.Role.OFFICE
        Contact.objects.create(account=account, name=d["name"], role=role, phone=d["phone"], email=d["email"], is_primary=True)
        Property.objects.create(account=account, street=d["street"], city=d["city"], state=d["state"], zip_code=d["zip_code"])
        return account


class AccountForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "kind", "language", "customer_since"]


class ContactForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "role", "phone", "email", "is_primary"]


class PropertyForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Property
        fields = ["street", "city", "state", "zip_code", "site_name", "site_phone", "access_notes"]


class NoteForm(Bootstrap, forms.Form):
    text = forms.CharField(label=_("Note"), widget=forms.Textarea(attrs={"rows": 3}))


# ---------- opportunities ----------
class OpportunityForm(Bootstrap, forms.ModelForm):
    job_type = type_box()

    class Meta:
        model = Opportunity
        fields = ["place", "job_type", "source", "labor_only", "description"]
        labels = {"description": _("What is it for?")}
        help_texts = {"description": ""}
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["place"].queryset = account.properties.all()
        self.fields["place"].empty_label = None
        self.fields["source"].choices = [("", "---------")] + list(Opportunity.Source.choices)


class InspectionForm(Bootstrap, forms.Form):
    day = forms.DateField(label=_("Day"), widget=date_box())
    time = forms.TimeField(label=_("Time"), widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    day_off_ok = day_off_box()

    def clean(self):
        data = super().clean()
        check_day(self, "day")
        return data


class SignForm(Bootstrap, forms.Form):
    signed_how = forms.ChoiceField(label=_("How was it signed?"))

    def __init__(self, *args, opportunity, **kwargs):
        super().__init__(*args, **kwargs)
        how = Opportunity.SignedHow
        order = [how.PO, how.PAPER] if opportunity.account.is_company else [how.PAPER, how.LINK]
        self.fields["signed_how"].choices = [(h.value, h.label) for h in order]


class LostForm(Bootstrap, forms.Form):
    lost_reason = forms.ChoiceField(label=_("Reason"), choices=Opportunity.LostReason.choices)


# ---------- jobs ----------
class ScheduleForm(Bootstrap, forms.ModelForm):
    day_off_ok = day_off_box()
    field_order = ["crew", "first_day", "day_off_ok", "days", "workers"]

    class Meta:
        model = Job
        fields = ["crew", "first_day", "days", "workers"]
        labels = {"days": _("How many work days")}
        widgets = {"first_day": date_box(), "workers": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["crew"].queryset = Crew.objects.filter(active=True)
        self.fields["crew"].required = True
        self.fields["crew"].empty_label = None
        self.fields["first_day"].required = True
        self.fields["workers"].queryset = Worker.objects.filter(active=True, crew__isnull=True)
        self.fields["workers"].help_text = _("Workers who help on this job. They have no login; this records who worked.")

    def clean(self):
        data = super().clean()
        check_day(self, "first_day")
        return data

    def clean_days(self):
        days = self.cleaned_data["days"]
        if not 1 <= days <= 60:
            raise forms.ValidationError(_("Enter a number of days from 1 to 60."))
        return days


class RefForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Job
        fields = ["ref_type", "ref_number"]

    def clean(self):
        data = super().clean()
        if data.get("ref_number") and not data.get("ref_type"):
            self.add_error("ref_type", _("Pick the kind of number."))
        if not data.get("ref_number"):
            data["ref_type"] = ""
        return data


class WarrantyForm(Bootstrap, forms.Form):
    problem = forms.CharField(label=_("What is the problem?"), widget=forms.Textarea(attrs={"rows": 2}))


# ---------- the Apple Notes import ----------
class ImportForm(Bootstrap, forms.Form):
    file = forms.FileField(label=_("The notes export file"), help_text=_("The .json file exported from Apple Notes."))
    skip_folders = forms.CharField(
        label=_("Folders to leave out"), required=False, max_length=500,
        help_text=_("Apple Notes folders that are never imported, separated by commas. Their notes are counted, not stored."))


class ImportedNoteForm(Bootstrap, forms.Form):
    """What the app read from a note. The administrator can correct it before creating the account."""
    name = forms.CharField(label=_("Name"), max_length=160, required=False)
    phone = forms.CharField(label=_("Phone"), max_length=30, required=False)
    email = forms.EmailField(label=_("Email"), required=False)
    street = forms.CharField(label=_("Street address"), max_length=160, required=False)
    city = forms.CharField(label=_("City"), max_length=80, required=False)
    zip_code = forms.CharField(label=_("ZIP"), max_length=10, required=False)

    def clean(self):
        data = super().clean()
        if not (data.get("name") or data.get("street")):
            raise forms.ValidationError(_("Enter a name or a street address for the new account."))
        return data


# ---------- leads ----------
class LeadForm(Bootstrap, forms.ModelForm):
    """A request typed in by the office, or sent by the website's form."""
    job_type = type_box()

    class Meta:
        model = Lead
        fields = ["name", "phone", "email", "street", "city", "state", "zip_code", "job_type", "message", "language", "source"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if not (data.get("phone") or data.get("email")):
            raise forms.ValidationError(_("Enter a phone number or an email address, so someone can answer."))
        return data


class ConvertForm(Bootstrap, forms.Form):
    """Convert a lead: the type of work, and (for a customer with an open job) where the request goes."""
    job_type = type_box()
    add_to_job = forms.ChoiceField(label=_("What should happen?"), widget=forms.RadioSelect, required=False)

    def __init__(self, *args, open_job=None, **kwargs):
        super().__init__(*args, **kwargs)
        if open_job:
            self.fields["add_to_job"].choices = [("", _("Start a new opportunity")),
                                                 ("yes", _("Add the request to job #%(number)s") % {"number": open_job.number})]
        else:
            del self.fields["add_to_job"]


class UnfitForm(Bootstrap, forms.Form):
    reason = forms.ChoiceField(label=_("Reason"), choices=Lead.Reason.choices)


# ---------- money on a job ----------
class ChangeOrderForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = ChangeOrder
        fields = ["description", "amount"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if not amount:
            raise forms.ValidationError(_("Enter the amount. Use a minus sign to take work off."))
        return amount


class PaymentForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "check_number", "paid_on"]
        widgets = {"paid_on": date_box()}

    def __init__(self, *args, balance, **kwargs):
        super().__init__(*args, **kwargs)
        self.balance = balance

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError(_("Enter the amount received."))
        if amount > self.balance:
            raise forms.ValidationError(_("That is more than the balance due."))
        return amount


# ---------- the Price Book and the company's details ----------
class PriceItemForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = PriceItem
        fields = ["supplier", "line", "code", "name", "unit", "cost", "price"]


class NewPriceForm(Bootstrap, forms.Form):
    cost = forms.DecimalField(label=_("Cost"), max_digits=10, decimal_places=2, min_value=0)
    price = forms.DecimalField(label=_("Selling price"), max_digits=10, decimal_places=2, min_value=0)


class PriceUploadForm(Bootstrap, forms.Form):
    file = forms.FileField(label=_("The price spreadsheet"), help_text=_("An Excel file (.xlsx) with one row for each item: its code, name, unit, cost and selling price."))
    supplier = forms.CharField(label=_("Supplier"), max_length=80)
    line = forms.CharField(label=_("Product line"), max_length=80, required=False)


class CompanyForm(Bootstrap, forms.ModelForm):
    """Admin › Company details. The logo is not one of the company's own fields: it is checked and made ready by logo.check,
    and the view keeps it (logo.store)."""
    logo_upload = forms.ImageField(
        label=_("Logo"), required=False, widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}),
        help_text=_("Shown at the top left of every proposal, change order, invoice and receipt, above the business's name. "
                    "PNG, JPEG or WebP, at least 200 pixels wide, no larger than 5 MB. A document already signed or sent keeps the logo it had."))
    no_logo = forms.BooleanField(label=_("Stop using the logo"), required=False)

    class Meta:
        model = Company
        fields = ["name", "tagline", "legal_name", "license_number", "address", "phone",
                  "proposal_terms_en", "proposal_terms_es", "invoice_terms_en", "invoice_terms_es", "lead_owner", "lead_backup",
                  "summary_emails", "review_link"]
        widgets = {field: forms.Textarea(attrs={"rows": 2}) for field in
                   ["proposal_terms_en", "proposal_terms_es", "invoice_terms_en", "invoice_terms_es"]}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo_png = None
        if not self.instance.logo:
            del self.fields["no_logo"]
        for name in ("lead_owner", "lead_backup"):
            self.fields[name].queryset = self.fields[name].queryset.exclude(profile="crew").filter(is_active=True)
            self.fields[name].label_from_instance = lambda user: user.label

    def clean_logo_upload(self):
        upload = self.cleaned_data.get("logo_upload")
        if not upload:
            return None
        self.logo_png = logo.check(upload)
        return upload


# ---------- logins and their permission sets
class LoginDetailsForm(Bootstrap, forms.ModelForm):
    """A login: who it is for, its profile, its permission sets, and (when typed) a new password.
    The password box is not one of the login's own fields: a password is only ever saved through set_password, which scrambles it."""
    edit_objects = forms.MultipleChoiceField(
        label=_("Edit"), choices=EDIT_OBJECTS, required=False, widget=forms.CheckboxSelectMultiple,
        help_text=_("For an Office login: the kinds of record it may change on their Edit pages. The administrator may edit everything."))
    new_password = forms.CharField(label=_("Password"), required=False, strip=False,
                                   widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                   help_text=_("At least 10 characters. For a login that exists, leave this empty to keep its password."))
    field_order = ["username", "new_password"]

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "profile", "crew", "is_active", "edit_objects",
                  "can_price_book", "can_costs", "can_billing", "can_data_editor", "can_inspect", "can_delete", "can_crew_lead"]
        labels = {"is_active": _("Can sign in")}
        help_texts = {"is_active": _("Turn this off instead of deleting a login. Its name stays in the history."),
                      "first_name": _("For a login made for one person. The history then shows this name."),
                      "email": _("Where the app sends this person's reminders. It can stay empty.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["crew"].queryset = Crew.objects.filter(active=True)
        self.fields["crew"].help_text = _("For the Crew profile: the crew whose jobs this login sees.")
        if self.instance.pk:                                        # a login that exists shows only the sets for its profile
            for name in User.OFFICE_SETS + User.CREW_SETS:
                if name not in self.sets_for(self.instance.profile):
                    del self.fields[f"can_{name}"]
            if self.instance.profile != User.Profile.OFFICE:
                del self.fields["edit_objects"]
        else:
            self.initial.setdefault("edit_objects", [key for key, _label in EDIT_OBJECTS])

    @staticmethod
    def sets_for(profile):
        return [] if profile == User.Profile.ADMIN else User.CREW_SETS if profile == User.Profile.CREW else User.OFFICE_SETS

    def clean_new_password(self):
        password = self.cleaned_data["new_password"]
        if password:
            password_validation.validate_password(password, self.instance)
        elif not self.instance.pk:
            raise forms.ValidationError(_("A new login needs a password."))
        return password

    def clean(self):
        data = super().clean()
        user = self.instance
        if user.pk and user.is_admin_profile and (data.get("profile") != User.Profile.ADMIN or not data.get("is_active")):
            if not User.objects.filter(profile=User.Profile.ADMIN, is_active=True).exclude(pk=user.pk).exists():
                raise forms.ValidationError(_("This is the only administrator. Add another administrator before changing this one."))
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        for name in User.OFFICE_SETS + User.CREW_SETS:              # a set that is not for this profile goes back to how a new login starts
            if name not in self.sets_for(user.profile):
                setattr(user, f"can_{name}", User._meta.get_field(f"can_{name}").default)
        if user.profile == User.Profile.CREW:
            user.edit_objects = []                                  # a crew login edits no record
        elif "edit_objects" not in self.fields:
            user.edit_objects = user.edit_objects or [key for key, _label in EDIT_OBJECTS]
        if self.cleaned_data["new_password"]:
            user.set_password(self.cleaned_data["new_password"])
        user.save()
        return user


# ---------- Edit pages: every field a person can change on a record. Numbers, stages, dates stamped by a step,
# links between records and customer links are kept by the app, so they are not here.
class LeadEditForm(LeadForm):
    class Meta(LeadForm.Meta):
        fields = LeadForm.Meta.fields + ["owner"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = User.objects.filter(is_active=True).exclude(profile=User.Profile.CREW)
        self.fields["owner"].label_from_instance = lambda user: user.label


class OpportunityEditForm(Bootstrap, forms.ModelForm):
    job_type = type_box()

    class Meta:
        model = Opportunity
        fields = ["place", "job_type", "source", "labor_only", "description", "lost_reason"]
        labels = {"description": _("What is it for?")}
        help_texts = {"description": _("For a proposal that has lines, the lines are changed in the proposal builder.")}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opp = self.instance
        self.fields["place"].queryset = opp.account.properties.all()
        self.fields["place"].empty_label = None
        if opp.proposal_lines.exists():
            del self.fields["description"]                          # the proposal builder keeps it in step with the lines
        if opp.stage != Opportunity.Stage.LOST:
            del self.fields["lost_reason"]


class JobEditForm(Bootstrap, forms.ModelForm):
    job_type = type_box()

    class Meta:
        model = Job
        fields = ["place", "job_type", "price", "labor_only", "scope", "ref_type", "ref_number"]
        help_texts = {"price": _("The price from the signed proposal. Signed change orders are added to it.")}
        widgets = {"scope": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["place"].queryset = self.instance.account.properties.all()
        self.fields["place"].empty_label = None
        if self.instance.is_warranty:
            del self.fields["price"]
            self.fields["job_type"].choices = [("warranty", work_types()["warranty"].name)]
    
    def clean(self):
        data = super().clean()
        if data.get("ref_number") and not data.get("ref_type"):
            self.add_error("ref_type", _("Pick the kind of number."))
        if not data.get("ref_number"):
            data["ref_type"] = ""
        if data.get("price") is not None and data["price"] < 0:
            self.add_error("price", _("A price cannot be below zero."))
        return data


class PaymentEditForm(PaymentForm):
    class Meta(PaymentForm.Meta):
        fields = ["amount", "method", "check_number", "paid_on", "kind"]


class NoteEditForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Note
        fields = ["text", "noted_on"]
        widgets = {"text": forms.Textarea(attrs={"rows": 6}), "noted_on": date_box()}


class WorkTypeForm(Bootstrap, forms.ModelForm):
    """A type of work. The three built in (Inspection, Warranty visit, Other) are always offered."""
    class Meta:
        model = WorkType
        fields = ["name_en", "name_es", "days", "in_revenue_report", "words", "position", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.built_in:
            del self.fields["active"]
            if self.instance.key == "other":
                del self.fields["in_revenue_report"]            # "Other" is always a column of its own

    def clean_days(self):
        days = self.cleaned_data["days"]
        if not 1 <= days <= 60:
            raise forms.ValidationError(_("Enter a number of days from 1 to 60."))
        return days


# ---------- the business's look
class LookForm(Bootstrap, forms.ModelForm):
    """Admin › Colors and icon. The picture is not stored as it came: clean_icon_upload fits it on a square (look.fitted_icon)."""
    icon_upload = forms.ImageField(
        label=_("App icon"), required=False, widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}),
        help_text=_("A square picture works best, at least 180 × 180 pixels: PNG, JPEG or WebP. "
                    "Any other shape is fitted on a white square. With no picture, the app draws one from the name and the colors."))
    no_icon = forms.BooleanField(label=_("Stop using the uploaded icon"), required=False)

    class Meta:
        model = Company
        fields = ["accent_color", "bar_color"]
        widgets = {name: forms.TextInput(attrs={"type": "color", "class": "form-control-color"}) for name in ["accent_color", "bar_color"]}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon_png = None
        if not self.instance.icon:
            del self.fields["no_icon"]

    def clean_accent_color(self):
        return self.cleaned_data["accent_color"].strip().lower()

    def clean_bar_color(self):
        return self.cleaned_data["bar_color"].strip().lower()

    def clean_icon_upload(self):
        upload = self.cleaned_data.get("icon_upload")
        if not upload:
            return None
        if upload.size > settings.MAX_FILE_SIZE:
            raise forms.ValidationError(_("The picture is larger than 25 MB."))
        upload.seek(0)
        image = Image.open(upload)                  # already checked by the field: it is a picture
        image.load()
        if max(image.size) < look.SMALLEST:
            raise forms.ValidationError(_("The picture is too small for an icon: its longer side needs at least 180 pixels."))
        self.icon_png = look.fitted_icon(image)
        return upload

