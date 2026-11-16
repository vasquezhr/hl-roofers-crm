"""The user's second message of Nov 16: the Recycle Bin's back link, the job page's buttons, the uncontacted lead reminder,
days off, the Rescheduled notice, reschedules with a reason, and the crew's pop-up for notes. Everything here is made up."""
from django.urls import reverse

from .base import Base


class RecycleBinBackLink(Base):
    def test_the_administrator_goes_back_to_admin(self):
        self.sign_in(self.admin)
        page = self.client.get(reverse("recycle_bin"))
        self.assertContains(page, f'href="{reverse("admin_home")}"')
        self.assertContains(page, "<span>Admin</span>")
        page = self.client.get(reverse("recycle_bin"), HTTP_REFERER="http://testserver" + reverse("admin_home"))
        self.assertContains(page, "<span>Admin</span>")

    def test_it_names_the_page_the_person_came_from(self):
        self.office.can_delete = True
        self.office.save()
        self.sign_in(self.office)
        page = self.client.get(reverse("recycle_bin"), HTTP_REFERER="http://testserver" + reverse("jobs"))
        self.assertContains(page, f'href="{reverse("jobs")}"')
        self.assertContains(page, "<span>Jobs</span>")
        page = self.client.get(reverse("recycle_bin"))                  # the office cannot open Admin: back to Today
        self.assertContains(page, "<span>Today</span>")
        self.assertNotContains(page, f'href="{reverse("admin_home")}"')


class LeadReminder(Base):
    """Item 8: after a whole day, the same assigned person is reminded again. Nobody else is alerted."""
    def setUp(self):
        from crm.models import Company
        self.office.email, self.admin.email = "office@example.com", "admin@example.com"
        self.office.save()
        self.admin.save()
        company = Company.load()
        company.lead_owner = self.office
        company.save()

    def test_only_the_assigned_person_is_emailed_twice(self):
        from datetime import timedelta

        from django.core import mail
        from django.utils import timezone

        from crm import automations
        from crm.models import Lead
        now = timezone.now()
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", owner=self.office, received_at=now - timedelta(days=2))
        automations.remind_about_leads(None, now)
        self.assertEqual([message.to for message in mail.outbox], [["office@example.com"], ["office@example.com"]])
        self.assertEqual(lead.activities.first().text, "Still new after a day: office was reminded again")
        automations.remind_about_leads(None, now + timedelta(days=1))
        self.assertEqual(len(mail.outbox), 2)                                # each email once
        # a request that went to the backup person before Nov 16 is not reminded a second time
        old = Lead.objects.create(name="Naomi Iturralde", owner=self.office, received_at=now - timedelta(days=2))
        from crm.models import log
        log(old, "auto_reminded", detail="office", actor="Automation")
        log(old, "auto_escalated", detail="admin", actor="Automation")
        automations.remind_about_leads(None, now)
        self.assertEqual(len(mail.outbox), 2)

    def test_the_backup_setting_is_gone(self):
        self.sign_in(self.admin)
        page = self.client.get(reverse("company_details"))
        self.assertNotContains(page, "lead_backup")
        self.assertNotContains(page, "also tell")
        page = self.client.get(reverse("automations"))
        self.assertContains(page, "After a whole day: emails that same person again. Nobody else is told.")
        self.assertNotContains(page, "backup person")
