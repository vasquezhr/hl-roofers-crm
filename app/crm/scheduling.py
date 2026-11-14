"""
The schedule: who is where on which day, and suggested times.

Work days are WORK_WEEKDAYS in the settings (WORK_DAYS in .env). For H & L: Monday to Friday.
Saturdays are never offered, and Sunday is not decided yet.

Distances are rough on purpose. Each address is placed at the middle of its ZIP code, using the
"zipcodes" library, which needs no internet and sends nothing anywhere. That is enough to tell
"near that day's other stops" from "across town". An address with no ZIP code has no distance.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from urllib.parse import quote

import zipcodes
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from .dates import range_text
from .models import Job, Opportunity, digits

INSPECTION_HOURS = range(9, 17)         # a one-hour inspection can start at 9 am ... 4 pm
FAR = 40                                # miles assumed when a distance is not known, so known-near days rank first
SUGGESTIONS = 4                         # how many suggested times to show
ON_SCHEDULE = [Job.Stage.SCHEDULED, Job.Stage.IN_PROGRESS, Job.Stage.DONE, Job.Stage.INVOICED, Job.Stage.PAID]


# ---------------------------------------------------------------- days
def is_work_day(day):
    return day.weekday() in settings.WORK_WEEKDAYS


def work_day(n, start=None):
    """n work days after `start` (today when not given). If `start` is a day off, counting begins on the next work day."""
    day = start or timezone.localdate()
    while not is_work_day(day):
        day += timedelta(days=1)
    step, left = (-1 if n < 0 else 1), abs(n)
    while left:
        day += timedelta(days=step)
        if is_work_day(day):
            left -= 1
    return day


def week(offset=0):
    """The five work days shown on the schedule: offset 0 starts today, 1 is the five after that."""
    return [work_day(offset * 5 + i) for i in range(5)]


def calendar_days(offset=0):
    """The seven days on the Schedule calendar, every day of the week, days off included: offset 0 starts today, 1 is the seven after that."""
    first = timezone.localdate() + timedelta(days=7 * offset)
    return [first + timedelta(days=i) for i in range(7)]


# ---------------------------------------------------------------- distance
@lru_cache(maxsize=2000)
def zip_point(zip_code):
    """(latitude, longitude) of the middle of a ZIP code, or None."""
    try:
        found = zipcodes.matching(zip_code[:5])
    except (TypeError, ValueError):
        return None
    return (float(found[0]["lat"]), float(found[0]["long"])) if found else None


def point_of(place):
    return zip_point(place.zip_code) if place and place.zip_code else None


def miles(a, b):
    """Rough driving miles between two properties: straight-line miles and a quarter more. None when either has no ZIP."""
    a, b = point_of(a), point_of(b)
    if not a or not b:
        return None
    lat1, lng1, lat2, lng2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return round(2 * 3958.8 * asin(sqrt(h)) * 1.25, 1)


# ---------------------------------------------------------------- stops
@dataclass
class Stop:
    """One thing on the schedule on one day: an inspection at a time, or a job a crew is on."""
    kind: str                       # "inspection" or "job"
    record: object                  # the Opportunity or the Job
    day: object
    starts: object = None           # for an inspection: the time it starts

    @property
    def place(self):
        return self.record.place

    @property
    def account(self):
        return self.record.account

    @property
    def hour(self):
        return self.starts.hour if self.starts else 0

    def overlaps(self, hour):
        """True when this one-hour inspection takes any part of the hour that starts at `hour`."""
        return self.starts is not None and abs(self.starts.hour * 60 + self.starts.minute - hour * 60) < 60

    @property
    def day_number(self):
        return self.record.day_number(self.day) if self.kind == "job" else 0


def stops_between(first, last, crew=None):
    """Every stop from `first` to `last`: {day: [stops]}. With `crew`, only that crew's jobs."""
    days = {}
    jobs = (Job.objects.filter(starts_on__lte=last, last_day__gte=first, stage__in=ON_SCHEDULE, crew__isnull=False)
            .select_related("account", "place", "crew").prefetch_related("change_orders", "payments", "workers"))
    for job in jobs.filter(crew=crew) if crew else jobs:
        for day in job.work_days:
            if first <= day <= last:
                days.setdefault(day, []).append(Stop("job", job, day))
    if not crew:
        zone = timezone.get_current_timezone()
        start, end = datetime.combine(first, time.min, tzinfo=zone), datetime.combine(last, time.max, tzinfo=zone)
        for opp in (Opportunity.objects.filter(stage=Opportunity.Stage.INSPECTION, inspection_at__range=(start, end))
                    .select_related("account", "place")):
            at = timezone.localtime(opp.inspection_at)
            days.setdefault(at.date(), []).append(Stop("inspection", opp, at.date(), at.time().replace(second=0, microsecond=0)))
    for stops in days.values():
        stops.sort(key=lambda stop: (stop.kind == "job", stop.starts or time.min, stop.record.pk))       # inspections first, by time
    return days


def nearest(place, stops):
    """The stop closest to a place: (miles, stop), or None when no distance is known."""
    known = [(miles(place, stop.place), stop) for stop in stops]
    known = [(distance, stop) for distance, stop in known if distance is not None]
    return min(known, key=lambda pair: pair[0]) if known else None


# ---------------------------------------------------------------- suggested times
def inspection_suggestions(opp):
    """The best hour on each of the next six work days, nearest days first: up to four of them.

    A day ranks by how close this visit is to that day's nearest other stop, then by soonest.
    Within a day, the hour next to that nearest inspection is preferred. An hour already taken by
    another inspection is never offered."""
    first, last = work_day(1), work_day(6)
    booked = stops_between(first, last)
    choices = []
    day = first
    while day <= last:
        others = [stop for stop in booked.get(day, []) if stop.record != opp]
        near = nearest(opp.place, others)
        near_hour = near[1].hour if near and near[1].kind == "inspection" else INSPECTION_HOURS[0]
        for hour in INSPECTION_HOURS:
            if not any(stop.overlaps(hour) for stop in others):
                choices.append({"day": day, "hour": hour, "time": time(hour, 0), "near": near, "has_stops": bool(others),
                                "score": near[0] if near else FAR, "gap": abs(hour - near_hour)})
        day = work_day(1, day)
    choices.sort(key=lambda c: (c["score"], c["day"], c["gap"], c["hour"]))
    best, seen = [], set()
    for choice in choices:
        if choice["day"] not in seen:
            seen.add(choice["day"])
            best.append(choice)
    return best[:SUGGESTIONS]


def crew_days(crew, first, last, but=None):
    """The days a crew already has a job on, from `first` to `last`: {day: job}. `but` is a job to leave out."""
    busy = {}
    for job in Job.objects.filter(crew=crew, starts_on__lte=last, last_day__gte=first, stage__in=ON_SCHEDULE).select_related("account", "place"):
        if job != but:
            for day in job.work_days:
                busy.setdefault(day, job)
    return busy


def job_suggestions(job, crew, length=None):
    """The next start days when the crew is free for the whole job: up to four, within the next three weeks.
    Each says where the crew is the day before, so a job can follow one that is close by."""
    length = max(1, length or job.days)
    busy = crew_days(crew, work_day(0), work_day(15 + length), but=job)
    found = []
    for k in range(1, 16):
        days = [work_day(k + i) for i in range(length)]
        if any(day in busy for day in days):
            continue
        before = busy.get(work_day(k - 1))
        found.append({"days": days, "first": days[0], "last": days[-1], "before": before, "miles": miles(job.place, before.place) if before else None})
        if len(found) == SUGGESTIONS:
            break
    return found


# ---------------------------------------------------------------- telling the crew about a change
def notify_href(job, company):
    """A link that opens Messages with the text for the crew lead, ready to send. Empty when the crew has no phone."""
    if not (job.crew and job.crew.phone):
        return ""
    text = _("%(company)s: job #%(number)s (%(name)s) changed. Now: %(now)s. Before: %(was)s. Please tap Got it in the app.") % {
        "company": company.name, "number": job.number, "name": job.account.name,
        "now": range_text(job.first_day, job.last_day), "was": range_text(job.was_first_day, job.was_last_day)}
    return "sms:" + digits(job.crew.phone) + "&body=" + quote(text)


# ---------------------------------------------------------------- the small map
def mini_map(place, stops, width=320, height=150):
    """Where a new visit is next to that day's other stops, as points for a small drawing.
    Returns None when there is nothing to draw (no ZIP codes). The points are whole numbers, so a page
    in Spanish does not write them with a decimal comma, which a drawing cannot read."""
    here = point_of(place)
    others = [(point_of(stop.place), stop) for stop in stops]
    others = [(point, stop) for point, stop in others if point]
    if not here or not others:
        return None
    lats, lngs = [here[0]] + [p[0] for p, _stop in others], [here[1]] + [p[1] for p, _stop in others]
    pad = 0.03
    low_lat, high_lat, low_lng, high_lng = min(lats) - pad, max(lats) + pad, min(lngs) - pad, max(lngs) + pad

    def spot(point):
        x = (point[1] - low_lng) / ((high_lng - low_lng) or 1) * (width - 110) + 15
        y = height - ((point[0] - low_lat) / ((high_lat - low_lat) or 1) * (height - 30) + 15)
        return round(x), round(y)

    x, y = spot(here)
    return {"width": width, "height": height, "x": x, "y": y,
            "stops": [{"x": spot(point)[0], "y": spot(point)[1], "label": stop.account.name.split(" ")[0]} for point, stop in others]}
