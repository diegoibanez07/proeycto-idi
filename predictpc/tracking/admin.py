from django.contrib import admin

from .models import (
    Equipo, EventoHistorial, Hallazgo, IntervencionElectronica, Lote,
    RegistroTriage1, RegistroTriage2, RegistroTriage3, Remision, VerificacionPeriferico,
)


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "fecha_creacion")
    search_fields = ("codigo",)


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ("id_equipo", "lote", "serial", "etapa", "estado", "fecha_ingreso")
    list_filter = ("etapa", "estado", "lote")
    search_fields = ("id_equipo", "serial")


@admin.register(Hallazgo)
class HallazgoAdmin(admin.ModelAdmin):
    list_display = ("equipo", "origen", "tipo", "estado", "fecha")
    list_filter = ("origen", "tipo", "estado")


@admin.register(Remision)
class RemisionAdmin(admin.ModelAdmin):
    list_display = ("id", "equipo", "etapa_origen", "estado", "fecha")
    list_filter = ("estado", "etapa_origen")


admin.site.register(RegistroTriage1)
admin.site.register(RegistroTriage2)
admin.site.register(VerificacionPeriferico)
admin.site.register(RegistroTriage3)
admin.site.register(IntervencionElectronica)
admin.site.register(EventoHistorial)
