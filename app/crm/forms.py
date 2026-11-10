"""The forms people fill in. Each one gets Bootstrap's form styling automatically."""
from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from .models import JOB_TYPES, LANGS, Account, Contact, Crew, Job, Opportunity, Property, Worker


class Bootstrap:
    """Adds Bootstrap's classes to every field."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = (widget.attrs.get("class", "") + " " + css).strip()


def date_box():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def work_day(day):
    """Jobs and inspections go on work days only."""
    if day.weekday() not in settings.WORK_WEEKDAYS:
        raise forms.ValidationError(_("Pick a work day, Monday to Friday."))
    return day


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
    state = forms.CharField(label=_("State"), max_length=2, required=False, initial="VA")
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
        self.fields["job_type"].choices = [c for c in JOB_TYPES if c[0] != "warranty"]      # warranty visits are opened from a job
        self.fields["source"].choices = [("", "---------")] + list(Opportunity.Source.choices)


class InspectionForm(Bootstrap, forms.Form):
    day = forms.DateField(label=_("Day"), widget=date_box())
    time = forms.TimeField(label=_("Time"), widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))

    def clean_day(self):
        return work_day(self.cleaned_data["day"])


class ProposalForm(Bootstrap, forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["description", "total"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def clean_total(self):
        total = self.cleaned_data["total"]
        if not total or total <= 0:
            raise forms.ValidationError(_("Enter the price."))
        return total

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if not text:
            raise forms.ValidationError(_("Say what the proposal covers."))
        return text


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

    def clean_first_day(self):
        return work_day(self.cleaned_data["first_day"])

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
