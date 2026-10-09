from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import services
from .forms import (
    EquipoIngresoForm, IntervencionElectronicaForm, PeriféricoFormSet,
    RemisionForm, Triage1EncendidoForm, Triage1SOForm, Triage2MantenimientoForm,
    Triage3ReconstruccionForm,
)
from .models import (
    Equipo, EventoHistorial, Hallazgo, Remision, RegistroTriage1, RegistroTriage2,
    RegistroTriage3, VerificacionPeriferico,
)


# --------------------------------------------------------------------------- P01
@login_required
def bandeja_equipos(request):
    """P01 · HU01, HU16, HU17: punto de entrada con búsqueda y filtros por etapa/estado."""
    equipos = Equipo.objects.select_related("lote").all()

    q = request.GET.get("q", "").strip()
    etapa = request.GET.get("etapa", "")
    estado = request.GET.get("estado", "")
    if q:
        equipos = equipos.filter(id_equipo__icontains=q)
    if etapa:
        equipos = equipos.filter(etapa=etapa)
    if estado:
        equipos = equipos.filter(estado=estado)

    contadores = {c.label: Equipo.objects.filter(etapa=c.value).count() for c in [
        Equipo.Etapa.INGRESO, Equipo.Etapa.TRIAGE_1, Equipo.Etapa.TRIAGE_2,
        Equipo.Etapa.TRIAGE_3, Equipo.Etapa.ELECTRONICA,
    ]}
    for e in equipos:
        e.demorado = services.esta_demorado(e)

    return render(request, "tracking/p01_bandeja.html", {
        "equipos": equipos, "contadores": contadores, "q": q,
        "etapa_sel": etapa, "estado_sel": estado, "etapas": Equipo.Etapa.choices,
        "estados": Equipo.Estado.choices,
    })


# --------------------------------------------------------------------------- P02
@login_required
def registrar_equipo(request):
    """P02 · HU01: crea la ficha única y abre el evento de ingreso."""
    if request.method == "POST":
        form = EquipoIngresoForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                equipo = form.save(usuario=request.user)
                services.ingresar_equipo(equipo, request.user)
            messages.success(request, f"Equipo {equipo.id_equipo} registrado. Continúe a Triage 1.")
            return redirect("tracking:triage1_encendido", pk=equipo.pk)
    else:
        form = EquipoIngresoForm(initial={"fecha_ingreso": timezone.now()})
    return render(request, "tracking/p02_registro.html", {"form": form})


# --------------------------------------------------------------------------- P03
@login_required
def ficha_equipo(request, pk):
    """P03 · HU01, HU09, HU16, HU17: vista central de navegación del equipo."""
    equipo = get_object_or_404(Equipo, pk=pk)
    triage1 = getattr(equipo, "triage1", None)
    hallazgos = equipo.hallazgos.select_related("registrado_por").all()
    return render(request, "tracking/p03_ficha.html", {
        "equipo": equipo, "triage1": triage1, "hallazgos": hallazgos,
        "demorado": services.esta_demorado(equipo),
        "remisiones": equipo.remisiones.all()[:1],
    })


# --------------------------------------------------------------------------- P04 / P05
@login_required
def triage1_encendido(request, pk):
    """P04 · Paso 1 — HU02, HU03."""
    equipo = get_object_or_404(Equipo, pk=pk)
    instancia = getattr(equipo, "triage1", None)
    if request.method == "POST":
        form = Triage1EncendidoForm(request.POST, instance=instancia)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.equipo = equipo
            registro.tecnico = request.user
            registro.save()
            if not (registro.procesador_conforme and registro.ram_conforme and registro.almacenamiento_conforme):
                services.crear_hallazgo(
                    equipo, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.CONFIGURACION,
                    form.cleaned_data.get("diferencia_descripcion") or "Diferencia de configuración detectada.",
                    request.user,
                )
            equipo.cambiar_etapa(Equipo.Etapa.TRIAGE_1)
            services.registrar_evento(
                equipo, Equipo.Etapa.TRIAGE_1, "Triage 1",
                f"Encendido: {registro.get_resultado_encendido_display()}.", tecnico=request.user,
            )
            return redirect("tracking:triage1_so", pk=equipo.pk)
    else:
        form = Triage1EncendidoForm(instance=instancia, initial={
            "ram_encontrada_gb": equipo.ram_esperada_gb,
            "almacenamiento_tipo_encontrado": equipo.almacenamiento_tipo_esperado,
            "almacenamiento_gb_encontrado": equipo.almacenamiento_gb_esperado,
        })
    return render(request, "tracking/p04_triage1_encendido.html", {"equipo": equipo, "form": form})


@login_required
def triage1_so(request, pk):
    """P05 · Paso 2 — HU04, HU05: SO, controladores y excepción de BIOS bloqueada."""
    equipo = get_object_or_404(Equipo, pk=pk)
    instancia = getattr(equipo, "triage1", None)
    if instancia is None:
        messages.warning(request, "Registre primero el encendido y la configuración (paso 1).")
        return redirect("tracking:triage1_encendido", pk=equipo.pk)

    if request.method == "POST":
        form = Triage1SOForm(request.POST, instance=instancia)
        if form.is_valid():
            registro = form.save()
            if registro.bios_bloqueada:
                hallazgo = services.crear_hallazgo(
                    equipo, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.BIOS, "BIOS bloqueada", request.user,
                )
                services.crear_remision(
                    equipo, hallazgo, "BIOS bloqueada", form.cleaned_data.get("evidencia_bios", ""),
                    request.user, Equipo.Etapa.TRIAGE_1,
                )
                messages.success(request, "Se generó la remisión a Electrónica por BIOS bloqueada.")
                return redirect("tracking:ficha_equipo", pk=equipo.pk)
            else:
                services.registrar_evento(
                    equipo, Equipo.Etapa.TRIAGE_1, "Triage 1",
                    "SO y controladores instalados. Configuración verificada.", tecnico=request.user,
                )
                messages.success(request, "Triage 1 completado.")
                equipo.cambiar_etapa(Equipo.Etapa.TRIAGE_2)
                return redirect("tracking:triage2", pk=equipo.pk)
    else:
        form = Triage1SOForm(instance=instancia)
    return render(request, "tracking/p05_triage1_so.html", {"equipo": equipo, "form": form})


# --------------------------------------------------------------------------- P06
@login_required
def triage2(request, pk):
    """P06 · HU06, HU07: mantenimiento preventivo y verificación de periféricos."""
    equipo = get_object_or_404(Equipo, pk=pk)
    registro, _ = RegistroTriage2.objects.get_or_create(equipo=equipo, defaults={"tecnico": request.user})
    if not registro.verificaciones.exists():
        for elemento, _label in VerificacionPeriferico.Elemento.choices:
            VerificacionPeriferico.objects.create(triage2=registro, elemento=elemento, resultado=VerificacionPeriferico.Resultado.CONFORME)

    if request.method == "POST":
        mform = Triage2MantenimientoForm(request.POST, instance=registro)
        formset = PeriféricoFormSet(request.POST, queryset=registro.verificaciones.all())
        if mform.is_valid() and formset.is_valid():
            mform.save()
            fallas = []
            for f in formset:
                v = f.save()
                if v.resultado == VerificacionPeriferico.Resultado.FALLA:
                    fallas.append(v)
            for v in fallas:
                services.crear_hallazgo(
                    equipo, Hallazgo.Origen.TRIAGE_2, Hallazgo.Tipo.PERIFERICO,
                    f"{v.get_elemento_display()}: {v.observacion or 'falla registrada'}", request.user,
                )
            services.registrar_evento(
                equipo, Equipo.Etapa.TRIAGE_2, "Triage 2",
                f"Mantenimiento y pruebas funcionales completados. Fallas registradas: {len(fallas)}.",
                tecnico=request.user,
            )
            equipo.cambiar_etapa(Equipo.Etapa.TRIAGE_3)
            return redirect("tracking:triage3", pk=equipo.pk)
    else:
        mform = Triage2MantenimientoForm(instance=registro)
        formset = PeriféricoFormSet(queryset=registro.verificaciones.all())

    return render(request, "tracking/p06_triage2.html", {
        "equipo": equipo, "mform": mform, "formset": formset,
        "total": formset.total_form_count(),
    })


# --------------------------------------------------------------------------- P07
@login_required
def triage3(request, pk):
    """P07 · HU09, HU10, HU14, HU15: consulta de hallazgos previos y reconstrucción."""
    equipo = get_object_or_404(Equipo, pk=pk)
    hallazgos = equipo.hallazgos.all()

    if request.method == "POST":
        form = Triage3ReconstruccionForm(request.POST, equipo=equipo)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.equipo = equipo
            registro.tecnico = request.user
            registro.save()
            if registro.validacion_posterior == RegistroTriage3.Validacion.CORREGIDA:
                registro.hallazgo.marcar_resuelta()
                services.registrar_evento(
                    equipo, Equipo.Etapa.TRIAGE_3, "Triage 3",
                    f"Reconstrucción: {registro.actividad_realizada}. Falla corregida.", tecnico=request.user,
                )
            else:
                services.crear_remision(
                    equipo, registro.hallazgo, registro.actividad_realizada,
                    "Continúa pendiente tras reconstrucción en Triage 3.", request.user, Equipo.Etapa.TRIAGE_3,
                )
                return redirect("tracking:ficha_equipo", pk=equipo.pk)
            if not equipo.hallazgos_pendientes().exists():
                equipo.cambiar_etapa(Equipo.Etapa.VALIDACION, Equipo.Estado.FINALIZADO)
                messages.success(request, "Triage 3 finalizado: todos los hallazgos están resueltos.")
                return redirect("tracking:historial", pk=equipo.pk)
            return redirect("tracking:triage3", pk=equipo.pk)
    else:
        form = Triage3ReconstruccionForm(equipo=equipo)

    return render(request, "tracking/p07_triage3.html", {
        "equipo": equipo, "hallazgos": hallazgos, "form": form,
        "pendientes": equipo.hallazgos_pendientes().count(),
    })


# --------------------------------------------------------------------------- P08
@login_required
def electronica(request, remision_id):
    """P08 · HU11, HU12: recibir remisión, intervenir y devolver al flujo."""
    remision = get_object_or_404(Remision.objects.select_related("equipo", "hallazgo"), pk=remision_id)
    equipo = remision.equipo
    instancia = getattr(remision, "intervencion", None)

    if request.method == "POST":
        form = IntervencionElectronicaForm(request.POST, instance=instancia)
        if form.is_valid():
            intervencion = form.save(commit=False)
            intervencion.remision = remision
            intervencion.tecnico = request.user
            intervencion.save()
            services.resolver_intervencion(intervencion, request.user)
            messages.success(request, f"Equipo {equipo.id_equipo} devuelto a {intervencion.get_etapa_retorno_display()}.")
            return redirect("tracking:ficha_equipo", pk=equipo.pk)
    else:
        form = IntervencionElectronicaForm(instance=instancia, initial={
            "diagnostico": remision.motivo, "etapa_retorno": remision.etapa_origen,
        })

    antecedentes = equipo.historial.all()
    return render(request, "tracking/p08_electronica.html", {
        "remision": remision, "equipo": equipo, "form": form, "antecedentes": antecedentes,
    })


@login_required
def remisiones_pendientes(request):
    """Bandeja auxiliar de Electrónica: lista remisiones abiertas para abrir P08."""
    remisiones = Remision.objects.filter(estado=Remision.Estado.ABIERTA).select_related("equipo", "hallazgo")
    return render(request, "tracking/remisiones_pendientes.html", {"remisiones": remisiones})


# --------------------------------------------------------------------------- P09
@login_required
def historial(request, pk):
    """P09 · HU16: línea de tiempo cronológica con filtros."""
    equipo = get_object_or_404(Equipo, pk=pk)
    eventos = equipo.historial.select_related("tecnico").all()

    etapa = request.GET.get("etapa", "")
    tecnico = request.GET.get("tecnico", "")
    if etapa:
        eventos = eventos.filter(etapa=etapa)
    if tecnico:
        eventos = eventos.filter(tecnico_id=tecnico)

    return render(request, "tracking/p09_historial.html", {
        "equipo": equipo, "eventos": eventos, "etapas": Equipo.Etapa.choices,
    })


# --------------------------------------------------------------------------- P10
@login_required
def panel_supervisor(request):
    """P10 · HU17, HU18: indicadores, tiempos por etapa y equipos demorados."""
    import json
    equipos = Equipo.objects.all()
    datos = services.panel_indicadores(equipos)
    return render(request, "tracking/p10_panel.html", {
        "datos": datos, "equipos": equipos,
        "chart_etapa_json": json.dumps({
            "labels": [k.label for k in datos["por_etapa"]],
            "valores": list(datos["por_etapa"].values()),
        }),
        "chart_tiempo_json": json.dumps({
            "labels": [k.label for k in datos["tiempo_promedio"]],
            "valores": list(datos["tiempo_promedio"].values()),
        }),
    })
