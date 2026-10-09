"""
Modelos del núcleo MVP de PREDICT PC.

Cada modelo referencia, en su docstring, la(s) historia(s) de usuario del
Product Backlog de la Fase 2 que implementa. Esto mantiene la trazabilidad
HU -> modelo -> vista -> plantilla pedida en la Fase 3 (sección 12).
"""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Lote(models.Model):
    """Agrupa computadores que ingresan juntos (HU01)."""
    codigo = models.CharField(max_length=20, unique=True)
    fecha_creacion = models.DateTimeField(default=timezone.now)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return self.codigo


class Equipo(models.Model):
    """Ficha única del computador (HU01, HU16, HU17). Pantallas P02/P03."""

    class Etapa(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso"
        TRIAGE_1 = "TRIAGE_1", "Triage 1"
        TRIAGE_2 = "TRIAGE_2", "Triage 2"
        TRIAGE_3 = "TRIAGE_3", "Triage 3"
        ELECTRONICA = "ELECTRONICA", "Electrónica"
        VALIDACION = "VALIDACION", "Validación final"
        FINALIZADO = "FINALIZADO", "Finalizado"

    class Estado(models.TextChoices):
        EN_PROCESO = "EN_PROCESO", "En proceso"
        PENDIENTE_INTERVENCION = "PENDIENTE_INTERVENCION", "Pendiente de intervención"
        DEMORADO = "DEMORADO", "Demorado"
        FINALIZADO = "FINALIZADO", "Finalizado"

    class TipoEquipo(models.TextChoices):
        PORTATIL = "PORTATIL", "Portátil"
        ESCRITORIO = "ESCRITORIO", "Escritorio"
        TODO_EN_UNO = "TODO_EN_UNO", "Todo en uno"

    id_equipo = models.CharField(max_length=20, unique=True, editable=False)
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="equipos")
    serial = models.CharField(max_length=60)
    tipo = models.CharField(max_length=20, choices=TipoEquipo.choices, default=TipoEquipo.PORTATIL)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=60)
    fecha_ingreso = models.DateTimeField(default=timezone.now)
    observaciones_ingreso = models.TextField(blank=True)

    # Configuración esperada (especificación del proveedor) — HU03, solo lectura en Triage 1
    proc_esperado = models.CharField("Procesador esperado", max_length=80)
    ram_esperada_gb = models.PositiveIntegerField("RAM esperada (GB)")
    almacenamiento_tipo_esperado = models.CharField(max_length=10, choices=[("SSD", "SSD"), ("HDD", "HDD")])
    almacenamiento_gb_esperado = models.PositiveIntegerField("Capacidad esperada (GB)")
    so_esperado = models.CharField("SO esperado", max_length=60, blank=True)

    etapa = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.INGRESO)
    estado = models.CharField(max_length=30, choices=Estado.choices, default=Estado.EN_PROCESO)
    etapa_desde = models.DateTimeField(default=timezone.now)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="equipos_creados")

    class Meta:
        ordering = ["-fecha_ingreso"]

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.id_equipo:
            self.id_equipo = f"PC-{self.pk:06d}"
            Equipo.objects.filter(pk=self.pk).update(id_equipo=self.id_equipo)

    def __str__(self):
        return self.id_equipo or f"Equipo #{self.pk}"

    def get_absolute_url(self):
        return reverse("tracking:equipo_detalle", args=[self.pk])

    def cambiar_etapa(self, nueva_etapa, nuevo_estado=None):
        """Centraliza el cambio de etapa y reinicia el cronómetro de tiempo en etapa (HU17)."""
        self.etapa = nueva_etapa
        if nuevo_estado:
            self.estado = nuevo_estado
        self.etapa_desde = timezone.now()
        self.save(update_fields=["etapa", "estado", "etapa_desde"])

    def tiempo_en_etapa(self):
        return timezone.now() - self.etapa_desde

    def hallazgos_pendientes(self):
        return self.hallazgos.filter(estado=Hallazgo.Estado.PENDIENTE)


class Hallazgo(models.Model):
    """
    Unidad de trazabilidad de una novedad detectada en cualquier etapa
    (diferencia de configuración, falla de periférico, BIOS bloqueada...).
    Soporta HU03, HU05, HU07, HU09, HU10, HU11 y la ficha del equipo (HU16).
    """

    class Origen(models.TextChoices):
        TRIAGE_1 = "TRIAGE_1", "Triage 1"
        TRIAGE_2 = "TRIAGE_2", "Triage 2"
        TRIAGE_3 = "TRIAGE_3", "Triage 3"

    class Tipo(models.TextChoices):
        CONFIGURACION = "CONFIGURACION", "Diferencia de configuración"
        BIOS = "BIOS", "BIOS bloqueada"
        PERIFERICO = "PERIFERICO", "Periférico o puerto"
        ESTETICA = "ESTETICA", "Estética / pantalla"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        RESUELTA = "RESUELTA", "Resuelta"

    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="hallazgos")
    origen = models.CharField(max_length=20, choices=Origen.choices)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.CharField(max_length=255)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.equipo.id_equipo} · {self.get_tipo_display()}"

    def marcar_resuelta(self):
        self.estado = Hallazgo.Estado.RESUELTA
        self.save(update_fields=["estado"])


class RegistroTriage1(models.Model):
    """Encendido, contraste de configuración, SO y controladores (HU02, HU03, HU04)."""

    class Encendido(models.TextChoices):
        ENCIENDE = "ENCIENDE", "Enciende"
        NO_ENCIENDE = "NO_ENCIENDE", "No enciende"
        NOVEDAD = "NOVEDAD", "Enciende con novedad"

    equipo = models.OneToOneField(Equipo, on_delete=models.CASCADE, related_name="triage1")
    resultado_encendido = models.CharField(max_length=15, choices=Encendido.choices)
    observacion_encendido = models.CharField(max_length=255, blank=True)

    ram_encontrada_gb = models.PositiveIntegerField(null=True, blank=True)
    almacenamiento_tipo_encontrado = models.CharField(max_length=10, choices=[("SSD", "SSD"), ("HDD", "HDD")], blank=True)
    almacenamiento_gb_encontrado = models.PositiveIntegerField(null=True, blank=True)
    procesador_conforme = models.BooleanField(default=True)
    ram_conforme = models.BooleanField(default=True)
    almacenamiento_conforme = models.BooleanField(default=True)

    so_instalado = models.CharField(max_length=60, blank=True)
    imagen_version = models.CharField(max_length=60, blank=True)
    drivers_video = models.BooleanField(default=False)
    drivers_audio = models.BooleanField(default=False)
    drivers_red = models.BooleanField(default=False)
    drivers_chipset = models.BooleanField(default=False)
    drivers_bluetooth = models.BooleanField(default=False)
    drivers_huellas = models.BooleanField(default=False)
    observaciones_so = models.TextField(blank=True)

    bios_bloqueada = models.BooleanField(default=False)
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Triage 1 · {self.equipo.id_equipo}"


class RegistroTriage2(models.Model):
    """Mantenimiento preventivo y verificación individual de periféricos (HU06, HU07)."""
    equipo = models.OneToOneField(Equipo, on_delete=models.CASCADE, related_name="triage2")
    limpieza_interna = models.BooleanField(default=False)
    ventiladores = models.BooleanField(default=False)
    pasta_termica = models.BooleanField(default=False)
    limpieza_teclado = models.BooleanField(default=False)
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Triage 2 · {self.equipo.id_equipo}"


class VerificacionPeriferico(models.Model):
    """Una fila por elemento verificado en Triage 2 (criterio de HU07: registro individual)."""

    class Elemento(models.TextChoices):
        TECLADO = "TECLADO", "Teclado"
        TOUCHPAD = "TOUCHPAD", "Touchpad"
        CAMARA = "CAMARA", "Cámara"
        AUDIO = "AUDIO", "Audio"
        USB = "USB", "USB"
        HDMI = "HDMI", "HDMI"
        CARGA = "CARGA", "Carga"

    class Resultado(models.TextChoices):
        CONFORME = "CONFORME", "Conforme"
        FALLA = "FALLA", "Falla"

    triage2 = models.ForeignKey(RegistroTriage2, on_delete=models.CASCADE, related_name="verificaciones")
    elemento = models.CharField(max_length=15, choices=Elemento.choices)
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("triage2", "elemento")

    def __str__(self):
        return f"{self.elemento} · {self.resultado}"


class RegistroTriage3(models.Model):
    """Reconstrucción y revalidación de hallazgos previos (HU09, HU10)."""

    class Validacion(models.TextChoices):
        CORREGIDA = "CORREGIDA", "Falla corregida"
        PENDIENTE = "PENDIENTE", "Continúa pendiente"

    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="registros_triage3")
    hallazgo = models.ForeignKey(Hallazgo, on_delete=models.CASCADE, related_name="reconstrucciones")
    actividad_realizada = models.CharField(max_length=255)
    detalle = models.TextField(blank=True)
    validacion_posterior = models.CharField(max_length=15, choices=Validacion.choices)
    # HU14 / HU15: decisión técnica, opcional, autoría voluntaria (protección del conocimiento individual)
    decision_criterio = models.TextField(blank=True)
    decision_autoria_visible = models.BooleanField(default=False)
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Triage 3 · {self.equipo.id_equipo} · {self.hallazgo.get_tipo_display()}"


class Remision(models.Model):
    """Remisión a Electrónica (u otra área) con motivo y evidencia (HU05, HU11)."""

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        RESUELTA = "RESUELTA", "Resuelta"

    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="remisiones")
    hallazgo = models.ForeignKey(Hallazgo, on_delete=models.CASCADE, related_name="remisiones")
    etapa_origen = models.CharField(max_length=20, choices=Equipo.Etapa.choices)
    motivo = models.CharField(max_length=255)
    evidencia_nota = models.TextField(blank=True)
    evidencia_archivo = models.FileField(upload_to="evidencias/", blank=True, null=True)
    remitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="remisiones_hechas")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"R-{self.pk:04d} · {self.equipo.id_equipo}"


class IntervencionElectronica(models.Model):
    """Diagnóstico, intervención y retorno al flujo (HU12). Pantalla P08."""
    remision = models.OneToOneField(Remision, on_delete=models.CASCADE, related_name="intervencion")
    diagnostico = models.CharField(max_length=255)
    intervencion_realizada = models.CharField(max_length=255)
    archivo_bin = models.CharField("Archivo .bin utilizado", max_length=120, blank=True)
    verificada = models.BooleanField("¿Reprogramación / intervención verificada?", default=False)
    observaciones = models.TextField(blank=True)
    etapa_retorno = models.CharField(max_length=20, choices=Equipo.Etapa.choices)
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Intervención · {self.remision}"


class EventoHistorial(models.Model):
    """
    Bitácora cronológica append-only del equipo (HU16, HU17).
    Se alimenta automáticamente desde cada vista que registra un paso del flujo,
    para que nunca quede un evento sin registrar.
    """
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="historial")
    etapa = models.CharField(max_length=20, choices=Equipo.Etapa.choices)
    tipo_evento = models.CharField(max_length=30)  # Ingreso, Triage 1, Remisión, Electrónica, Retorno...
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    descripcion = models.CharField(max_length=500)
    destacado = models.BooleanField(default=False)  # remisiones y retornos se resaltan en P09
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha:%d/%m %H:%M} · {self.equipo.id_equipo} · {self.tipo_evento}"
