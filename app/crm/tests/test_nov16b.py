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
