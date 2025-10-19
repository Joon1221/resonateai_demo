from datetime import datetime, time, timedelta
from typing import Iterable, Optional
from django.utils import timezone
from django.db import transaction
from appointments.models import Availability, Appointment
from django.core.management.base import BaseCommand

OPEN_HOUR = 8
CLOSE_HOUR = 18
SLOT_MINUTES = 30
OPEN_WEEKDAYS = {0,1,2,3,4,5}  # Mon..Sat (0=Mon, 6=Sun)

DEFAULT_TYPES = (
    Availability.ApptType.CLEANING,
    Availability.ApptType.CHECKUP,
    Availability.ApptType.FILLING,
)

def _dt(day, hh, mm=0):
    # combine a date with a local time, timezone-aware
    dt = datetime.combine(day.date(), time(hh, mm))
    return timezone.make_aware(dt)

def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return not (a_end <= b_start or b_end <= a_start)

@transaction.atomic
def generate_availability_window(
    start_dt: Optional[datetime] = None,
    days: int = 14,
    slot_minutes: int = SLOT_MINUTES,
    appt_types: Iterable[str] = DEFAULT_TYPES,
    skip_if_exists: bool = True,
) -> int:
    """
    Create availability slots in a rolling window, skipping Sundays and
    skipping any slot that overlaps an existing Appointment.
    Returns number of slots created.
    """
    tz_now = timezone.now()
    start_dt = start_dt or tz_now
    # normalize to start-of-day
    start_day = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    created = 0
    for d in range(days):
        print("Generating day", d)
        print("created so far", created)
        day = start_day + timedelta(days=d)
        if day.weekday() not in OPEN_WEEKDAYS:
            continue

        day_open = _dt(day, OPEN_HOUR)
        day_close = _dt(day, CLOSE_HOUR)

        # Preload appointments for the day to avoid overlaps
        day_appts = list(
            Appointment.objects.filter(
                start__lt=day_close, end__gt=day_open, status=Appointment.Status.BOOKED
            ).values_list("start", "end")
        )

        t = day_open
        while t + timedelta(minutes=slot_minutes) <= day_close:
            slot_start = t
            slot_end = t + timedelta(minutes=slot_minutes)

            # Skip if an appointment overlaps this time
            if any(_overlaps(slot_start, slot_end, a0, a1) for (a0, a1) in day_appts):
                t = slot_end
                continue

            # Optionally skip if we already have a slot at this time/type
            if skip_if_exists and Availability.objects.filter(start=slot_start, end=slot_end).exists():
                t = slot_end
                continue

            # Create one slot per type (or just one if you prefer)
            for appt_type in appt_types:
                Availability.objects.create(
                    start=slot_start,
                    end=slot_end,
                    appointment_type=appt_type,
                )
                created += 1

            t = slot_end

    return created

class Command(BaseCommand):
    help = "Generate availability (default next 14 days). Skips Sundays and overlaps with existing appointments."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14, help="How many days ahead to generate.")
        parser.add_argument("--from", dest="from_iso", type=str, default=None, help="Start ISO datetime (optional).")

    def handle(self, *args, **opts):
        start = timezone.now()
        if opts.get("from_iso"):
            start = timezone.make_aware(timezone.datetime.fromisoformat(opts["from_iso"]))
        n = generate_availability_window(start_dt=start, days=opts["days"])
        self.stdout.write(self.style.SUCCESS(f"Created {n} availability slots."))
