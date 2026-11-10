"""The navigation tabs each profile sees. Runs for every page."""
from django.utils.translation import gettext_lazy as _

# tab key -> (name of the page it opens, label, icon)
TABS = {
    "today": ("home", _("Today"), "today"),
    "opps": ("opps", _("Opportunities"), "opps"),
    "jobs": ("jobs", _("Jobs"), "jobs"),
    "accounts": ("accounts", _("Accounts"), "accounts"),
    "search": ("search", _("Search"), "search"),
    "admin": ("imports", _("Admin"), "admin"),
    "my_jobs": ("my_jobs", _("My Jobs"), "my_jobs"),
}
# which tab is highlighted for each page
TAB_OF_PAGE = {
    "home": "today", "search": "search", "my_jobs": "my_jobs",
    "accounts": "accounts", "account": "accounts", "account_new": "accounts", "account_edit": "accounts",
    "contact_new": "accounts", "contact_edit": "accounts", "property_new": "accounts", "property_edit": "accounts", "note_new": "accounts",
    "opps": "opps", "opp": "opps", "opp_new": "opps", "opp_inspection": "opps", "opp_proposal": "opps", "opp_sign": "opps", "opp_lost": "opps",
    "jobs": "jobs", "job": "jobs", "job_schedule": "jobs", "job_ref": "jobs", "job_warranty": "jobs",
    "imports": "admin", "import_queue": "admin", "import_note": "admin",
}


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    if user.is_crew_profile:
        keys = ["my_jobs", "search"]
    else:
        keys = ["today", "opps", "jobs", "accounts", "search"] + (["admin"] if user.is_admin_profile else [])
    page = request.resolver_match.url_name if request.resolver_match else ""
    active = TAB_OF_PAGE.get(page, "")
    if user.is_crew_profile and active == "jobs":
        active = "my_jobs"
    tabs = [{"key": k, "url": TABS[k][0], "label": TABS[k][1], "icon": TABS[k][2], "active": k == active} for k in keys]
    # phones show up to five tabs; with more, the fifth is "More"
    first, more = (tabs[:4], tabs[4:]) if len(tabs) > 5 else (tabs, [])
    return {"nav_tabs": tabs, "nav_first": first, "nav_more": more, "nav_more_active": any(t["active"] for t in more)}
