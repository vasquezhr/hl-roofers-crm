"""The shell: what each business sets for itself instead of having it written in the code."""
from django.urls import reverse
from django.utils import translation

from crm import reports
from crm.models import Activity, Job, Lead, WorkType, type_choices, type_name

from .base import Base


class TypesOfWork(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def add(self, **fields):
        data = {"name_en": "Solar panels", "name_es": "Paneles solares", "days": "2", "words": "solar, paneles", "position": "20", "active": "on", **fields}
        return self.client.post(reverse("work_type_new"), data)

    def test_the_twelve_types_are_there(self):
        page = self.client.get(reverse("work_types"))
        self.assertEqual([kind.key for kind in page.context["kinds"]],
                         ["repair", "replacement", "gutters", "tpo", "siding", "chimney", "skylight", "metal", "soffit", "inspection", "warranty", "other"])
        self.assertContains(page, "Techo nuevo")

    def test_a_new_type_is_offered_everywhere(self):
        self.add()
        kind = WorkType.objects.get(name_en="Solar panels")
        self.assertEqual(kind.key, "solar-pane")
        self.assertIn(("solar-pane", "Solar panels"), type_choices())
        with translation.override("es"):
            self.assertEqual(type_name("solar-pane"), "Paneles solares")
        self.assertContains(self.client.get(reverse("opp_new", args=[self.account.pk])), "Solar panels")
        # a job of this type gets its usual days when the proposal is signed
        opp = self.opportunity(job_type="solar-pane", stage="proposal", total=900)
        self.assertEqual(opp.sign("paper").days, 2)
        # the website's form can send it by name or by one of its words
        with self.settings(LEAD_FORM_KEY="k"):
            self.client.post(reverse("lead_in"), {"key": "k", "name": "Mina Seo", "phone": "(804) 555-0178", "service": "paneles"})
        self.assertEqual(Lead.objects.get().job_type, "solar-pane")
        self.assertEqual(Activity.objects.filter(kind="type_added").get().detail, "Solar panels")

    def test_its_own_column_in_the_revenue_report(self):
        self.add(in_revenue_report="on")
        columns, _rows = reports.revenue(*reports.span("y"))
        self.assertIn("Solar panels", [label for label, _kind in columns])

    def test_switched_off_it_is_not_offered_and_old_records_keep_it(self):
        job = self.job(job_type="chimney")
        chimney = WorkType.objects.get(key="chimney")
        self.client.post(reverse("work_type_edit", args=[chimney.pk]), {"name_en": "Chimney", "name_es": "Chimenea", "days": "1", "words": "",
                                                                         "position": str(chimney.position)})
        chimney.refresh_from_db()
        self.assertFalse(chimney.active)
        self.assertNotIn("chimney", [key for key, _name in type_choices()])
        self.assertEqual(Job.objects.get(pk=job.pk).get_job_type_display(), "Chimney")
        self.assertIn("Offered: yes → no", Activity.objects.filter(kind="type_edited").get().text)

    def test_the_built_in_ones_stay_offered(self):
        warranty = WorkType.objects.get(key="warranty")
        self.assertNotContains(self.client.get(reverse("work_type_edit", args=[warranty.pk])), 'name="active"')
        self.client.post(reverse("work_type_edit", args=[warranty.pk]), {"name_en": "Warranty call", "name_es": "Visita de garantía", "days": "1",
                                                                          "words": "", "position": "10"})
        warranty.refresh_from_db()
        self.assertEqual((warranty.name_en, warranty.active), ("Warranty call", True))
        self.assertNotIn("warranty", [key for key, _name in type_choices()])           # never sold, only opened from a job

    def test_only_the_administrator(self):
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertNotEqual(self.client.get(reverse("work_types")).status_code, 200)
