"""Persisted trips, so every result has a shareable id.

These mirror the engine's dataclasses rather than replacing them: the engine still
computes in pure Python, and this layer only records what it produced.
"""

from django.db import models

STOP_KINDS = [
    ("start", "Start"),
    ("pickup", "Pickup"),
    ("dropoff", "Dropoff"),
    ("fuel", "Fuel"),
    ("break_30", "30-minute break"),
    ("rest_10", "10-hour rest"),
    ("restart_34", "34-hour restart"),
]

DUTY_STATUSES = [
    ("off_duty", "Off duty"),
    ("sleeper", "Sleeper berth"),
    ("driving", "Driving"),
    ("on_duty", "On duty (not driving)"),
]


class Trip(models.Model):
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used = models.FloatField(help_text="Hours already used in the 70/8 cycle")

    total_distance_miles = models.FloatField()
    total_drive_hours = models.FloatField(help_text="HOS basis: distance / 55 mph")
    total_days = models.IntegerField()
    cycle_hours_remaining = models.FloatField()

    provider_eta_hours = models.FloatField(
        null=True,
        blank=True,
        help_text="Routing provider's own estimate. Display only -- never used for HOS.",
    )
    provider_eta_source = models.CharField(
        max_length=64,
        blank=True,
        help_text=(
            "Which provider and profile produced the route, e.g. 'Geoapify truck'. "
            "Stored rather than derived so an old trip keeps reporting the provider "
            "that actually served it."
        ),
    )

    # Not in the reference model list, but without it a saved trip cannot
    # reproduce its own payload: the map needs the route line back.
    geometry = models.JSONField(default=list, help_text="[[lat, lng], ...] polyline")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.pickup_location} -> {self.dropoff_location} "
            f"({self.total_distance_miles:.0f} mi)"
        )


class RouteStop(models.Model):
    trip = models.ForeignKey(Trip, related_name="stops", on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, choices=STOP_KINDS)
    label = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    arrive_at = models.DateTimeField()
    depart_at = models.DateTimeField()
    sequence = models.IntegerField()

    class Meta:
        ordering = ["sequence"]


class LogDay(models.Model):
    trip = models.ForeignKey(Trip, related_name="logs", on_delete=models.CASCADE)
    date = models.DateField()
    total_off_duty = models.FloatField()
    total_sleeper = models.FloatField()
    total_driving = models.FloatField()
    total_on_duty = models.FloatField()
    total_miles = models.FloatField()

    class Meta:
        ordering = ["date"]


class DutySegment(models.Model):
    log_day = models.ForeignKey(LogDay, related_name="segments", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=DUTY_STATUSES)
    start_minute = models.IntegerField(help_text="Minutes from midnight, 0-1440")
    end_minute = models.IntegerField(help_text="Minutes from midnight, 0-1440")
    remark = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["start_minute"]
