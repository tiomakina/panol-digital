# Registro de Clientes — Pañol 360 SaaS

Cada subdirectorio aquí corresponde a un cliente activo o histórico del sistema.

## Estructura de cada cliente

```
clients/<slug>/
├── client.conf     ← Datos de conexión y configuración del cliente
└── CHANGELOG.md    ← Bitácora de todos los cambios hechos para este cliente
```

## Cómo usar

```bash
# Listar todos los clientes
bash scripts/admin.sh list

# Ver estado de un cliente
bash scripts/admin.sh status vms-ingenieria

# Agregar entrada a la bitácora
bash scripts/admin.sh log vms-ingenieria "Ajusté el color primario a verde"

# Establecer contexto de sesión (para Claude Code)
bash scripts/admin.sh context vms-ingenieria prod
```

## Convención de slugs

El slug es el identificador único del cliente en minúsculas, sin espacios, sin tildes:
- VMS Ingeniería → `vms-ingenieria`
- Taller Mecánico VMS → `taller-vms`
- Constructora Atacama S.A. → `constructora-atacama`
