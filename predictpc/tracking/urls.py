from django.urls import path

from . import views

app_name = "tracking"

urlpatterns = [
    path("", views.bandeja_equipos, name="bandeja"),  # P01
    path("equipos/nuevo/", views.registrar_equipo, name="registrar_equipo"),  # P02
    path("equipos/<int:pk>/", views.ficha_equipo, name="ficha_equipo"),  # P03
    path("equipos/<int:pk>/triage1/encendido/", views.triage1_encendido, name="triage1_encendido"),  # P04
    path("equipos/<int:pk>/triage1/so/", views.triage1_so, name="triage1_so"),  # P05
    path("equipos/<int:pk>/triage2/", views.triage2, name="triage2"),  # P06
    path("equipos/<int:pk>/triage3/", views.triage3, name="triage3"),  # P07
    path("remisiones/", views.remisiones_pendientes, name="remisiones_pendientes"),
    path("remisiones/<int:remision_id>/electronica/", views.electronica, name="electronica"),  # P08
    path("equipos/<int:pk>/historial/", views.historial, name="historial"),  # P09
    path("panel/", views.panel_supervisor, name="panel_supervisor"),  # P10
]
