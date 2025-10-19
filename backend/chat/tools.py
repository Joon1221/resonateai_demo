from dataclasses import dataclass
from datetime import timedelta
from typing import List, Dict, Any, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from appointments.models import (
    Patient, Family, FamilyMember, Availability, Appointment, StaffAlert
)
from scheduling.fuzzy import parse_fuzzy_date_range
import re


PHONE_DIGITS = re.compile(r"\D+")

def _norm_phone(p: str) -> str:
    return PHONE_DIGITS.sub("", (p or "").strip())

def _find_patient_by_name_phone(name: str, phone: str) -> Optional[Patient]:
    if not name or not phone:
        return None
    phone_norm = _norm_phone(phone)
    # Try exact digits match; allow "+1" leading
    qs = Patient.objects.filter(full_name__iexact=name.strip())
    for p in qs:
        p_phone = _norm_phone(p.phone)
        if p_phone == phone_norm or p_phone.endswith(phone_norm):
            return p
    return None

def verify_patient(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { "name": str, "phone": str }
    Returns: { ok: bool, patient_id?: int, error?: "patient_not_found" }
    """
    name = params.get("name", "")
    phone = params.get("phone", "")
    p = _find_patient_by_name_phone(name, phone)
    if not p:
        return {"ok": False, "error": "patient_not_found"}
    return {"ok": True, "patient_id": p.id, "name": p.full_name, "phone": p.phone}


def list_appointments(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params:
      Either:
        {"patient_id": int, "date_range": optional str, "include_past": optional bool, "limit": optional int}
      Or:
        {"name": str, "phone": str, "date_range": optional str, "include_past": optional bool, "limit": optional int}

    Behavior:
      - If date_range provided (e.g., "next week", "this month"), filter by that range.
      - Else, default to upcoming (now -> +60 days).
      - Returns only BOOKED by default.
    """
    limit = int(params.get("limit", 10))
    include_past = bool(params.get("include_past", False))

    patient: Optional[Patient] = None
    if "patient_id" in params:
        patient = Patient.objects.filter(id=params["patient_id"]).first()
    else:
        name, phone = params.get("name", ""), params.get("phone", "")
        patient = _find_patient_by_name_phone(name, phone)

    if not patient:
        return {"ok": False, "error": "patient_not_found"}

    # Time window
    if "date_range" in params and isinstance(params["date_range"], str) and params["date_range"].strip():
        start, end = parse_fuzzy_date_range(params["date_range"])
    else:
        start = timezone.now()
        end = start + timezone.timedelta(days=60)

    qs = Appointment.objects.filter(patient=patient, status=Appointment.Status.BOOKED)
    if not include_past:
        qs = qs.filter(end__gte=timezone.now())

    # Apply window
    qs = qs.filter(start__lt=end, end__gt=start).order_by("start")

    items = []
    for appt in qs[:limit]:
        items.append({
            "appointment_id": appt.id,
            "type": appt.type,
            "start": appt.start.isoformat(),
            "end": appt.end.isoformat(),
            "notes": appt.notes or "",
        })

    return {
        "ok": True,
        "patient": {"user_id": patient.id, "name": patient.full_name, "phone": patient.phone},
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "appointments": items,
    }

def _get_or_create_patient(info: Dict[str, Any]) -> Patient:
    """
    info: {"full_name": str, "phone": str, "dob": "YYYY-MM-DD" (optional), "insurance_name": optional}
    """
    name = info.get("full_name") or info.get("name")
    phone = info.get("phone")
    dob = info.get("dob")
    qs = Patient.objects.filter(full_name__iexact=name.strip(), phone=phone.strip())
    if dob:
        qs = qs.filter(dob=dob)
    p = qs.first()
    if p:
        # update insurance if provided
        if info.get("insurance_name") and not p.insurance_name:
            p.insurance_name = info["insurance_name"]
            p.save(update_fields=["insurance_name"])
        return p
    return Patient.objects.create(
        full_name=name.strip(),
        phone=phone.strip(),
        dob=dob or timezone.now().date(),   
        insurance_name=info.get("insurance_name"),
    )


def _slot_duration_minutes(start, end) -> int:
    return int((end - start).total_seconds() // 60)

def find_slots(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { "type": "cleaning"|"checkup"|"filling"|"emergency",
              "date_range": "tomorrow morning" | "next week" | ...,
              "count": int=3,
              "family_members": [names]? (optional)
            }
    """
    appt_type = params["type"]
    phrase = params.get("date_range", "next 14 days")
    # count = int(params.get("count", 100))
    start, end = parse_fuzzy_date_range(phrase)

    qs = (
        Availability.objects
        .filter(appointment_type=appt_type, start__gte=start, end__lte=end)
        .order_by("start")
    )
    slots = list(qs.values("id", "start", "end"))

    return {
        "ok": True,
        "type": appt_type,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "slots": slots,
    }


@transaction.atomic
def book_appointment(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { "patient_info": {...}, "type": "...", "start": ISO8601, "notes": optional }
    """
    patient = _get_or_create_patient(params["patient_info"])
    appt_type = params["type"]
    start = timezone.make_aware(timezone.datetime.fromisoformat(params["start"].replace("Z","")))
    # find a matching availability slot with same start
    slot = Availability.objects.filter(appointment_type=appt_type, start=start).order_by("start").first()
    print(slot)
    if not slot:
        # try nearest within +/−30m
        near = Availability.objects.filter(
            appointment_type=appt_type,
            start__gte=start - timezone.timedelta(minutes=30),
            start__lte=start + timezone.timedelta(minutes=30),
        ).order_by("start").first()
        if not near:
            return {"ok": False, "error": "slot_not_available"}

        slot = near

    appt = Appointment.objects.create(
        patient=patient,
        type=appt_type,
        start=slot.start,
        end=slot.end,
        notes=params.get("notes"),
    )
    # consumptive model: delete the slot so it can't be rebooked
    slot.delete()
    return {"ok": True, "appointment_id": appt.id, "start": appt.start.isoformat(), "end": appt.end.isoformat()}


@transaction.atomic
def reschedule_appointment(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { "appointment_id": int, "new_start": ISO8601 }
    """
    appt = Appointment.objects.select_for_update().get(id=params["appointment_id"])
    new_start = timezone.make_aware(timezone.datetime.fromisoformat(params["new_start"].replace("Z","")))
    duration = _slot_duration_minutes(appt.start, appt.end)
    # look for availability matching type + new_start (+same duration)
    slot = Availability.objects.filter(
        appointment_type=appt.type,
        start=new_start,
        end=new_start + timezone.timedelta(minutes=duration),
    ).first()
    if not slot:
        return {"ok": False, "error": "no_matching_slot"}

    # free the old time (optional): create a new availability from old appt
    Availability.objects.create(start=appt.start, end=appt.end, appointment_type=appt.type)

    # update appt and consume the new slot
    appt.start, appt.end = slot.start, slot.end

    # update appointment in DB and refresh instance
    Appointment.objects.filter(id=appt.id).update(start=slot.start, end=slot.end)
    appt.refresh_from_db()

    # consume the slot
    slot.delete()

    return {"ok": True, "appointment_id": appt.id, "start": appt.start.isoformat(), "end": appt.end.isoformat()}


def cancel_appointment(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { "appointment_id": int }
    """
    appt = Appointment.objects.filter(id=params["appointment_id"]).first()
    if not appt:
        return {"ok": False, "error": "not_found"}
    appt.status = Appointment.Status.CANCELED
    appt.save(update_fields=["status"])

    # optionally release the slot back to availability
    Availability.objects.create(start=appt.start, end=appt.end, appointment_type=appt.type)

    return {"ok": True}


def create_staff_alert(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { "summary": str, "appointment_id": optional int }
    """
    alert = StaffAlert.objects.create(
        appointment_id=params.get("appointment_id"),
        kind=StaffAlert.Kind.EMERGENCY,
        summary=params["summary"][:2000],
    )
    return {"ok": True, "alert_id": alert.id}
