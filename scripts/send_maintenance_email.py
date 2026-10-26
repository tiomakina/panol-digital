#!/usr/bin/env python3
"""
Envía el email de resumen del mantenimiento mensual.
Lee credenciales desde --conf (archivo KEY=VALUE, sin comillas).
"""
import argparse
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _load_conf(path: str) -> dict[str, str]:
    conf: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            conf[k.strip()] = v.strip()
    return conf


def _tail_log(logfile: str, lines: int = 60) -> str:
    try:
        content = Path(logfile).read_text()
        tail = content.splitlines()[-lines:]
        return "\n".join(tail)
    except Exception:
        return "(no disponible)"


def _icon(ok: bool) -> str:
    return "✅" if ok else "❌"


def _row(label: str, value: str, warn: bool = False) -> str:
    color = "#dc2626" if warn else "#374151"
    return (
        f"<tr>"
        f"<td style='padding:10px 16px;border-bottom:1px solid #f3f4f6;"
        f"color:#6b7280;font-size:13px;white-space:nowrap'>{label}</td>"
        f"<td style='padding:10px 16px;border-bottom:1px solid #f3f4f6;"
        f"color:{color};font-size:13px;font-weight:500'>{value}</td>"
        f"</tr>"
    )


def build_html(args: argparse.Namespace, fecha: str) -> str:
    reboot_warn = bool(args.reboot)
    disk_pct = int(args.disk.split("%")[0].split("(")[0].strip()) if "%" in args.disk else 0
    disk_warn = disk_pct >= 80

    reboot_banner = ""
    if reboot_warn:
        reboot_banner = (
            "<div style='background:#fef2f2;border:1px solid #fca5a5;"
            "border-radius:8px;padding:14px 18px;margin-bottom:20px;"
            "color:#991b1b;font-size:14px'>"
            "⚠️ <strong>Se requiere reinicio del servidor.</strong> "
            "Conéctate por SSH y ejecuta <code>sudo reboot</code>, "
            "luego verifica los contenedores con <code>docker compose ps</code>."
            "</div>"
        )

    tail = _tail_log(args.logfile)

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Mantenimiento panol360.app</title></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:'Segoe UI',Arial,sans-serif">
<div style="max-width:620px;margin:32px auto;background:#fff;border-radius:12px;
            overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.08)">

  <!-- Header -->
  <div style="background:#1e40af;padding:28px 32px">
    <p style="margin:0 0 4px;color:#bfdbfe;font-size:12px;letter-spacing:.05em;
              text-transform:uppercase">panol360.app</p>
    <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">
      Mantenimiento Mensual Completado
    </h1>
    <p style="margin:8px 0 0;color:#93c5fd;font-size:14px">{fecha}</p>
  </div>

  <!-- Body -->
  <div style="padding:28px 32px">
    {reboot_banner}

    <p style="color:#374151;font-size:14px;margin:0 0 20px">
      El mantenimiento mensual automático se ejecutó correctamente.
      A continuación el resumen:
    </p>

    <!-- Tabla resumen -->
    <table width="100%" cellspacing="0" cellpadding="0"
           style="border:1px solid #e5e7eb;border-radius:8px;
                  border-collapse:separate;overflow:hidden;margin-bottom:24px">
      {_row("💾 Backup",        args.backup, warn=("FALLÓ" in args.backup))}
      {_row("📦 Actualizaciones", args.apt,   warn=("FALLÓ" in args.apt))}
      {_row("🐳 Contenedores",  f"{args.containers} activos")}
      {_row("💿 Disco raíz",    args.disk,  warn=disk_warn)}
      {_row("🐧 Kernel",        args.kernel)}
      {_row("🔄 Reinicio",      "Requerido — pendiente" if reboot_warn else "No requerido", warn=reboot_warn)}
    </table>

    <!-- Próximo mantenimiento -->
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
                padding:14px 18px;margin-bottom:24px">
      <p style="margin:0;color:#1e40af;font-size:14px">
        📅 <strong>Próximo mantenimiento programado: {args.next}</strong>
      </p>
    </div>

    <!-- Log tail -->
    <p style="color:#374151;font-size:13px;font-weight:600;margin:0 0 8px">
      Log de ejecución (últimas líneas)
    </p>
    <pre style="background:#1e2433;color:#cdd6f4;border-radius:8px;
                padding:14px;font-size:11.5px;overflow-x:auto;
                white-space:pre-wrap;word-break:break-all;
                max-height:300px;overflow-y:auto">{tail}</pre>
  </div>

  <!-- Footer -->
  <div style="background:#f9fafb;border-top:1px solid #f3f4f6;
              padding:16px 32px;text-align:center">
    <p style="margin:0;color:#9ca3af;font-size:12px">
      Pañol 360 · Mantenimiento automático · Oracle Cloud Santiago
    </p>
  </div>
</div>
</body></html>"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--conf",       required=True)
    p.add_argument("--backup",     required=True)
    p.add_argument("--apt",        required=True)
    p.add_argument("--containers", required=True)
    p.add_argument("--disk",       required=True)
    p.add_argument("--kernel",     required=True)
    p.add_argument("--reboot",     default="")
    p.add_argument("--next",       required=True)
    p.add_argument("--logfile",    required=True)
    args = p.parse_args()

    conf = _load_conf(args.conf)
    smtp_host = conf.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(conf.get("SMTP_PORT", "587"))
    smtp_user = conf["SMTP_USER"]
    smtp_pass = conf["SMTP_PASS"]
    email_to  = conf.get("EMAIL_TO", smtp_user)

    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    subject = f"✅ Mantenimiento panol360.app — {datetime.now().strftime('%B %Y')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Pañol 360 Servidor <{smtp_user}>"
    msg["To"]      = email_to

    html = build_html(args, fecha)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [email_to], msg.as_string())

    print(f"Email enviado a {email_to}")


if __name__ == "__main__":
    main()
