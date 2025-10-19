from django.contrib import admin
from .models import Patient, Family, FamilyMember, Availability, Appointment, StaffAlert
admin.site.register([Patient, Family, FamilyMember, Availability, Appointment, StaffAlert])
