"""What every page needs: the navigation tabs for the person's profile, and the business's name and look."""
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from . import look
from .dates import days_off_text, work_days_text
from .models import Company

# tab key -> (name of the page it opens, label, icon)
TABS = {
    "dashboard": ("dashboard", _("Dashboard"), "dashboard"),
    "today": ("home", _("Today"), "today"),
    "leads": ("leads", _("Leads"), "leads"),
    "opps": ("opps", _("Opportunities"), "opps"),
    "jobs": ("jobs", _("Jobs"), "jobs"),
    "schedule": ("schedule", _("Schedule"), "schedule"),
    "accounts": ("accounts", _("Accounts"), "accounts"),
    "search": ("search", _("Search"), "search"),
    "reports": ("reports", _("Reports"), "reports"),
    "admin": ("admin_home", _("Admin"), "admin"),
    "prices": ("pricebook", _("Price Book"), "dollar"),
    "editor": ("editor", _("Data editor"), "edit"),
    "my_day": ("my_day", _("My Day"), "my_day"),
    "my_jobs": ("my_jobs", _("My Jobs"), "my_jobs"),
}
# every tab, in order, and the tick that shows it (permissions.py). A login sees the tabs its profile and permission sets allow.
NAV = [("dashboard", "dashboard"), ("today", "today"), ("my_day", "my_day"), ("my_jobs", "my_day"), ("leads", "lead.see"),
       ("opps", "opportunity.see"), ("jobs", "job.see"), ("schedule", "schedule"), ("accounts", "account.see"), ("search", "search"),
       ("reports", "reports"), ("admin", "admin")]
# the cards of the Admin hub (Admin > ...), each with its tick. The Price Book and the Data editor are cards there too; a login without
# the Admin tab that may open one of them gets a tab of its own.
ADMIN_TICKS = ["users", "company", "setup", "setup_history", "status", "import_data", "export_data", "admin_site", "purge"]


def opens_admin(user):
    """True when the login may open the Admin hub: it has one of the Admin pages besides the Price Book and the Data editor."""
    return any(user.can(tick) for tick in ADMIN_TICKS)
# which tab is highlighted: a page's name starts with one of these
TAB_BY_PAGE = [
    ("home", "today"), ("dashboard", "dashboard"), ("lead", "leads"), ("opp", "opps"), ("proposal", "opps"),
    ("job", "jobs"), ("change_order", "jobs"), ("payment", "jobs"), ("invoice", "jobs"), ("worker", "jobs"),
    ("schedule", "schedule"), ("book", "schedule"),
    ("account", "accounts"), ("contact", "accounts"), ("property", "accounts"), ("note", "accounts"),
    ("search", "search"), ("report", "reports"), ("my_day", "my_day"), ("my_jobs", "my_jobs"),
    ("admin", "admin"), ("import", "admin"), ("price", "admin"), ("company", "admin"), ("automation", "admin"),
    ("user", "admin"), ("pick", "admin"), ("data", "admin"), ("editor", "admin"), ("status", "admin"), ("recycle", "admin"), ("bin", "admin"),
]


def exists(page):
    """True when a page with this name has been built."""
    try:
        reverse(page)
        return True
    except NoReverseMatch:
        return False


def company(request):
    """The business's name and details, for the top bar and the documents, and its colors and icon (look.py)."""
    firm = Company.load()
    return {"company": firm, "look": look.of(firm), "week": {"work": work_days_text(), "off": days_off_text()}}


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    admin = opens_admin(user)
    keys = [key for key, tick in NAV if (admin if tick == "admin" else user.can(tick)) and exists(TABS[key][0])
            and not (key == "jobs" and user.is_crew_login)]                # a crew login lists its jobs on My Jobs
    if not admin and (user.can("price_book") or user.can("costs.see")):
        keys.append("prices")                                       # a permission set gives the office its own Price Book tab
    if not admin and user.can("data_editor"):
        keys.append("editor")
    page = request.resolver_match.url_name if request.resolver_match else ""
    active = next((tab for start, tab in TAB_BY_PAGE if page and page.startswith(start)), "")
    if active == "admin" and "admin" not in keys:
        active = "prices" if page.startswith("price") else "editor" if page.startswith("editor") else ""
    if user.is_crew_login and active == "jobs":
        active = "my_jobs"
    tabs = [{"key": k, "url": TABS[k][0], "label": TABS[k][1], "icon": TABS[k][2], "active": k == active} for k in keys]
    # phones show up to five tabs; with more, the fifth is "More"
    first, more = (tabs[:4], tabs[4:]) if len(tabs) > 5 else (tabs, [])
    return {"nav_tabs": tabs, "nav_first": first, "nav_more": more, "nav_more_active": any(t["active"] for t in more)}
