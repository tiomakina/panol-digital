# 🔧 Pañol v2.0 — Sistema de Gestión de Herramientas

Sistema empresarial de gestión de herramientas con branding dinámico por empresa.
Cada organización personaliza el logo y la paleta de colores de la aplicación.

## ✨ Características principales

- **Branding dinámico**: Logo y paleta de colores personalizables por empresa
- **Instalación 1 clic**: GUI con PyInstaller, sin conocimientos técnicos
- **PWA**: Instalable en móvil/PC, funciona sin internet
- **Préstamos**: Vales PDF con firma digital táctil
- **QR**: Inventario con escáner por cámara del dispositivo
- **Dashboard**: KPIs en tiempo real con WebSockets
- **Roles**: Jefe / Encargado / Mecánico con permisos granulares

## 🚀 Instalación rápida (desarrollo)

```bash
# 1. Clonar el proyecto
git clone https://github.com/tuempresa/panol-v2
cd panol-v2

# 2. Configurar entorno
cp .env.example .env
# Editar .env con sus datos

# 3. Iniciar con Docker
make up

# 4. O iniciar en modo desarrollo
cd backend
pip install -r requirements.txt
make dev
```

Acceder en: http://localhost:8080

## 🎨 Personalización de marca

1. Ir a **Administración → Personalización**
2. Subir el logo de la empresa (PNG, SVG, JPG, WebP)
3. Ajustar la paleta de colores o dejar que el sistema la detecte del logo
4. Guardar — el cambio aplica instantáneamente en toda la aplicación

## 📁 Estructura del proyecto

Ver `CLAUDE.md` para la documentación técnica completa.

## 🤝 Equipo virtual de desarrollo
Alex (Arquitecto) · Luna (UX/UI) · Marco (Backend) · Sara (Frontend) · Diego (Security) · Kim (DevOps)
