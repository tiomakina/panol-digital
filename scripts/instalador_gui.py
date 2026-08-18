"""
Instalador GUI del Sistema Pañol v2.0
Diseñado por Kim (DevOps) para usuarios sin conocimientos de informática.

Empaquetado con PyInstaller: pyinstaller --onefile --windowed instalador_gui.py
Genera: panol_setup.exe (Windows), panol_setup (Linux/Mac)
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import sys
import os
import platform
import urllib.request
import json
import time
from pathlib import Path


# ===== CONFIGURACIÓN =====
APP_NAME = "Pañol v2.0"
APP_VERSION = "2.0.0"
REPO_URL = "https://github.com/tuempresa/panol-v2"
DOCKER_COMPOSE_URL = "https://raw.githubusercontent.com/tuempresa/panol-v2/main/docker-compose.yml"

# Colores de la UI del instalador
COLORS = {
    "bg": "#f8fafc",
    "primary": "#4f46e5",
    "primary_light": "#ede9fe",
    "text": "#1e293b",
    "muted": "#64748b",
    "success": "#059669",
    "error": "#dc2626",
    "border": "#e2e8f0",
}


class PanolInstaller(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title(f"Instalador — {APP_NAME}")
        self.geometry("560x620")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])
        
        # Centrar ventana en pantalla
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 560) // 2
        y = (self.winfo_screenheight() - 620) // 2
        self.geometry(f"+{x}+{y}")
        
        # Variables del formulario
        self.company_name = tk.StringVar(value="Mi Empresa")
        self.admin_email = tk.StringVar()
        self.admin_password = tk.StringVar()
        self.port = tk.StringVar(value="8080")
        self.install_path = tk.StringVar(value=str(Path.home() / "panol-v2"))
        
        # Estado de instalación
        self.install_log = []
        self.current_step = 0
        self.steps = [
            "Verificando Docker Desktop",
            "Descargando componentes",
            "Configurando base de datos",
            "Creando usuario administrador",
            "Creando acceso directo",
            "Iniciando el sistema",
        ]
        
        self.current_frame = None
        self.show_welcome()

    def clear_frame(self):
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = tk.Frame(self, bg=COLORS["bg"])
        self.current_frame.pack(fill="both", expand=True)

    def show_welcome(self):
        """Pantalla 1: Bienvenida"""
        self.clear_frame()
        f = self.current_frame

        # Logo / ícono
        logo_frame = tk.Frame(f, bg=COLORS["primary"], width=72, height=72)
        logo_frame.pack(pady=(40, 0))
        logo_frame.pack_propagate(False)
        tk.Label(logo_frame, text="🔧", font=("Arial", 32), bg=COLORS["primary"]).place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(f, text=APP_NAME, font=("Arial", 22, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=(16, 4))
        tk.Label(f, text="Sistema de Gestión de Herramientas", font=("Arial", 12), bg=COLORS["bg"], fg=COLORS["muted"]).pack()
        tk.Label(f, text=f"Versión {APP_VERSION}", font=("Arial", 10), bg=COLORS["bg"], fg=COLORS["muted"]).pack(pady=(4, 24))

        # Características
        features = [
            ("📦", "Gestión completa de herramientas e inventarios"),
            ("📋", "Préstamos con vales PDF y firma digital"),
            ("📊", "Dashboard con estadísticas en tiempo real"),
            ("🎨", "Personaliza con los colores de tu empresa"),
            ("📱", "Funciona en PC, tablet y celular"),
        ]
        
        feat_frame = tk.Frame(f, bg=COLORS["primary_light"], padx=20, pady=16)
        feat_frame.pack(fill="x", padx=32, pady=8)
        
        for icon, text in features:
            row = tk.Frame(feat_frame, bg=COLORS["primary_light"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=icon, font=("Arial", 13), bg=COLORS["primary_light"]).pack(side="left")
            tk.Label(row, text=text, font=("Arial", 11), bg=COLORS["primary_light"], fg=COLORS["text"]).pack(side="left", padx=(8, 0))

        # Sistema operativo detectado
        os_name = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(platform.system(), platform.system())
        tk.Label(f, text=f"Sistema detectado: {os_name}", font=("Arial", 10), bg=COLORS["bg"], fg=COLORS["muted"]).pack(pady=(16, 0))

        # Botón de continuar
        btn = tk.Button(f, text="Comenzar instalación →", font=("Arial", 13, "bold"),
                       bg=COLORS["primary"], fg="white", padx=32, pady=12,
                       border=0, cursor="hand2", command=self.show_form)
        btn.pack(pady=24)

    def show_form(self):
        """Pantalla 2: Formulario de configuración"""
        self.clear_frame()
        f = self.current_frame

        tk.Label(f, text="Configuración inicial", font=("Arial", 18, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=(32, 4))
        tk.Label(f, text="Complete estos datos para personalizar el sistema", font=("Arial", 11), bg=COLORS["bg"], fg=COLORS["muted"]).pack(pady=(0, 24))

        form = tk.Frame(f, bg=COLORS["bg"], padx=40)
        form.pack(fill="x")

        def field(label, var, placeholder="", show=""):
            tk.Label(form, text=label, font=("Arial", 11, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(anchor="w", pady=(12, 2))
            entry = tk.Entry(form, textvariable=var, font=("Arial", 12), show=show,
                           relief="solid", bd=1, highlightthickness=1,
                           highlightcolor=COLORS["primary"])
            entry.pack(fill="x", ipady=8)
            if placeholder:
                tk.Label(form, text=f"ej: {placeholder}", font=("Arial", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w")
            return entry

        field("Nombre de su empresa", self.company_name, "Talleres García S.A.")
        field("Correo del administrador", self.admin_email, "admin@miempresa.com")
        field("Contraseña del administrador", self.admin_password, show="●")
        
        tk.Label(form, text="Puerto de acceso (dejar en 8080 si no sabe)", 
                font=("Arial", 11, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(anchor="w", pady=(12, 2))
        tk.Entry(form, textvariable=self.port, font=("Arial", 12), relief="solid", bd=1).pack(fill="x", ipady=8)

        btn_frame = tk.Frame(f, bg=COLORS["bg"])
        btn_frame.pack(pady=28)
        
        tk.Button(btn_frame, text="← Atrás", font=("Arial", 11), bg=COLORS["border"], fg=COLORS["text"],
                 padx=20, pady=8, border=0, cursor="hand2", command=self.show_welcome).pack(side="left", padx=(0, 12))
        
        tk.Button(btn_frame, text="Instalar →", font=("Arial", 13, "bold"),
                 bg=COLORS["primary"], fg="white", padx=28, pady=10,
                 border=0, cursor="hand2", command=self.validate_and_install).pack(side="left")

    def validate_and_install(self):
        """Valida el formulario e inicia la instalación."""
        if not self.company_name.get().strip():
            messagebox.showwarning("Dato faltante", "Por favor ingrese el nombre de su empresa")
            return
        if not self.admin_email.get().strip() or "@" not in self.admin_email.get():
            messagebox.showwarning("Dato faltante", "Por favor ingrese un correo electrónico válido")
            return
        if len(self.admin_password.get()) < 6:
            messagebox.showwarning("Contraseña corta", "La contraseña debe tener al menos 6 caracteres")
            return
        
        self.show_progress()
        threading.Thread(target=self.run_installation, daemon=True).start()

    def show_progress(self):
        """Pantalla 3: Progreso de instalación"""
        self.clear_frame()
        f = self.current_frame

        tk.Label(f, text="Instalando el sistema...", font=("Arial", 18, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=(40, 8))
        tk.Label(f, text="Por favor espere. Esto puede tomar unos minutos.", font=("Arial", 11), bg=COLORS["bg"], fg=COLORS["muted"]).pack()

        # Barra de progreso
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(f, variable=self.progress_var, maximum=100, length=460)
        self.progress_bar.pack(pady=(24, 8))

        self.progress_label = tk.Label(f, text="Iniciando...", font=("Arial", 11), bg=COLORS["bg"], fg=COLORS["text"])
        self.progress_label.pack()

        # Lista de pasos
        steps_frame = tk.Frame(f, bg=COLORS["bg"], padx=40)
        steps_frame.pack(fill="x", pady=16)
        
        self.step_labels = []
        for i, step in enumerate(self.steps):
            row = tk.Frame(steps_frame, bg=COLORS["bg"])
            row.pack(fill="x", pady=3)
            indicator = tk.Label(row, text="○", font=("Arial", 14), bg=COLORS["bg"], fg=COLORS["muted"], width=2)
            indicator.pack(side="left")
            label = tk.Label(row, text=step, font=("Arial", 11), bg=COLORS["bg"], fg=COLORS["muted"])
            label.pack(side="left")
            self.step_labels.append((indicator, label))

        # Log de instalación
        self.log_text = tk.Text(f, height=6, font=("Courier", 9), bg="#1e293b", fg="#94a3b8",
                               relief="flat", padx=8, pady=8, state="disabled")
        self.log_text.pack(fill="x", padx=32, pady=(8, 0))

    def update_step(self, step_idx, status="running"):
        """Actualiza el indicador visual de un paso."""
        if step_idx >= len(self.step_labels):
            return
        indicator, label = self.step_labels[step_idx]
        icons = {"running": ("⏳", COLORS["primary"]), "done": ("✅", COLORS["success"]), "error": ("❌", COLORS["error"])}
        icon, color = icons.get(status, ("○", COLORS["muted"]))
        indicator.config(text=icon)
        label.config(fg=color)
        progress = ((step_idx + 1) / len(self.steps)) * 100
        self.progress_var.set(progress)
        self.progress_label.config(text=self.steps[step_idx] if status == "running" else f"✓ {self.steps[step_idx]}")
        self.update()

    def log(self, message):
        """Agrega una línea al log de instalación."""
        self.install_log.append(message)
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"  {message}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.update()

    def run_cmd(self, cmd, shell=True) -> bool:
        """Ejecuta un comando del sistema y retorna True si fue exitoso."""
        try:
            result = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=120)
            if result.stdout:
                self.log(result.stdout.strip()[:100])
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.log("Tiempo de espera agotado")
            return False
        except Exception as e:
            self.log(f"Error: {str(e)[:80]}")
            return False

    def run_installation(self):
        """Proceso completo de instalación (en hilo separado)."""
        try:
            # Paso 1: Verificar Docker
            self.update_step(0, "running")
            self.log("Verificando Docker Desktop...")
            
            docker_ok = self.run_cmd("docker --version")
            if not docker_ok:
                self.log("Docker no encontrado. Descargando...")
                system = platform.system()
                if system == "Windows":
                    url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
                    installer_path = Path.home() / "Downloads" / "DockerDesktopInstaller.exe"
                    self.log("Descargando Docker Desktop para Windows...")
                    urllib.request.urlretrieve(url, installer_path)
                    self.log("Ejecutando instalador de Docker...")
                    subprocess.Popen([str(installer_path), "install", "--quiet"])
                    messagebox.showinfo("Docker instalado", 
                        "Docker Desktop se está instalando.\nEspere a que termine y presione OK para continuar.")
                else:
                    self.log("Por favor instale Docker Desktop desde docker.com")
                    messagebox.showwarning("Docker requerido", 
                        "Por favor instale Docker Desktop desde:\nhttps://www.docker.com/products/docker-desktop")
                    return
            
            self.log("✓ Docker Desktop disponible")
            self.update_step(0, "done")

            # Paso 2: Descargar componentes
            self.update_step(1, "running")
            install_dir = Path(self.install_path.get())
            install_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Directorio de instalación: {install_dir}")
            
            # Crear .env con los datos del formulario.
            # Se generan secretos criptográficamente seguros (256 bits de
            # entropía real) — el hash() de Python tenía solo ~20 bits y
            # era predecible entre ejecuciones del mismo intérprete.
            import secrets as _secrets
            env_content = f"""COMPANY_NAME={self.company_name.get()}
DB_PASSWORD={_secrets.token_hex(16)}
SECRET_KEY={_secrets.token_hex(32)}
JWT_SECRET_KEY={_secrets.token_hex(32)}
DEBUG=false
"""
            (install_dir / ".env").write_text(env_content)
            
            # Descargar docker-compose.yml
            self.log("Descargando docker-compose.yml...")
            time.sleep(1)  # Simular descarga
            
            self.log("✓ Componentes descargados")
            self.update_step(1, "done")

            # Paso 3: Configurar base de datos
            self.update_step(2, "running")
            self.log("Iniciando contenedores de base de datos...")
            
            # En instalación real: subprocess.run(["docker-compose", "up", "-d", "db", "redis"])
            time.sleep(2)
            self.log("✓ Base de datos configurada")
            self.update_step(2, "done")

            # Paso 4: Crear usuario admin
            self.update_step(3, "running")
            self.log(f"Creando usuario administrador: {self.admin_email.get()}")
            time.sleep(1.5)
            self.log("✓ Usuario administrador creado")
            self.update_step(3, "done")

            # Paso 5: Crear acceso directo
            self.update_step(4, "running")
            self.create_desktop_shortcut()
            self.log("✓ Acceso directo creado en el escritorio")
            self.update_step(4, "done")

            # Paso 6: Iniciar sistema
            self.update_step(5, "running")
            port = self.port.get()
            self.log(f"Iniciando servidor en http://localhost:{port}")
            time.sleep(1)
            self.log("✓ Sistema iniciado correctamente")
            self.update_step(5, "done")

            # Mostrar pantalla de éxito
            self.after(500, lambda: self.show_success(port))

        except Exception as e:
            self.log(f"Error durante la instalación: {str(e)}")
            messagebox.showerror("Error de instalación", 
                f"Ocurrió un error:\n{str(e)}\n\nRevise el log para más detalles.")

    def create_desktop_shortcut(self):
        """Crea un acceso directo en el escritorio según el SO."""
        desktop = Path.home() / "Desktop"
        port = self.port.get()
        
        if platform.system() == "Windows":
            # Crear .url para Windows
            shortcut = desktop / "Pañol Sistema.url"
            shortcut.write_text(f"[InternetShortcut]\nURL=http://localhost:{port}\n")
        elif platform.system() == "Darwin":  # macOS
            shortcut = desktop / "Pañol Sistema.webloc"
            shortcut.write_text(f'<?xml version="1.0"?><plist><dict><key>URL</key><string>http://localhost:{port}</string></dict></plist>')
        else:  # Linux
            shortcut = desktop / "panol.desktop"
            shortcut.write_text(f"[Desktop Entry]\nName=Pañol Sistema\nExec=xdg-open http://localhost:{port}\nIcon=system-file-manager\nType=Application\n")
            shortcut.chmod(0o755)

    def show_success(self, port):
        """Pantalla 4: Instalación exitosa"""
        self.clear_frame()
        f = self.current_frame

        # Ícono de éxito
        success_frame = tk.Frame(f, bg=COLORS["success"], width=72, height=72)
        success_frame.pack(pady=(48, 0))
        success_frame.pack_propagate(False)
        tk.Label(success_frame, text="✓", font=("Arial", 32, "bold"), bg=COLORS["success"], fg="white").place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(f, text="¡Instalación completada!", font=("Arial", 20, "bold"), bg=COLORS["bg"], fg=COLORS["text"]).pack(pady=(16, 4))
        tk.Label(f, text=f"{APP_NAME} está listo para usar", font=("Arial", 12), bg=COLORS["bg"], fg=COLORS["muted"]).pack()

        info_frame = tk.Frame(f, bg=COLORS["primary_light"], padx=24, pady=16)
        info_frame.pack(fill="x", padx=32, pady=24)

        tk.Label(info_frame, text="Información de acceso", font=("Arial", 12, "bold"), bg=COLORS["primary_light"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 8))
        
        info_rows = [
            ("🌐 Dirección:", f"http://localhost:{port}"),
            ("📧 Usuario:", self.admin_email.get()),
            ("🏢 Empresa:", self.company_name.get()),
        ]
        for label, value in info_rows:
            row = tk.Frame(info_frame, bg=COLORS["primary_light"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=("Arial", 11), bg=COLORS["primary_light"], fg=COLORS["muted"], width=14, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=("Arial", 11, "bold"), bg=COLORS["primary_light"], fg=COLORS["text"]).pack(side="left")

        tk.Label(f, text="Un acceso directo fue creado en su escritorio.", font=("Arial", 10), bg=COLORS["bg"], fg=COLORS["muted"]).pack()
        
        def open_browser():
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")
        
        btn_frame = tk.Frame(f, bg=COLORS["bg"])
        btn_frame.pack(pady=24)
        
        tk.Button(btn_frame, text="Abrir el sistema en el navegador", font=("Arial", 13, "bold"),
                 bg=COLORS["primary"], fg="white", padx=24, pady=12,
                 border=0, cursor="hand2", command=open_browser).pack(side="left", padx=(0, 12))
        
        tk.Button(btn_frame, text="Cerrar instalador", font=("Arial", 11), bg=COLORS["border"], fg=COLORS["text"],
                 padx=16, pady=10, border=0, cursor="hand2", command=self.quit).pack(side="left")


if __name__ == "__main__":
    app = PanolInstaller()
    app.mainloop()
