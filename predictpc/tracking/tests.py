from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import (
    Equipo, EventoHistorial, Hallazgo, Lote, Remision, VerificacionPeriferico,
)

User = get_user_model()

EQUIPO_POST = {
    "lote_codigo": "l-014", "serial": "5CG3120KDL", "tipo": "PORTATIL", "marca": "Marca X",
    "modelo": "Modelo 14-A", "fecha_ingreso": "2026-09-19T08:05",
    "proc_esperado": "Intel Core i5 (gen. 11)", "ram_esperada_gb": 16,
    "almacenamiento_tipo_esperado": "SSD", "almacenamiento_gb_esperado": 512,
    "so_esperado": "Windows 11", "observaciones_ingreso": "",
}


def crear_equipo(usuario, lote="L-014", serial="S1"):
    l, _ = Lote.objects.get_or_create(codigo=lote)
    e = Equipo.objects.create(
        lote=l, serial=serial, marca="X", modelo="Y", proc_esperado="i5",
        ram_esperada_gb=16, almacenamiento_tipo_esperado="SSD",
        almacenamiento_gb_esperado=512, creado_por=usuario,
    )
    services.ingresar_equipo(e, usuario)
    return e


class BaseTest(TestCase):
    def setUp(self):
        self.tec = User.objects.create_user("tec", password="x")
        self.client.login(username="tec", password="x")


class ModeloYServiciosTests(BaseTest):
    def test_id_unico_autogenerado(self):
        e = crear_equipo(self.tec)
        self.assertTrue(e.id_equipo.startswith("PC-"))
        self.assertEqual(e.id_equipo, f"PC-{e.pk:06d}")

    def test_ingreso_crea_evento_de_historial(self):
        e = crear_equipo(self.tec)
        self.assertEqual(e.historial.count(), 1)
        self.assertEqual(e.historial.first().tipo_evento, "Ingreso")

    def test_remision_deja_equipo_pendiente_de_intervencion(self):
        e = crear_equipo(self.tec)
        h = services.crear_hallazgo(e, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.BIOS, "BIOS bloqueada", self.tec)
        r = services.crear_remision(e, h, "BIOS bloqueada", "foto", self.tec, Equipo.Etapa.TRIAGE_1)
        e.refresh_from_db()
        self.assertEqual(e.etapa, Equipo.Etapa.ELECTRONICA)
        self.assertEqual(e.estado, Equipo.Estado.PENDIENTE_INTERVENCION)
        self.assertEqual(r.estado, Remision.Estado.ABIERTA)
        self.assertTrue(e.historial.filter(tipo_evento="Remisión", destacado=True).exists())

    def test_demorado_segun_umbral_de_etapa(self):
        e = crear_equipo(self.tec)
        e.cambiar_etapa(Equipo.Etapa.TRIAGE_3)
        self.assertFalse(services.esta_demorado(e))
        e.etapa_desde = timezone.now() - timedelta(hours=5)
        e.save()
        self.assertTrue(services.esta_demorado(e))


class VistasBasicasTests(BaseTest):
    def test_login_requerido(self):
        self.client.logout()
        r = self.client.get(reverse("tracking:bandeja"))
        self.assertEqual(r.status_code, 302)

    def test_p02_registra_equipo_y_redirige_a_triage1(self):
        r = self.client.post(reverse("tracking:registrar_equipo"), EQUIPO_POST)
        e = Equipo.objects.get()
        self.assertRedirects(r, reverse("tracking:triage1_encendido", args=[e.pk]))
        self.assertEqual(e.lote.codigo, "L-014")  # normaliza a mayúsculas

    def test_p01_filtra_por_etapa(self):
        e1 = crear_equipo(self.tec, serial="A")
        e2 = crear_equipo(self.tec, serial="B")
        e2.cambiar_etapa(Equipo.Etapa.TRIAGE_2)
        r = self.client.get(reverse("tracking:bandeja"), {"etapa": "TRIAGE_2"})
        self.assertContains(r, e2.id_equipo)
        self.assertNotContains(r, e1.id_equipo)

    def test_paginas_principales_responden_200(self):
        e = crear_equipo(self.tec)
        for name, args in [
            ("tracking:bandeja", []), ("tracking:registrar_equipo", []),
            ("tracking:ficha_equipo", [e.pk]), ("tracking:triage1_encendido", [e.pk]),
            ("tracking:triage2", [e.pk]), ("tracking:triage3", [e.pk]),
            ("tracking:historial", [e.pk]), ("tracking:panel_supervisor", []),
            ("tracking:remisiones_pendientes", []),
        ]:
            with self.subTest(vista=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)


class ValidacionesDeNegocioTests(BaseTest):
    def test_hu03_diferencia_exige_descripcion(self):
        e = crear_equipo(self.tec)
        r = self.client.post(reverse("tracking:triage1_encendido", args=[e.pk]), {
            "resultado_encendido": "ENCIENDE", "ram_encontrada_gb": 16,
            "almacenamiento_tipo_encontrado": "SSD", "almacenamiento_gb_encontrado": 256,
            "procesador_conforme": "on", "ram_conforme": "on",  # almacenamiento NO conforme
            "diferencia_descripcion": "",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "obligatoria")
        self.assertFalse(Hallazgo.objects.filter(equipo=e).exists())

    def test_hu05_bios_exige_evidencia(self):
        e = crear_equipo(self.tec)
        self.client.post(reverse("tracking:triage1_encendido", args=[e.pk]), {
            "resultado_encendido": "ENCIENDE", "ram_encontrada_gb": 16,
            "almacenamiento_tipo_encontrado": "SSD", "almacenamiento_gb_encontrado": 512,
            "procesador_conforme": "on", "ram_conforme": "on", "almacenamiento_conforme": "on",
        })
        r = self.client.post(reverse("tracking:triage1_so", args=[e.pk]), {
            "so_instalado": "Win", "imagen_version": "v3", "bios_bloqueada": "on", "evidencia_bios": "",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Remision.objects.exists())


class CasoDemostrableTests(BaseTest):
    """Recorre por las vistas el caso acordado en las Fases 2 y 3."""

    def test_flujo_completo_bios_electronica_retorno_triage2_triage3(self):
        # P02 ingreso
        self.client.post(reverse("tracking:registrar_equipo"), EQUIPO_POST)
        e = Equipo.objects.get()

        # P04 Triage 1: diferencia de almacenamiento (genera hallazgo)
        self.client.post(reverse("tracking:triage1_encendido", args=[e.pk]), {
            "resultado_encendido": "ENCIENDE", "ram_encontrada_gb": 16,
            "almacenamiento_tipo_encontrado": "SSD", "almacenamiento_gb_encontrado": 256,
            "procesador_conforme": "on", "ram_conforme": "on",
            "diferencia_descripcion": "SSD de 256 GB; proveedor especifica 512 GB",
        })
        self.assertEqual(Hallazgo.objects.filter(tipo="CONFIGURACION").count(), 1)

        # P05 BIOS bloqueada -> remisión a Electrónica
        r = self.client.post(reverse("tracking:triage1_so", args=[e.pk]), {
            "so_instalado": "Windows 11 Pro", "imagen_version": "v3", "drivers_video": "on",
            "bios_bloqueada": "on", "evidencia_bios": "foto de pantalla BIOS",
        })
        e.refresh_from_db()
        self.assertEqual(e.etapa, Equipo.Etapa.ELECTRONICA)
        remision = Remision.objects.get()

        # P08 Electrónica: intervención y retorno a Triage 2
        self.client.post(reverse("tracking:electronica", args=[remision.pk]), {
            "diagnostico": "BIOS bloqueada",
            "intervencion_realizada": "Reprogramación de chip BIOS",
            "archivo_bin": "bios_modelo_v1.bin", "verificada": "True",
            "observaciones": "", "etapa_retorno": "TRIAGE_2",
        })
        e.refresh_from_db(); remision.refresh_from_db()
        self.assertEqual(e.etapa, Equipo.Etapa.TRIAGE_2)
        self.assertEqual(e.estado, Equipo.Estado.EN_PROCESO)
        self.assertEqual(remision.estado, Remision.Estado.RESUELTA)

        # P06 Triage 2: falla en USB
        self.client.get(reverse("tracking:triage2", args=[e.pk]))  # crea filas de verificación
        verifs = list(VerificacionPeriferico.objects.filter(triage2__equipo=e).order_by("id"))
        data = {
            "form-TOTAL_FORMS": len(verifs), "form-INITIAL_FORMS": len(verifs),
            "form-MIN_NUM_FORMS": 0, "form-MAX_NUM_FORMS": 1000,
            "limpieza_interna": "on", "ventiladores": "on",
        }
        for i, v in enumerate(verifs):
            data[f"form-{i}-id"] = v.pk
            data[f"form-{i}-elemento"] = v.elemento
            usb = v.elemento == "USB"
            data[f"form-{i}-resultado"] = "FALLA" if usb else "CONFORME"
            data[f"form-{i}-observacion"] = "Puerto 2 no reconoce dispositivos" if usb else ""
        self.client.post(reverse("tracking:triage2", args=[e.pk]), data)
        e.refresh_from_db()
        self.assertEqual(e.etapa, Equipo.Etapa.TRIAGE_3)
        usb = Hallazgo.objects.get(tipo="PERIFERICO")

        # P07 Triage 3: reparar y revalidar -> finaliza cuando no quedan pendientes
        for h in e.hallazgos_pendientes():
            self.client.post(reverse("tracking:triage3", args=[e.pk]), {
                "hallazgo": h.pk, "actividad_realizada": "Reparación / reemplazo",
                "detalle": "", "validacion_posterior": "CORREGIDA",
            })
        e.refresh_from_db()
        self.assertEqual(e.estado, Equipo.Estado.FINALIZADO)
        self.assertFalse(e.hallazgos_pendientes().exists())

        # P09 historial completo con remisión y retorno resaltados
        tipos = list(EventoHistorial.objects.filter(equipo=e).values_list("tipo_evento", flat=True))
        for esperado in ["Ingreso", "Triage 1", "Remisión", "Electrónica", "Retorno", "Triage 2", "Triage 3"]:
            self.assertIn(esperado, tipos)
        r = self.client.get(reverse("tracking:historial", args=[e.pk]))
        self.assertContains(r, "retorna a")

    def test_triage3_continua_pendiente_genera_nueva_remision(self):
        e = crear_equipo(self.tec)
        h = services.crear_hallazgo(e, Hallazgo.Origen.TRIAGE_2, Hallazgo.Tipo.PERIFERICO, "USB", self.tec)
        e.cambiar_etapa(Equipo.Etapa.TRIAGE_3)
        self.client.post(reverse("tracking:triage3", args=[e.pk]), {
            "hallazgo": h.pk, "actividad_realizada": "Reemplazo", "validacion_posterior": "PENDIENTE",
        })
        e.refresh_from_db()
        self.assertEqual(e.etapa, Equipo.Etapa.ELECTRONICA)
        self.assertEqual(Remision.objects.filter(equipo=e).count(), 1)


class PanelTests(BaseTest):
    def test_panel_cuenta_demorados_y_remisiones(self):
        e = crear_equipo(self.tec)
        e.cambiar_etapa(Equipo.Etapa.TRIAGE_3)
        e.etapa_desde = timezone.now() - timedelta(hours=6)
        e.save()
        e2 = crear_equipo(self.tec, serial="S2")
        h = services.crear_hallazgo(e2, Hallazgo.Origen.TRIAGE_1, Hallazgo.Tipo.BIOS, "BIOS", self.tec)
        services.crear_remision(e2, h, "BIOS", "", self.tec, Equipo.Etapa.TRIAGE_1)
        datos = services.panel_indicadores(Equipo.objects.all())
        self.assertEqual(len(datos["demorados"]), 1)
        self.assertEqual(datos["remisiones_abiertas"], 1)
        self.assertEqual(datos["en_proceso"], 2)
        r = self.client.get(reverse("tracking:panel_supervisor"))
        self.assertContains(r, "Panel de seguimiento")
