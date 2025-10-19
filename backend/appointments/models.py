from django.db import models

class Patient(models.Model):
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    dob = models.DateField()
    insurance_name = models.CharField(max_length=120, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["phone"]),
            models.Index(fields=["full_name"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


class Family(models.Model):
    name = models.CharField(max_length=120)

    def __str__(self):
        return self.name


class FamilyMember(models.Model):
    class Relationship(models.TextChoices):
        SELF = "self", "Self"
        SPOUSE = "spouse", "Spouse"
        CHILD = "child", "Child"
        OTHER = "other", "Other"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="members")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="families")
    relationship = models.CharField(max_length=16, choices=Relationship.choices, default=Relationship.SELF)

    class Meta:
        unique_together = ("family", "patient")


class Availability(models.Model):
    class ApptType(models.TextChoices):
        CLEANING = "cleaning", "Cleaning"
        CHECKUP = "checkup", "Checkup"
        FILLING = "filling", "Filling"
        EMERGENCY = "emergency", "Emergency"

    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    appointment_type = models.CharField(max_length=24, choices=ApptType.choices)

    # optional: block out already-booked slots by removing/consuming availability
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["appointment_type", "start"]),
        ]


class Appointment(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        CANCELED = "canceled", "Canceled"
        COMPLETED = "completed", "Completed"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
    type = models.CharField(max_length=24, choices=Availability.ApptType.choices)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.BOOKED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["patient", "start"]),
        ]
        constraints = [
            # prevent double-booking same patient time window
            models.UniqueConstraint(fields=["patient", "start", "end"], name="uniq_patient_timeslot"),
        ]


class StaffAlert(models.Model):
    class Kind(models.TextChoices):
        EMERGENCY = "emergency", "Emergency"
        GENERAL = "general", "General"

    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.GENERAL)
    summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "created_at"])]
