"""
Who may open what.

Every page asks the login's ticks (permissions.py): its profile's, plus its permission sets'. The checks run on the server for every
page, so a login cannot reach a page by typing its address, and a section it may not see is left out of the page itself.

  @needs("lead.see")              an everyday page. Refused: a crew login is sent to My Day, its own first page; anyone else gets "not allowed"
  @with_permission("users")       an Admin page or an action. Refused: "not allowed". With several ticks, any one of them opens it
  @may_edit("job")                an Edit page: needs("job.edit")
  job_or_404(user, number)        a job this login may see; a crew login with "Only jobs scheduled to their crew" only reaches its crew's jobs
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect

from .models import Activity, Job


def refuse(request):
    """A page this login may not open. A crew login goes to My Day, as before; anyone else is told it is not allowed."""
    if request.user.is_crew_login:
        return redirect("my_day")
    raise PermissionDenied


def needs(*ticks):
    """An everyday page for a login with every one of these ticks: @needs("account.see")"""
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not all(request.user.can(tick) for tick in ticks):
                return refuse(request)
            return view(request, *args, **kwargs)
        return wrapper
    return decorate


def with_permission(*ticks):
    """An Admin page or an action, for a login with one of these ticks: @with_permission("price_book", "costs.see")"""
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not any(request.user.can(tick) for tick in ticks):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorate


def may_edit(what):
    """An Edit page, for a login whose profile may edit this kind of record: @may_edit("job")"""
    return needs(f"{what}.edit")


def jobs_for(user):
    """The jobs this login may see: none without See for jobs; with "Only jobs scheduled to their crew", only its crew's; else every job."""
    jobs = Job.objects.select_related("account", "place", "crew", "opportunity").prefetch_related("change_orders", "payments")
    if not user.can("job.see"):
        return jobs.none()
    if user.can("own_jobs"):
        return jobs.filter(crew=user.crew) if user.crew_id else jobs.none()
    return jobs


def job_or_404(user, number):
    """A job by its number, or 'not found' when this login may not see it."""
    try:
        return jobs_for(user).get(number=number)
    except Job.DoesNotExist:
        raise Http404


def unread_notes(user, job=None):
    """The notes the office wrote on this crew's jobs that the crew has not tapped Got it on yet, newest first (the pop-up on
    My Day, My Jobs and the job). Empty for anyone but a crew. A note written before Nov 16, 2026 is not one (for_crew is False)."""
    if not (user.is_crew_login and user.can("job_notes.see")):
        return []
    jobs = jobs_for(user) if job is None else jobs_for(user).filter(pk=job.pk)
    return list(Activity.objects.filter(kind="note", for_crew=True, read_at__isnull=True, job__in=jobs.values("pk"))
                .select_related("job__account").order_by("-at", "-id"))
