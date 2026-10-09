# PREDICT PC · Incremento funcional (Fase 4)

Plataforma web de trazabilidad operativa de computadores. Implementa el
núcleo MVP definido en la Fase 2 y diseñado en la Fase 3 (pantallas P01–P10),
con Django + Bootstrap 5 + Chart.js, según el stack preliminar de la Fase 1.

## Requisitos
- Python 3.11+
- pip

## Instalación y ejecución local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo      # crea usuarios y el caso demostrable
python manage.py runserver
```

Abrir http://127.0.0.1:8000 e iniciar sesión con:

| Usuario        | Contraseña      | Rol                         |
|----------------|-----------------|------------------------------|
| tecnico1       | predictpc2026   | Triage 1                     |
| tecnico2       | predictpc2026   | Triage 2                     |
| tecnico3       | predictpc2026   | Triage 3                     |
| electronica1   | predictpc2026   | Electrónica                  |
| supervisor     | predictpc2026   | Supervisor / panel           |
| admin          | predictpc2026   | Superusuario (/admin/)       |

## Pruebas automatizadas

```bash
python manage.py test tracking
```

## Estructura

```
predictpc/          Configuración del proyecto (settings, urls raíz)
tracking/
  models.py          Modelos del núcleo MVP (HU01–HU18)
  services.py         Reglas de negocio (remisión, retorno, indicadores)
  forms.py            Formularios de cada pantalla
  views.py             Vistas P01–P10
  urls.py
  templates/tracking/  Plantillas Bootstrap 5 (una por pantalla P01–P10)
  management/commands/seed_demo.py  Datos de demostración (caso BIOS bloqueada)
  tests.py             Pruebas unitarias y de flujo completo (13 pruebas)
```

## Trazabilidad con las fases anteriores

- Fase 1: problema, actores y stack preliminar (Django, PostgreSQL/SQLite, Bootstrap, Chart.js).
- Fase 2: historias de usuario HU01–HU18 → modelos y vistas de este repositorio.
- Fase 3: wireframes P01–P10 → plantillas `tracking/templates/tracking/p0X_*.html`.
- Fase 4 (este repositorio): incremento funcional, Kanban de desarrollo y control de versiones (ver documento de la fase).
