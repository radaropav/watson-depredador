import os
import time
import requests
import hashlib
from flask import Flask, request, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Desactivar alertas de certificados inseguros para el bypass forzado
from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Inicialización nativa con guiones dobles para el mapa de rutas de Flask
app = Flask(__name__)

SYMBOL = "ETHUSDT"
TELEGRAM_CHAT_ID = "-1004335003036"
FILTRO_MECHAZO_MAX = 0.0018  

# EXTRACCIÓN SEGURA DE CREDENCIALES DESDE EL ENTORNO DE RENDER
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
PASSWORD_HASH_SECRETO = os.getenv("DASHBOARD_PASSWORD_HASH", "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92")

# VARIABLES GLOBALES DINÁMICAS (Viven 100% en la memoria RAM de Render)
ESTADO_BOT = "PREDADOR"       # Modos permitidos: "OFF", "PREDADOR", "APLANAMIENTO"
LEVERAGE_MANUAL = 10          # Control dinámico de apalancamiento desde la web
ULTIMO_PRECIO_MONITOREO = 0.0 
ULTIMO_ATR_MONITOREO = 0.0    
CONTADOR_MECHAZOS = 0         

def obtener_cliente_binance():
    if BINANCE_API_KEY and BINANCE_SECRET_KEY:
        try:
            return Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        except Exception:
            return None
    return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        return False
    # REGLA DE ORO MANDATORIA: Bypass regional fragmentado por variables individuales
    p = "https://"
    s = "api."
    r = "telegram"
    t = ".org"
    m = "/bot" + str(TELEGRAM_TOKEN) + "/sendMessage"
    url = p + s + r + t + m
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    try:
        requests.post(url, json=payload, headers=headers, timeout=4, verify=False)
        return True
    except Exception:
        return False

def calcular_atr_dinamico_flash(client_local, periodos=14):
    if not client_local:
        return None
    try:
        klines = client_local.futures_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_5MINUTE, limit=periodos + 1)
        true_ranges = []
        for i in range(1, len(klines)):
            high = float(klines[i])        # Índice 2: Precio Máximo de la vela
            low = float(klines[i])         # Índice 3: Precio Mínimo de la vela
            prev_close = float(klines[i-1]) # Índice 4: Precio de Cierre de la vela anterior
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        return sum(true_ranges) / len(true_ranges)
    except Exception:
        return None

def evaluar_filtro_anti_mechazo_directo(client_local, precio_origen):
    time.sleep(3)
    if not client_local:
        return False
    try:
        ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
        precio_actual = float(ticker['price'])
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        return variacion_micro <= FILTRO_MECHAZO_MAX
    except Exception:
        return False

def ejecutar_caza_asimetrica(client_local, direccion, precio_mercado, fuerza_senal):
    global ULTIMO_ATR_MONITOREO, ULTIMO_PRECIO_MONITOREO
    if not client_local:
        return "Cliente Binance no inicializado"
    try:
        ULTIMO_PRECIO_MONITOREO = precio_mercado
        
        # PILAR 2: INTERRUPTOR DE PÁNICO (MODO OFF)
        if ESTADO_BOT == "OFF":
            return "ORDEN BLOQUEADA: El bot se encuentra en MODO OFF"

        # PILAR 1: CONMUTADOR DE MOTORES ALGORÍTMICOS EN TIEMPO REAL
        if ESTADO_BOT == "APLANAMIENTO":
            # MOTOR NUEVO: Micro-salidas fijas cortas para la consolidación lateral de Asia
            tp_porcentaje = 0.0025
            sl_porcentaje = 0.0018
            precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 - tp_porcentaje), 2)
            precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 + sl_porcentaje), 2)
            tipo_gestion = "RANGOS_COMPRIMIDOS_REVERSION"
        else:
            # MOTOR CLÁSICO: Depredador Flash asimétrico por ATR dinámico
            atr = calcular_atr_dinamico_flash(client_local)
            ULTIMO_ATR_MONITOREO = atr if atr is not None else 0.0
            if atr is not None and atr > 0:
                multiplicador_tp = 2.0 if fuerza_senal >= 0.0040 else 1.5
                multiplicador_sl = 1.2 if fuerza_senal >= 0.0040 else 1.0
                distancia_tp = atr * multiplicador_tp
                distancia_sl = atr * multiplicador_sl
                precio_tp = round(precio_mercado + distancia_tp, 2) if direccion == "LONG" else round(precio_mercado - distancia_tp, 2)
                precio_sl = round(precio_mercado - distancia_sl, 2) if direccion == "LONG" else round(precio_mercado + distancia_sl, 2)
                tipo_gestion = "DEPREDADOR_DINAMICO_ATR"
            else:
                # CORRECCIÓN DE SINTAXIS ABIERTA DE LA SESIÓN PASADA
                tp_porcentaje = 0.0050 if fuerza_senal >= 0.0040 else 0.0035
                sl_porcentaje = 0.0030 if fuerza_senal >= 0.0040 else 0.0020
                precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 - tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 + sl_porcentaje), 2)
                tipo_gestion = "FALLBACK_PREDADOR_FIJO"

        # REGLA DE ORO: Mensajería con concatenación clásica pura uniendo variables mediante (+ str())
        mensaje = "Modo: " + str(tipo_gestion) + " - Dir: " + str(direccion) + " - TP: " + str(precio_tp) + " - SL: " + str(precio_sl)
        enviar_telegram(mensaje)
        return mensaje
    except Exception as e:
        return "Error en ejecucion: " + str(e)

# ------------------------------------------------------------------
# PILAR 3: LIVE DATA FEED CENTER (WEBHOOK Y DASHBOARD)
# ------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    # SOLUCIÓN AL ERROR 404: Ruta raíz obligatoria para el proxy inverso de Render
    return jsonify({"status": "Watson Online", "estado_bot": ESTADO_BOT}), 200

@app.route('/webhook', methods=['POST'])
def webhook_receptor():
    global CONTADOR_MECHAZOS
    try:
        datos = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "reason": "JSON invalido"}), 400
        
    if not datos or "action" not in datos or "price" not in datos:
        return jsonify({"status": "error", "reason": "Faltan parametros criticos"}), 400
        
    direccion = str(datos.get("action")).upper() 
    precio_origen = float(datos.get("price"))
    fuerza_senal = float(datos.get("fuerza", 0.0))
    
    client_local = obtener_cliente_binance()
    
    if not evaluar_filtro_anti_mechazo_directo(client_local, precio_origen):
        CONTADOR_MECHAZOS = CONTADOR_MECHAZOS + 1
        enviar_telegram("Alerta bloqueada por Filtro Anti-Mechazo en precio: " + str(precio_origen))
        return jsonify({"status": "bloqueado", "reason": "Filtro anti-mechazo activado"}), 200
        
    resultado = ejecutar_caza_asimetrica(client_local, direccion, precio_origen, fuerza_senal)
    return jsonify({"status": "procesado", "resultado": resultado}), 200

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard_control():
    global ESTADO_BOT, LEVERAGE_MANUAL
    password_input = request.headers.get("Authorization") or request.args.get("pass")
    if not password_input:
        return jsonify({"error": "No autorizado"}), 401
        
    hash_input = hashlib.sha256(str(password_input).encode('utf-8')).hexdigest()
    if hash_input != PASSWORD_HASH_SECRETO:
        return jsonify({"error": "Credenciales incorrectas"}), 403
        
    if request.method == 'POST':
        try:
            datos = request.get_json(force=True)
            if "nuevo_modo" in datos:
                modo = str(datos["nuevo_modo"]).upper()
                if modo in ["OFF", "PREDADOR", "APLANAMIENTO"]:
                    ESTADO_BOT = modo
            if "nuevo_leverage" in datos:
                LEVERAGE_MANUAL = int(datos["nuevo_leverage"])
        except Exception:
            pass
            
    return jsonify({
        "activo": SYMBOL,
        "estado_actual_bot": ESTADO_BOT,
        "leverage_actual": LEVERAGE_MANUAL,
        "ultimo_precio_visto": ULTIMO_PRECIO_MONITOREO,
        "ultimo_atr_calculado": ULTIMO_ATR_MONITOREO,
        "mechazos_bloqueados": CONTADOR_MECHAZOS
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "estado_bot": ESTADO_BOT}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
