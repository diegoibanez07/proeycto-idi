from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Equipo, IntervencionElectronica, Lote, RegistroTriage1, RegistroTriage2,
    RegistroTriage3, VerificacionPeriferico,
)

WIDGET_INPUT = "form-control"
WIDGET_SELECT = "form-select"


def _w(widget_cls, css=WIDGET_INPUT, **attrs):
    attrs.setdefault("class", css)
    return widget_cls(attrs=attrs)


class EquipoIngresoForm(forms.ModelForm):
    """Pantalla P02 — HU01."""

    lote_codigo = forms.CharField(label="Lote *", widget=_w(forms.TextInput, placeholder="L-014"))

    class Meta:
        model = Equipo
        fields = [
            "serial", "tipo", "marca", "modelo", "fecha_ingreso",
            "proc_esperado", "ram_esperada_gb", "almacenamiento_tipo_esperado",
            "almacenamiento_gb_esperado", "so_esperado", "observaciones_ingreso",
        ]
        widgets = {
            "serial": _w(forms.TextInput),
            "tipo": _w(forms.Select, WIDGET_SELECT),
            "marca": _w(forms.TextInput),
            "modelo": _w(forms.TextInput),
            "fecha_ingreso": _w(forms.DateTimeInput, type="datetime-local"),
            "proc_esperado": _w(forms.TextInput),
            "ram_esperada_gb": _w(forms.NumberInput),
            "almacenamiento_tipo_esperado": _w(forms.Select, WIDGET_SELECT),
            "almacenamiento_gb_esperado": _w(forms.NumberInput),
            "so_esperado": _w(forms.TextInput),
            "observaciones_ingreso": _w(forms.Textarea, rows=3),
        }

    def clean_lote_codigo(self):
        return self.cleaned_data["lote_codigo"].strip().upper()

    def save(self, commit=True, usuario=None):
        equipo = super().save(commit=False)
        lote, _ = Lote.objects.get_or_create(codigo=self.cleaned_data["lote_codigo"])
        equipo.lote = lote
        equipo.creado_por = usuario
        if commit:
            equipo.save()
        return equipo


class Triage1EncendidoForm(forms.ModelForm):
    """Paso 1 de P04 — HU02, HU03."""

    class Meta:
        model = RegistroTriage1
        fields = [
            "resultado_encendido", "observacion_encendido",
            "ram_encontrada_gb", "almacenamiento_tipo_encontrado", "almacenamiento_gb_encontrado",
            "procesador_conforme", "ram_conforme", "almacenamiento_conforme",
        ]
        widgets = {
            "resultado_encendido": forms.RadioSelect,
            "observacion_encendido": _w(forms.TextInput, placeholder="Observación (opcional)"),
            "ram_encontrada_gb": _w(forms.NumberInput),
            "almacenamiento_tipo_encontrado": _w(forms.Select, WIDGET_SELECT),
            "almacenamiento_gb_encontrado": _w(forms.NumberInput),
            "procesador_conforme": _w(forms.CheckboxInput, "form-check-input"),
            "ram_conforme": _w(forms.CheckboxInput, "form-check-input"),
            "almacenamiento_conforme": _w(forms.CheckboxInput, "form-check-input"),
        }

    diferencia_descripcion = forms.CharField(
        required=False, label="Descripción de la diferencia",
        widget=_w(forms.Textarea, rows=2, placeholder="Obligatoria si hay alguna diferencia"),
    )

    def clean(self):
        cleaned = super().clean()
        hay_diferencia = not all([
            cleaned.get("procesador_conforme", True),
            cleaned.get("ram_conforme", True),
            cleaned.get("almacenamiento_conforme", True),
        ])
        if hay_diferencia and not cleaned.get("diferencia_descripcion"):
            raise ValidationError(
                "Describa la diferencia encontrada: es obligatoria cuando algún "
                "componente no es conforme con la especificación del proveedor (criterio HU03)."
            )
        return cleaned


class Triage1SOForm(forms.ModelForm):
    """Paso 2 de P05 — HU04, HU05."""

    class Meta:
        model = RegistroTriage1
        fields = [
            "so_instalado", "imagen_version",
            "drivers_video", "drivers_audio", "drivers_red", "drivers_chipset",
            "drivers_bluetooth", "drivers_huellas", "observaciones_so", "bios_bloqueada",
        ]
        widgets = {
            "so_instalado": _w(forms.TextInput),
            "imagen_version": _w(forms.TextInput),
            "observaciones_so": _w(forms.Textarea, rows=2),
            "drivers_video": _w(forms.CheckboxInput, "form-check-input"),
            "drivers_audio": _w(forms.CheckboxInput, "form-check-input"),
            "drivers_red": _w(forms.CheckboxInput, "form-check-input"),
            "drivers_chipset": _w(forms.CheckboxInput, "form-check-input"),
            "drivers_bluetooth": _w(forms.CheckboxInput, "form-check-input"),
            "drivers_huellas": _w(forms.CheckboxInput, "form-check-input"),
            "bios_bloqueada": _w(forms.CheckboxInput, "form-check-input"),
        }

    evidencia_bios = forms.CharField(
        required=False, label="Evidencia (nota, referencia de foto)",
        widget=_w(forms.TextInput, placeholder="Descripción de la foto o nota adjunta"),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("bios_bloqueada") and not cleaned.get("evidencia_bios"):
            raise ValidationError(
                "Adjunte una nota de evidencia: es obligatoria al remitir por BIOS bloqueada (criterio HU05)."
            )
        return cleaned


class Triage2MantenimientoForm(forms.ModelForm):
    class Meta:
        model = RegistroTriage2
        fields = ["limpieza_interna", "ventiladores", "pasta_termica", "limpieza_teclado"]
        widgets = {f: _w(forms.CheckboxInput, "form-check-input") for f in
                   ["limpieza_interna", "ventiladores", "pasta_termica", "limpieza_teclado"]}


PeriféricoFormSet = forms.modelformset_factory(
    VerificacionPeriferico,
    fields=["elemento", "resultado", "observacion"],
    widgets={
        "elemento": forms.HiddenInput,
        "resultado": forms.RadioSelect,
        "observacion": _w(forms.TextInput, placeholder="Obligatoria si el resultado es Falla"),
    },
    extra=0,
)


class Triage3ReconstruccionForm(forms.ModelForm):
    class Meta:
        model = RegistroTriage3
        fields = [
            "hallazgo", "actividad_realizada", "detalle", "validacion_posterior",
            "decision_criterio", "decision_autoria_visible",
        ]
        widgets = {
            "hallazgo": _w(forms.Select, WIDGET_SELECT),
            "actividad_realizada": _w(forms.TextInput),
            "detalle": _w(forms.Textarea, rows=2),
            "validacion_posterior": forms.RadioSelect,
            "decision_criterio": _w(forms.Textarea, rows=2,
                                     placeholder="Opcional: hallazgo · criterio · acción · resultado"),
            "decision_autoria_visible": _w(forms.CheckboxInput, "form-check-input"),
        }

    def __init__(self, *args, equipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if equipo is not None:
            self.fields["hallazgo"].queryset = equipo.hallazgos_pendientes()


class RemisionForm(forms.Form):
    """Se usa desde P05 (BIOS) y P03 (remitir manualmente) — HU05, HU11."""
    motivo = forms.CharField(widget=_w(forms.TextInput))
    evidencia_nota = forms.CharField(required=False, widget=_w(forms.Textarea, rows=2))
    evidencia_archivo = forms.FileField(required=False)


class IntervencionElectronicaForm(forms.ModelForm):
    """Pantalla P08 — HU12."""

    class Meta:
        model = IntervencionElectronica
        fields = [
            "diagnostico", "intervencion_realizada", "archivo_bin",
            "verificada", "observaciones", "etapa_retorno",
        ]
        widgets = {
            "diagnostico": _w(forms.TextInput),
            "intervencion_realizada": _w(forms.TextInput),
            "archivo_bin": _w(forms.TextInput, placeholder="bios_modelo_v1.bin"),
            "verificada": forms.RadioSelect(choices=[(True, "Sí"), (False, "No")]),
            "observaciones": _w(forms.Textarea, rows=2),
            "etapa_retorno": _w(forms.Select, WIDGET_SELECT),
        }
