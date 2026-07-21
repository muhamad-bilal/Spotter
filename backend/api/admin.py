"""Admin registration, so a saved trip and its stops and log days are browsable.

Useful for demoing that the endpoint really persisted what it returned.
"""

from django.contrib import admin

from .models import DutySegment, LogDay, RouteStop, Trip


class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    fields = ["sequence", "kind", "label", "latitude", "longitude", "arrive_at", "depart_at"]


class LogDayInline(admin.TabularInline):
    model = LogDay
    extra = 0
    fields = ["date", "total_off_duty", "total_sleeper", "total_driving", "total_on_duty",
              "total_miles"]
    show_change_link = True


class DutySegmentInline(admin.TabularInline):
    model = DutySegment
    extra = 0
    fields = ["status", "start_minute", "end_minute", "remark"]


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "pickup_location",
        "dropoff_location",
        "total_distance_miles",
        "total_drive_hours",
        "total_days",
        "created_at",
    ]
    list_filter = ["created_at"]
    search_fields = ["current_location", "pickup_location", "dropoff_location"]
    readonly_fields = ["created_at"]
    inlines = [RouteStopInline, LogDayInline]


@admin.register(LogDay)
class LogDayAdmin(admin.ModelAdmin):
    list_display = ["id", "trip", "date", "total_driving", "total_miles"]
    list_filter = ["date"]
    inlines = [DutySegmentInline]


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ["id", "trip", "sequence", "kind", "label", "arrive_at"]
    list_filter = ["kind"]


@admin.register(DutySegment)
class DutySegmentAdmin(admin.ModelAdmin):
    list_display = ["id", "log_day", "status", "start_minute", "end_minute", "remark"]
    list_filter = ["status"]
