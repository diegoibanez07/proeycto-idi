from django import template

register = template.Library()

_ESTADO_CLASE = {
    "EN_PROCESO": "text-bg-primary-subtle text-primary-emphasis",
    "PENDIENTE_INTERVENCION": "text-bg-warning-subtle text-warning-emphasis",
    "DEMORADO": "text-bg-danger-subtle text-danger-emphasis",
    "FINALIZADO": "text-bg-success-subtle text-success-emphasis",
    "PENDIENTE": "text-bg-warning-subtle text-warning-emphasis",
    "RESUELTA": "text-bg-success-subtle text-success-emphasis",
    "CONFORME": "text-bg-success-subtle text-success-emphasis",
    "FALLA": "text-bg-danger-subtle text-danger-emphasis",
    "ABIERTA": "text-bg-warning-subtle text-warning-emphasis",
}


@register.filter
def badge_clase(valor):
    return _ESTADO_CLASE.get(valor, "text-bg-secondary-subtle")


@register.filter
def duracion_legible(delta):
    total_min = int(delta.total_seconds() // 60)
    horas, minutos = divmod(total_min, 60)
    if horas:
        return f"{horas} h {minutos:02d} min"
    return f"{minutos} min"
