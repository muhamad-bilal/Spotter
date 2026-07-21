from django.urls import path

from . import views

urlpatterns = [
    path("trips/", views.create_trip, name="create-trip"),
    path("trips/<int:pk>/", views.retrieve_trip, name="retrieve-trip"),
]
