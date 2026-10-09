"""
Carga usuarios y equipos de ejemplo, incluido el caso demostrable acordado
en la Fase 2 y usado en las pruebas de usabilidad de la Fase 3:
ingreso -> Triage 1 -> BIOS bloqueada -> Electrónica (.bin) -> retorno ->
Triage 2 -> Triage 3 -> historial y panel.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from tracking import services
from tracking.models import (
    Equipo, EventoHistorial, Hallazgo, IntervencionElectronica, Lote, RegistroTriage1,
    RegistroTriage2, RegistroTriage3, VerificacionPeriferico,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Crea usuarios y equipos de demostración para PREDICT PC."

    def handle(self, *args, **options):
        self.stdout.write("Creando usuarios…")
        tecnico1, _ = User.objects.get_or_create(username="tecnico1", defaults={"first_name": "Técnico", "last_name": "A"})
        tecnico2, _ = User.objects.get_or_create(username="tecnico2", defaults={"first_name": "Técnico", "last_name": "B"})
        tecnico3, _ = User.objects.get_or_create(username="tecnico3", defaults={"first_name": "Técnico", "last_name": "C"})
        electronica_user, _ = User.objects.get_or_create(username="electronica1", defaults={"first_name": "Técnico", "last_name": "E"})
        supervisor, _ = User.objects.get_or_create(username="supervisor", defaults={"first_name": "Supervisor", "is_staff": True})
        for u in [tecnico1, tecnico2, tecnico3, electronica_user, supervisor]:
            u.set_password("predictpc2026")
            u.save()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@predictpc.local", "predictpc2026")

        lote, _ = Lote.objects.get_or_create(codigo="L-014")
        Lote.objects.get_or_create(codigo="L-015")

        self.stdout.write("Creando el caso demostrable PC-000123 (BIOS bloqueada)…")
        equipo = Equipo.objects.create(
            lote=lote, serial="5CG3120KDL", tipo=Equipo.TipoEquipo.PORTATIL,
            marca="Marca X", modelo="Modelo 14-A",
            proc_esperado="Intel Core i5 (gen. 11)", ram_esperada_gb=16,
            almacenamiento_tipo_esperado="SSD", almacenamiento_gb_esperado=512,
            so_esperado="Windows 11", creado_por=tecnico1,
        )
        services.ingresar_equipo(equipo, tecnico1)

        t1 = RegistroTriage1.objects.create(
            equipo=equipo, resultado_encendido=RegistroTriage1.Encendido.ENCIENDE,
            ram_encontrada_gb=16, almacenamiento_tipo_encontrado="SSD", almacenamiento_gb_encontrado=256,
            procesador_conforme=True, ram_conforme=True, almacenamiento_conforme=False,
            so_instalado="Windows 11 Pro", imagen_version="Imagen corp. v3",
            drivers_video=True, drivers_audio=True, drivers_red=True, drivers_chipset=True,
            bios_bloqueada=True, tecnico=tecnico1,
        )
        equipo.cambiar_etapa(Equipo.Etapa.TRIAGE_1)
        services.registrar_evento(equipo, Equipo.Etapa.TRIAGE_1, "Triage 1",
                                   "Encendido: enciende. Almacenamiento con diferencia (SSD 256 vs 512 GB).", tecnico=tecnico1)
        h_config = services.crear_hallazgo(equipo, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.CONFIGURACION,
                                            "Se encontró SSD de 256 GB; el proveedor especifica 512 GB.", tecnico1)
        h_bios = services.crear_hallazgo(equipo, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.BIOS, "BIOS bloqueada", tecnico1)
        remision = services.crear_remision(equipo, h_bios, "BIOS bloqueada",
                                            "Foto adjunta de pantalla de BIOS bloqueada.", tecnico1, Equipo.Etapa.TRIAGE_1)

        intervencion = IntervencionElectronica.objects.create(
            remision=remision, diagnostico="BIOS bloqueada",
            intervencion_realizada="Desmontaje y reprogramación de chip BIOS",
            archivo_bin="bios_modelo_v1.bin", verificada=True,
            etapa_retorno=Equipo.Etapa.TRIAGE_2, tecnico=electronica_user,
        )
        services.resolver_intervencion(intervencion, electronica_user)

        t2 = RegistroTriage2.objects.create(equipo=equipo, limpieza_interna=True, ventiladores=True,
                                             pasta_termica=True, tecnico=tecnico2)
        for elemento, _label in VerificacionPeriferico.Elemento.choices:
            falla = elemento == "USB"
            VerificacionPeriferico.objects.create(
                triage2=t2, elemento=elemento,
                resultado=VerificacionPeriferico.Resultado.FALLA if falla else VerificacionPeriferico.Resultado.CONFORME,
                observacion="Puerto 2 no reconoce dispositivos" if falla else "",
            )
        h_usb = services.crear_hallazgo(equipo, Hallazgo.Origen.TRIAGE_2, Hallazgo.Tipo.PERIFERICO,
                                         "USB: Puerto 2 no reconoce dispositivos", tecnico2)
        equipo.cambiar_etapa(Equipo.Etapa.TRIAGE_3)
        services.registrar_evento(equipo, Equipo.Etapa.TRIAGE_2, "Triage 2",
                                   "Mantenimiento y pruebas funcionales completados. Fallas registradas: 1.", tecnico=tecnico2)

        RegistroTriage3.objects.create(
            equipo=equipo, hallazgo=h_usb, actividad_realizada="Reemplazo de puerto USB",
            detalle="Se reemplazó el módulo USB izquierdo.",
            validacion_posterior=RegistroTriage3.Validacion.CORREGIDA, tecnico=tecnico3,
        )
        h_usb.marcar_resuelta()
        services.registrar_evento(equipo, Equipo.Etapa.TRIAGE_3, "Triage 3",
                                   "Reconstrucción: Reemplazo de puerto USB. Falla corregida.", tecnico=tecnico3)
        h_config.marcar_resuelta()
        equipo.cambiar_etapa(Equipo.Etapa.VALIDACION, Equipo.Estado.FINALIZADO)
        services.registrar_evento(equipo, Equipo.Etapa.VALIDACION, "Validación",
                                   "Triage 3 finalizado: todos los hallazgos resueltos. Equipo listo para validación final.",
                                   tecnico=tecnico3)

        self.stdout.write("Creando equipos adicionales para poblar la bandeja y el panel…")
        datos = [
            ("5CG3120KDM", "L-014", Equipo.Etapa.ELECTRONICA, Equipo.Estado.PENDIENTE_INTERVENCION, tecnico2),
            ("5CG3120KDN", "L-014", Equipo.Etapa.TRIAGE_2, Equipo.Estado.EN_PROCESO, tecnico2),
            ("5CG3120KDP", "L-015", Equipo.Etapa.TRIAGE_3, Equipo.Estado.EN_PROCESO, tecnico3),
            ("5CG3120KDQ", "L-015", Equipo.Etapa.FINALIZADO, Equipo.Estado.FINALIZADO, tecnico1),
        ]
        equipo_electronica_pendiente = None
        for serial, lote_cod, etapa, estado, tec in datos:
            l, _ = Lote.objects.get_or_create(codigo=lote_cod)
            e = Equipo.objects.create(
                lote=l, serial=serial, marca="Marca X", modelo="Modelo 14-A",
                proc_esperado="Intel Core i5 (gen. 11)", ram_esperada_gb=16,
                almacenamiento_tipo_esperado="SSD", almacenamiento_gb_esperado=512,
                so_esperado="Windows 11", creado_por=tec,
            )
            services.ingresar_equipo(e, tec)
            e.cambiar_etapa(etapa, estado)
            # Backdatar la entrada a la etapa para que el panel (HU18) muestre
            # tiempos promedio realistas y no todos en cero.
            horas_atras = {
                Equipo.Etapa.TRIAGE_2: 2.4, Equipo.Etapa.TRIAGE_3: 6.0,
                Equipo.Etapa.ELECTRONICA: 3.1, Equipo.Etapa.FINALIZADO: 0.2,
            }.get(etapa, 1.0)
            entrada = timezone.now() - timezone.timedelta(hours=horas_atras)
            EventoHistorial.objects.filter(equipo=e, tipo_evento="Ingreso").update(
                fecha=entrada - timezone.timedelta(minutes=10)
            )
            e.etapa_desde = entrada
            e.save(update_fields=["etapa_desde"])
            services.registrar_evento(e, etapa, etapa.replace("_", " ").title(),
                                       f"Equipo de demostración cargado en etapa {e.get_etapa_display()}.",
                                       tecnico=tec)
            EventoHistorial.objects.filter(equipo=e, tipo_evento=etapa.replace("_", " ").title()).update(fecha=entrada)
            if serial == "5CG3120KDM":
                equipo_electronica_pendiente = e

        # Deja una remision realmente ABIERTA para poder demostrar la pantalla P08
        # (recepcion en Electronica) ademas del caso ya resuelto de PC-000001.
        if equipo_electronica_pendiente is not None:
            h_pantalla = services.crear_hallazgo(
                equipo_electronica_pendiente, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.ESTETICA,
                "Pantalla con líneas verticales intermitentes.", tecnico2,
            )
            services.crear_remision(
                equipo_electronica_pendiente, h_pantalla, "Falla intermitente de pantalla",
                "Video de la falla adjunto por el técnico.", tecnico2, Equipo.Etapa.TRIAGE_1,
            )

        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados correctamente."))
