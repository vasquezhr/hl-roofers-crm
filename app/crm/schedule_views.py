"""
The schedule, the crew's My Day, changes to a scheduled job, extra workers and the calendar feed.

  /schedule/                 five work days at a time, a filter for each crew, and "Schedule a visit"
                             with suggested times
  /my-day/                   the crew's first page: today's stops, tomorrow's, and anything that changed
  /calendar/<word>.ics       a crew's (or the office's) jobs for the phone's own calendar app
"""
from datetime import date, datetime, time, timedelta
from datetime import timezone as world_clock

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import scheduling
from .access import job_or_404, jobs_for, office_only
from .history import booking_code, when_code
from .models import Company, Crew, Job, Opportunity, Worker, log
from .views import filter_pills, next_step, saved, today

TONES = ["primary", "success", "warning", "danger", "secondary"]        # one color for each crew, in order


def crew_tones():
    return {crew.pk: TONES[i % len(TONES)] for i, crew in enumerate(Crew.objects.filter(active=True))}


def feed_address(request, token):
    """The calendar address for a phone: webcal://… makes the iPhone offer to subscribe."""
    path = reverse("calendar_feed", args=[token]) + f"?lang={translation.get_language()}"
    return "webcal://" + request.get_host() + path


# ---------------------------------------------------------------- the week
@office_only
def schedule(request):
    offset = max(0, int(request.GET["week"])) if request.GET.get("week", "").isdigit() else 0
    show = request.GET.get("show", "all")
    days = scheduling.week(offset)
    booked = scheduling.stops_between(days[0], days[-1])
    crews = list(Crew.objects.filter(active=True))
    tones = crew_tones()

    def wanted(stop):
        if show == "all":
            return True
        if show == "inspections":
            return stop.kind == "inspection"
        return stop.kind == "job" and str(stop.record.crew_id) == show

    columns = [{"day": day, "is_today": day == today(),
                "stops": [{"stop": stop, "tone": "info" if stop.kind == "inspection" else tones.get(stop.record.crew_id, "secondary")}
                          for stop in booked.get(day, []) if wanted(stop)]} for day in days]
    return render(request, "crm/schedule.html", {
        "columns": columns, "offset": offset, "show": show, "first": days[0], "last": days[-1],
        "pills": filter_pills(show, [("all", _("All"), "")] + [(str(crew.pk), crew.name, "") for crew in crews] + [("inspections", _("Inspections"), "")]),
        "legend": [(tones[crew.pk], crew.name) for crew in crews],
        # the office's calendar address, and each crew's own, which the office can send to that crew
        "feeds": [{"label": _("Everything: every crew and the inspections"), "which": "office",
                   "address": feed_address(request, Company.load().calendar_token())}]
                 + [{"label": crew.name, "which": crew.pk, "address": feed_address(request, crew.calendar_token())} for crew in crews],
        **booking(request, crews),
    })


def booking(request, crews):
    """What the "Schedule a visit" box needs: everything waiting to be booked, the one chosen, and its suggested times."""
    waiting_opps = list(Opportunity.objects.filter(stage=Opportunity.Stage.INSPECTION).select_related("account", "place").order_by("created_at"))
    waiting_jobs = list(Job.objects.filter(stage=Job.Stage.SIGNED).select_related("account", "place").order_by("created_at"))
    chosen = request.GET.get("book", "")
    kind, _colon, number = chosen.partition(":")
    # an inspection that already has a time is only listed while its time is being changed
    opps = [opp for opp in waiting_opps if not opp.inspection_at or (kind == "opp" and opp.number == number)]
    record = next((r for r in (opps if kind == "opp" else waiting_jobs if kind == "job" else []) if r.number == number), None)
    if record is None:
        kind, record = ("opp", opps[0]) if opps else ("job", waiting_jobs[0]) if waiting_jobs else ("", None)
    out = {"book_opps": opps, "book_jobs": waiting_jobs, "book_kind": kind, "book": record, "crews": crews}
    if kind == "opp":
        suggestions = scheduling.inspection_suggestions(record)
        out["suggestions"] = suggestions
        if suggestions:
            best = suggestions[0]
            others = [stop for stop in scheduling.stops_between(best["day"], best["day"]).get(best["day"], []) if stop.record != record]
            out["map"] = scheduling.mini_map(record.place, others)
    elif kind == "job":
        crew = next((c for c in crews if str(c.pk) == request.GET.get("crew")), crews[0] if crews else None)
        length = job_length(request.GET.get("days"), record.days)
        out.update(book_crew=crew, book_days=length, day_choices=range(1, max(10, length) + 1),
                   suggestions=scheduling.job_suggestions(record, crew, length) if crew else [])
    return out


def job_length(typed, default):
    """How many work days a job gets: what was picked, from 1 to 60, or the job's own number."""
    return min(60, max(1, int(typed))) if str(typed or "").isdigit() else default


@office_only
@require_POST
def book(request):
    """Book a suggested time: an inspection gets its day and hour, a job gets its crew and days."""
    kind, number = request.POST.get("kind"), request.POST.get("number", "")
    try:
        day = date.fromisoformat(request.POST.get("day", ""))
    except ValueError:
        raise Http404
    if not scheduling.is_work_day(day):
        messages.warning(request, _("Pick a work day, Monday to Friday."))
        return redirect("schedule")
    if kind == "opp":
        opp = get_object_or_404(Opportunity, number=number, stage=Opportunity.Stage.INSPECTION)
        hour = int(request.POST.get("hour", "9")) if request.POST.get("hour", "").isdigit() else 9
        if hour not in scheduling.INSPECTION_HOURS:
            raise Http404
        opp.inspection_at = timezone.make_aware(datetime.combine(day, time(hour, 0)))
        opp.save()
        log(opp, "inspection_booked", request.user, detail=when_code(timezone.localtime(opp.inspection_at)))
        saved(request, _("Booked"))
        return redirect("opp", number=opp.number)
    if kind == "job":
        job = get_object_or_404(Job, number=number, stage=Job.Stage.SIGNED)
        job.crew = get_object_or_404(Crew, pk=request.POST.get("crew") or 0, active=True)
        job.first_day, job.stage = day, Job.Stage.SCHEDULED
        job.days = job_length(request.POST.get("days"), job.days)
        job.save()
        log(job, "booked", request.user, detail=booking_code(job))
        saved(request, _("Booked"))
        return redirect("job", number=job.number)
    raise Http404


# ---------------------------------------------------------------- changes to a scheduled job
@login_required
@require_POST
def job_seen(request, number):
    """The crew's "Got it" button on a job that was moved. The office then sees that the change was seen."""
    job = job_or_404(request.user, number)
    if request.user.is_crew_profile and job.change_unseen:
        job.seen_at = timezone.now()
        job.save()
        log(job, "got_it", request.user)
        saved(request, _("The office can see that you got it"))
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = reverse("job", args=[job.number])
    return redirect(back)


# ---------------------------------------------------------------- extra workers on a job
@login_required
@require_POST
def job_worker(request, number):
    """Add or take off an extra worker. The office or the job's crew can, until the job is done."""
    job = job_or_404(request.user, number)
    if not job.is_finished and job.crew_id:
        worker = get_object_or_404(Worker, pk=request.POST.get("worker") or 0, crew__isnull=True)
        if request.POST.get("do") == "remove":
            job.workers.remove(worker)
            log(job, "worker_removed", request.user, detail=worker.name)
        elif worker.active:
            job.workers.add(worker)
            log(job, "worker_added", request.user, detail=worker.name)
    return redirect("job", number=job.number)


# ---------------------------------------------------------------- the crew's My Day
@login_required
def my_day(request):
    """Today's stops for this crew, with everything needed on site; then the next work day, and any job that was moved."""
    if not request.user.is_crew_profile:
        return redirect("home")
    crew, day = request.user.crew, today()
    next_day = scheduling.work_day(1, day) if scheduling.is_work_day(day) else scheduling.work_day(0, day)
    booked = scheduling.stops_between(day, next_day, crew) if crew else {}
    # each of today's stops, with the buttons this crew may use on it
    stops = [{"stop": stop, "job": stop.record, "step": next_step(stop.record, request.user),
              "can_pay": stop.record.can_take_payment(request.user)} for stop in booked.get(day, [])]
    on_today = {item["job"].pk for item in stops}
    return render(request, "crm/my_day.html", {
        "crew": crew, "day": day, "next_day": next_day, "stops": stops,
        "next_jobs": [stop.record for stop in booked.get(next_day, [])],
        "members": crew.members.filter(active=True) if crew else [],
        "changes": [job for job in jobs_for(request.user).filter(changed_at__isnull=False, seen_at__isnull=True) if job.pk not in on_today],
        "feeds": [{"label": crew.name, "address": feed_address(request, crew.calendar_token())}] if crew else [],
    })


# ---------------------------------------------------------------- the calendar feed
@office_only
@require_POST
def calendar_reset(request):
    """Give a calendar a new address, for when the old one reached someone it should not have.
    The old address stops working at once, so every phone that used it must subscribe again."""
    which = request.POST.get("which", "")
    owner = Company.load() if which == "office" else get_object_or_404(Crew, pk=which if which.isdigit() else 0)
    owner.feed_token = ""
    owner.calendar_token()
    log(None, "calendar_reset", request.user, detail=owner.name)
    saved(request, _("The calendar has a new address. The old one no longer works."))
    return redirect(reverse("schedule") + "?calendars=1#calendars")


def ics_text(text):
    """Text made safe for a calendar file."""
    for mark in ("\\", ";", ","):
        text = str(text).replace(mark, "\\" + mark)
    return text.replace("\n", "\\n")


def fold(line):
    """A calendar file's lines are at most 75 bytes; longer ones continue on the next line after a space."""
    raw, out = line.encode("utf-8"), []
    while len(raw) > 73:
        cut = 73
        while raw[cut] & 0xC0 == 0x80:                                 # never cut a letter such as ñ in half
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def calendar_feed(request, token):
    """Jobs for the phone's own calendar. The long random word in the address is the key: a calendar app cannot sign in.
    The feed holds names, addresses and the type of work. It never holds prices or phone numbers."""
    company = Company.load()
    crew = Crew.objects.filter(feed_token=token).first()
    if not crew and company.feed_token != token:
        raise Http404
    with translation.override("es" if request.GET.get("lang") == "es" else "en"):
        first, last = today() - timedelta(days=30), today() + timedelta(days=180)
        stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//crm//schedule//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
                 "X-WR-CALNAME:" + ics_text(f"{company.name} · {crew.name if crew else _('Schedule')}")]
        for day, stops in sorted(scheduling.stops_between(first, last, crew).items()):
            for stop in stops:
                record, place = stop.record, stop.place
                lines += ["BEGIN:VEVENT", f"UID:{stop.kind}-{record.number}-{day:%Y%m%d}@{request.get_host()}", f"DTSTAMP:{stamp}"]
                if stop.kind == "inspection":
                    start = record.inspection_at.astimezone(world_clock.utc)        # calendar files give times on the world clock (UTC)
                    lines += [f"DTSTART:{start:%Y%m%dT%H%M%SZ}", f"DTEND:{start + timedelta(hours=1):%Y%m%dT%H%M%SZ}",
                              "SUMMARY:" + ics_text(f"{_('Inspection')}: {record.account.name}")]
                else:
                    part = f" ({stop.day_number}/{record.days})" if record.days > 1 else ""
                    who = "" if crew else f"{record.crew.name} · "
                    lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                              "SUMMARY:" + ics_text(f"{who}{record.account.name} · {record.get_job_type_display()}{part}")]
                lines += ["LOCATION:" + ics_text(place.full_address), "DESCRIPTION:" + ics_text(f"#{record.number}"), "END:VEVENT"]
        lines.append("END:VCALENDAR")
    response = HttpResponse("\r\n".join(fold(line) for line in lines) + "\r\n", content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="schedule.ics"'
    return response
