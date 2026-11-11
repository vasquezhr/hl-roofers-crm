"""
Who may open what.

Three profiles: Admin, Office and Crew. A crew signs in with one shared login
and sees only the jobs scheduled to that crew. These checks run on the server
for every page, so a crew cannot reach an office page by typing its address.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect

from .models import Job


def office_only(view):
    """Pages for the Office and Admin profiles. A crew login is sent to its own first page."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_crew_profile:
            return redirect("my_jobs")
        return view(request, *args, **kwargs)
    return wrapper


def admin_only(view):
    """Pages for the administrator."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin_profile:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def jobs_for(user):
    """The jobs this login may see: every job for the office; only its own crew's jobs for a crew."""
    jobs = Job.objects.select_related("account", "place", "crew", "opportunity").prefetch_related("change_orders", "payments")
    if user.is_crew_profile:
        return jobs.filter(crew=user.crew) if user.crew_id else jobs.none()
    return jobs


def job_or_404(user, number):
    """A job by its number, or 'not found' when this login may not see it."""
    try:
        return jobs_for(user).get(number=number)
    except Job.DoesNotExist:
        raise Http404
