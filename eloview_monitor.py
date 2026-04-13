import requests
import schedule
import time
import json
import os
from datetime import datetime

# ── Credenciales ──────────────────────────────────────────
CLIENT_ID     = os.environ.get("CLIENT_ID", "yLeZA2aELm5CztEP1IKV4MZMkG")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "QlvJxcZsoZLMWYzOckdRlb6VPT80qz8R0RJxjifizFLIwoJQrs52")
ORG_ID        = os.environ.get("ORG_ID", "01K7PZV1M1HWYWAKGC75GWXVEB")
TG_TOKEN      = os.environ.get("TG_TOKEN", "TU_BOT_TOKEN_AQUI")
TG_CHAT       = os.environ.get("TG_CHAT", "1019869677")

INTERVALO_MIN    = 5      # cada cuántos minutos revisa
UMBRAL_OFFLINE   = 120   # minutos antes de alertar (2 horas)
HORA_REPORTE     = "08:00"
HORA_INICIO      = 8     # horario de alertas
HORA_FIN         = 20
BASE             = "https://secure-api.eloview.com/prod"
ESTADO_FILE      = "estado_dispositivos.json"
# ──────────────────────────────────────────────────────────

token_cache = {"token": None, "obtenido_a": 0}


def get_token():
    ahora = time.time()
    if token_cache["token"] and (ahora - token_cache["obtenido_a"]) < 82800:
        return token_cache["token"]
    r = requests.post(
        f"{BASE}/auth/{CLIENT_ID}/token",
        json={"clientsecret": CLIENT_SECRET},
        timeout=15
    )
    r.raise_for_status()
    token_cache["token"] = r.json()["result"]["access_token"]
    token_cache["obtenido_a"] = ahora
    return token_cache["token"]


def get_devices(token):
    r = requests.get(
        f"{BASE}/orgs/{ORG_ID}/contentStatus",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15
    )
    r.raise_for_status()
    return r.json().get("data", [])


def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
        timeout=10
    )


def cargar_estado():
    if os.path.exists(ESTADO_FILE):
        with open(ESTADO_FILE, "r") as f:
            return json.load(f)
    return {}


def guardar_estado(estado):
    with open(ESTADO_FILE, "w") as f:
        json.dump(estado, f)


def hora_en_rango():
    hora = datetime.now().hour
    return HORA_INICIO <= hora < HORA_FIN


def run_monitor():
    ahora_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n[{ahora_str}] Ejecutando monitoreo...")

    try:
        token  = get_token()
        devs   = get_devices(token)
        estado = cargar_estado()
        ahora  = time.time()

        for d in devs:
            serial   = d.get("serial", "")
            online   = d.get("isOnline", False)
            grupo    = d.get("groupName", "Sin grupo")
            contenido = d.get("contentName", "Sin contenido")

            prev = estado.get(serial, {})
            prev_online = prev.get("online", True)
            offline_desde = prev.get("offline_desde", None)
            alerta_enviada = prev.get("alerta_enviada", False)

            if not online:
                if prev_online:
                    offline_desde  = ahora
                    alerta_enviada = False
                    print(f"  [{serial}] Nuevo offline detectado — {grupo}")

                minutos_offline = int((ahora - offline_desde) / 60) if offline_desde else 0

                if minutos_offline >= UMBRAL_OFFLINE and not alerta_enviada and hora_en_rango():
                    horas  = minutos_offline // 60
                    minutos = minutos_offline % 60
                    msg = (
                        f"🚨 *Alerta EloView — Dispositivo offline*\n"
                        f"Serial: `{serial}`\n"
                        f"Grupo: {grupo}\n"
                        f"Contenido: {contenido}\n"
                        f"Tiempo offline: {horas}h {minutos}min\n"
                        f"Fecha: {ahora_str}"
                    )
                    send_telegram(msg)
                    alerta_enviada = True
                    print(f"  [{serial}] Alerta enviada — {horas}h {minutos}min offline")

                estado[serial] = {
                    "online": False,
                    "offline_desde": offline_desde,
                    "alerta_enviada": alerta_enviada,
                    "grupo": grupo
                }

            else:
                if not prev_online and offline_desde and hora_en_rango():
                    minutos_offline = int((ahora - offline_desde) / 60)
                    if minutos_offline >= UMBRAL_OFFLINE:
                        horas   = minutos_offline // 60
                        minutos = minutos_offline % 60
                        msg = (
                            f"✅ *Recuperación EloView*\n"
                            f"Serial: `{serial}`\n"
                            f"Grupo: {grupo}\n"
                            f"Estuvo offline: {horas}h {minutos}min\n"
                            f"Fecha: {ahora_str}"
                        )
                        send_telegram(msg)
                        print(f"  [{serial}] Recuperado tras {horas}h {minutos}min")

                estado[serial] = {"online": True, "offline_desde": None, "alerta_enviada": False, "grupo": grupo}

        guardar_estado(estado)

        offline_total = sum(1 for d in devs if not d.get("isOnline"))
        ok_total      = len(devs) - offline_total
        print(f"  Total: {len(devs)} | OK: {ok_total} | Offline: {offline_total}")

    except requests.exceptions.HTTPError as e:
        print(f"  ERROR HTTP: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")


def reporte_diario():
    print(f"\n[{datetime.now().strftime('%d/%m/%Y %H:%M')}] Generando reporte diario...")
    try:
        token = get_token()
        devs  = get_devices(token)
        estado = cargar_estado()
        ahora = time.time()

        total   = len(devs)
        ok      = sum(1 for d in devs if d.get("isOnline"))
        offline = total - ok
        pct     = round((ok / total) * 100) if total else 0
        fecha   = datetime.now().strftime("%d/%m/%Y %H:%M")

        msg = f"📊 *Reporte diario EloView*\n_{fecha}_\n\n"
        msg += f"*Resumen*\n"
        msg += f"• Total: {total} dispositivos\n"
        msg += f"• Operativos: {ok}\n"
        msg += f"• Offline: {offline}\n"
        msg += f"• Disponibilidad: {pct}%\n"

        problemas = []
        for d in devs:
            serial = d.get("serial", "")
            if not d.get("isOnline"):
                grupo  = d.get("groupName", "Sin grupo")
                prev   = estado.get(serial, {})
                offline_desde = prev.get("offline_desde", None)
                tiempo = ""
                if offline_desde:
                    mins  = int((ahora - offline_desde) / 60)
                    horas = mins // 60
                    resto = mins % 60
                    tiempo = f" — {horas}h {resto}min offline"
                problemas.append(f"• `{serial}` ({grupo}){tiempo}")

        if problemas:
            msg += f"\n*Dispositivos offline ({len(problemas)}):*\n"
            msg += "\n".join(problemas)
        else:
            msg += "\nTodos los dispositivos están operativos."

        send_telegram(msg)
        print(f"  Reporte enviado. {total} dispositivos, {offline} offline.")

    except Exception as e:
        print(f"  ERROR en reporte diario: {e}")


# ── Ejecución ─────────────────────────────────────────────
print("=" * 52)
print("  Monitor EloView — Arcoprime")
print(f"  Revisión cada {INTERVALO_MIN} min | Alerta a las {UMBRAL_OFFLINE} min offline")
print(f"  Horario de alertas: {HORA_INICIO}:00 - {HORA_FIN}:00")
print(f"  Reporte diario: {HORA_REPORTE}")
print("=" * 52)

run_monitor()
reporte_diario()

schedule.every(INTERVALO_MIN).minutes.do(run_monitor)
schedule.every().day.at(HORA_REPORTE).do(reporte_diario)

print(f"\nMonitor activo. Ctrl+C para detener.\n")

while True:
    schedule.run_pending()
    time.sleep(30)
