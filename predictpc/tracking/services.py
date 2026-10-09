"""
Reglas de negocio del flujo Triage -> Electrónica -> retorno.

Se centralizan aquí (y no en las vistas ni en los modelos) para que:
  - el registro de historial (HU16) nunca se olvide en una vista nueva.
  - las reglas "por confirmar" de la Fase 3 (umbral de demorado, retorno)
    tengan un único lugar de ajuste cuando el cliente las confirme.
"""
from datetime import timedelta

from django.utils import timezone

from .models import (
    Equipo, EventoHistorial, Hallazgo, Remision,
)

# Parámetro "por confirmar" (Fase 3, sección 7.4 / DD-11): umbral de demorado por etapa.
UMBRAL_DEMORADO_HORAS = {
    Equipo.Etapa.TRIAGE_1: 2,
    Equipo.Etapa.TRIAGE_2: 3,
    Equipo.Etapa.TRIAGE_3: 4,
    Equipo.Etapa.ELECTRONICA: 5,
}


def registrar_evento(equipo, etapa, tipo_evento, descripcion, tecnico=None, destacado=False):
    return EventoHistorial.objects.create(
        equipo=equipo, etapa=etapa, tipo_evento=tipo_evento,
        descripcion=descripcion, tecnico=tecnico, destacado=destacado,
    )


def ingresar_equipo(equipo, usuario):
    registrar_evento(
        equipo, Equipo.Etapa.INGRESO, "Ingreso",
        f"Equipo registrado en lote {equipo.lote.codigo}.", tecnico=usuario,
    )


def crear_hallazgo(equipo, origen, tipo, descripcion, usuario):
    hallazgo = Hallazgo.objects.create(
        equipo=equipo, origen=origen, tipo=tipo, descripcion=descripcion, registrado_por=usuario,
    )
    return hallazgo


def crear_remision(equipo, hallazgo, motivo, evidencia_nota, usuario, etapa_origen, archivo=None):
    remision = Remision.objects.create(
        equipo=equipo, hallazgo=hallazgo, etapa_origen=etapa_origen, motivo=motivo,
        evidencia_nota=evidencia_nota, remitido_por=usuario, evidencia_archivo=archivo,
    )
    equipo.cambiar_etapa(Equipo.Etapa.ELECTRONICA, Equipo.Estado.PENDIENTE_INTERVENCION)
    registrar_evento(
        equipo, etapa_origen, "Remisión",
        f"Hallazgo: {hallazgo.get_tipo_display()} → Remisión {remision_codigo(remision)} a Electrónica.",
        tecnico=usuario, destacado=True,
    )
    return remision


def remision_codigo(remision):
    return f"R-{remision.pk:04d}"


def resolver_intervencion(intervencion, usuario):
    """Cierra la remisión, marca el hallazgo como resuelto y devuelve el equipo al flujo (HU12)."""
    remision = intervencion.remision
    remision.estado = Remision.Estado.RESUELTA
    remision.save(update_fields=["estado"])
    remision.hallazgo.marcar_resuelta()

    equipo = remision.equipo
    equipo.cambiar_etapa(intervencion.etapa_retorno, Equipo.Estado.EN_PROCESO)

    registrar_evento(
        equipo, Equipo.Etapa.ELECTRONICA, "Electrónica",
        f"Acción: {intervencion.intervencion_realizada}"
        + (f" (archivo {intervencion.archivo_bin})" if intervencion.archivo_bin else "")
        + f" · Resultado: {'verificada' if intervencion.verificada else 'sin verificar'}.",
        tecnico=usuario, destacado=True,
    )
    registrar_evento(
        equipo, intervencion.etapa_retorno, "Retorno",
        f"Equipo retorna a {equipo.get_etapa_display()} para continuar el flujo.",
        tecnico=usuario, destacado=True,
    )
    return equipo


def esta_demorado(equipo):
    umbral = UMBRAL_DEMORADO_HORAS.get(equipo.etapa)
    if not umbral or equipo.estado == Equipo.Estado.FINALIZADO:
        return False
    return equipo.tiempo_en_etapa() >= timedelta(hours=umbral)


def panel_indicadores(queryset):
    """Datos agregados para P10: contadores por etapa y promedio de horas por etapa."""
    from django.utils.timezone import now

    por_etapa = {c: 0 for c in [Equipo.Etapa.INGRESO, Equipo.Etapa.TRIAGE_1, Equipo.Etapa.TRIAGE_2,
                                 Equipo.Etapa.TRIAGE_3, Equipo.Etapa.ELECTRONICA]}
    for e in queryset:
        if e.etapa in por_etapa:
            por_etapa[e.etapa] += 1

    demorados = [e for e in queryset if esta_demorado(e)]
    remisiones_abiertas = Remision.objects.filter(equipo__in=queryset, estado=Remision.Estado.ABIERTA).count()
    finalizados_hoy = queryset.filter(
        estado=Equipo.Estado.FINALIZADO, etapa_desde__date=now().date()
    ).count()

    tiempos = tiempo_promedio_por_etapa()

    return {
        "en_proceso": queryset.exclude(estado=Equipo.Estado.FINALIZADO).count(),
        "remisiones_abiertas": remisiones_abiertas,
        "demorados": demorados,
        "finalizados_hoy": finalizados_hoy,
        "por_etapa": por_etapa,
        "tiempo_promedio": tiempos,
    }


def tiempo_promedio_por_etapa():
    """
    Horas promedio que los equipos permanecen en cada etapa (HU18).
    Se calcula con la bitácora: la permanencia en una etapa va desde su primer
    evento hasta el siguiente evento de otra etapa (o hasta ahora si sigue ahí).
    """
    etapas = [Equipo.Etapa.TRIAGE_1, Equipo.Etapa.TRIAGE_2, Equipo.Etapa.TRIAGE_3, Equipo.Etapa.ELECTRONICA]
    duraciones = {e: [] for e in etapas}
    ahora = timezone.now()
    for equipo in Equipo.objects.prefetch_related("historial"):
        eventos = list(equipo.historial.all())
        for i, ev in enumerate(eventos):
            if ev.etapa not in duraciones or (i > 0 and eventos[i - 1].etapa == ev.etapa):
                continue
            fin = next((x.fecha for x in eventos[i + 1:] if x.etapa != ev.etapa), ahora)
            duraciones[ev.etapa].append((fin - ev.fecha).total_seconds() / 3600)
    return {e: round(sum(d) / len(d), 1) if d else 0 for e, d in duraciones.items()}
