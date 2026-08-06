import os
import time
import requests
import hashlib
import threading
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

# EXTRACCIÓN SEGURA DE CREDENCIALES Y PROXYS DESDE EL ENTORNO DE RENDER
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

URL_BINANCE = os.getenv("URL_BINANCE")
URL_CRYPTO = os.getenv("URL_CRYPTO")
URL_TELEGRAM = os.getenv("URL_TELEGRAM")

PASSWORD_HASH_SECRETO = os.getenv("DASHBOARD_PASSWORD_HASH", "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92")

# VARIABLES GLOBALES DINÁMICAS (Viven 100% en la memoria RAM de Render)
ESTADO_BOT = "PREDADOR"       # Modos permitidos: "OFF", "PREDADOR", "APLANAMIENTO"
LEVERAGE_MANUAL = 10          # Control dinámico de apalancamiento desde la web
ULTIMO_PRECIO_MONITOREO = 0.0 
ULTIMO_ATR_MONITOREO = 0.0    
CONTADOR_MECHAZOS = 0         

# Cerrojeros de inicialización aplanados en memoria RAM
BOT_INICIALIZADO = False
BLOQUEO_ARRANQUE = threading.Lock()

def obtener_cliente_binance():
    if BINANCE_API_KEY and BINANCE_SECRET_KEY:
        try:
            return Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        except Exception:
            return None
    return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not URL_TELEGRAM:
        return False
    url = str(URL_TELEGRAM) + "/bot" + str(TELEGRAM_TOKEN) + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    try:
        requests.post(url, json=payload, headers=headers, timeout=12, verify=False)
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
            high = float(klines[i])
            low = float(klines[i])
            prev_close = float(klines[i-1])
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
    global ULTIMO_ATR_MONITOREO
    if not client_local:
        return "Cliente Binance no inicializado"
    try:
        leverage = 20 if fuerza_senal >= 0.0040 else 10
        if ESTADO_BOT == "OFF":
            return "ORDEN BLOQUEADA: El bot se encuentra en MODO OFF"

        if ESTADO_BOT == "APLANAMIENTO":
            tp_porcentaje = 0.0025
            sl_porcentaje = 0.0018
            precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 - tp_porcentaje), 2)
            precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 + sl_porcentaje), 2)
            tipo_gestion = "RANGOS_COMPRIMIDOS_REVERSION"
        else:
            atr = calcular_atr_dinamico_flash(client_local)
            ULTIMO_ATR_MONITOREO = atr if atr is not None else 0.0
            if atr is not None and atr > 0:
                multiplicador_tp = 2.0 if fuerza_senal >= 0.0040 else 1.5
                multiplicador_sl = 1.2 if fuerza_senal >= 0.0040 else 1.0
                precio_tp = round(precio_mercado + (atr * multiplicador_tp), 2) if direccion == "LONG" else round(precio_mercado - (atr * multiplicador_tp), 2)
                precio_sl = round(precio_mercado - (atr * multiplicador_sl), 2) if direccion == "LONG" else round(precio_mercado + (atr * multiplicador_sl), 2)
                tipo_gestion = "DINAMICA_ATR"
            else:
                tp_porcentaje = 0.0050 if fuerza_senal >= 0.0040 else 0.0022
                sl_porcentaje = 0.0030 if fuerza_senal >= 0.0040 else 0.0015
                precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 - tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 + sl_porcentaje), 2)
                tipo_gestion = "FIJA_EMERGENCIA"

        client_local.futures_change_leverage(symbol=SYMBOL, leverage=leverage)
        account = client_local.futures_account()
        balance_disponible = float(account.get('availableBalance', 0))
        capital_operativo = balance_disponible * 0.25 if balance_disponible > 400.0 else balance_disponible * 0.10
        quantity = round((capital_operativo * leverage) / precio_mercado, 3)
        if quantity <= 0:
            return "Capital insuficiente"

        side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
        side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

        client_local.futures_create_order(symbol=SYMBOL, side=side_entrada, type=Client.FUTURE_ORDER_TYPE_MARKET, quantity=quantity)
        client_local.futures_create_order(symbol=SYMBOL, side=side_salida, type='TAKE_PROFIT_MARKET', stopPrice=precio_tp, closePosition=True)
        client_local.futures_create_order(symbol=SYMBOL, side=side_salida, type='STOP_MARKET', stopPrice=precio_sl, closePosition=True)

        msg = "==================================\n   SISTEMA DEPREDADOR OPERATIVO   \n==================================\n• ACTIVO      : " + str(SYMBOL) + "\n• DIRECCION   : " + str(direccion) + "\n• APALANCAMIENTO: x" + str(leverage) + "\n----------------------------------\n• ENTRADA     : " + str(precio_mercado) + "\n• TAKE PROFIT : " + str(precio_tp) + "\n• STOP LOSS   : " + str(precio_sl) + "\n----------------------------------\n• FUERZA SENAL: " + str(fuerza_senal) + "\n• MODO ACTIVO : " + str(ESTADO_BOT) + "\n• GESTION     : " + tipo_gestion + "\n=================================="
        enviar_telegram(msg)
        return "Exito"
    except BinanceAPIException as e:
        enviar_telegram("BINANCE_API_ERROR " + str(e.message))
        return e.message
    except Exception as e:
        enviar_telegram("ERROR CRITICO " + str(e))
        return str(e)

def verificar_credenciales(password_plano):
    if not password_plano:
        return False
    return hashlib.sha256(password_plano.encode('utf-8')).hexdigest() == PASSWORD_HASH_SECRETO

# ------------------------------------------------------------------
# MOTOR DE AUTO-GENERACIÓN DE SEÑALES (BOT FUERTE ANALÍTICO)
# ------------------------------------------------------------------
def ciclo_monitoreo_automatico():
    global ULTIMO_PRECIO_MONITOREO
    while True:
        try:
            if ESTADO_BOT != "OFF":
                client_local = obtener_cliente_binance()
                if client_local:
                    ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
                    ULTIMO_PRECIO_MONITOREO = float(ticker['price'])
            time.sleep(5)
        except Exception:
            time.sleep(5)

def ejecutar_arranque_atomico_secreto():
    global BOT_INICIALIZADO
    if not BOT_INICIALIZADO:
        with BLOQUEO_ARRANQUE:
            if not BOT_INICIALIZADO:
                BOT_INICIALIZADO = True
                enviar_telegram("SISTEMA WATSON: Conectividad proxy restaurada con exito. Canales activos.")
                threading.Thread(target=ciclo_monitoreo_automatico, daemon=True).start()

# ------------------------------------------------------------------
# VÍAS DE ENTRADA (MÉTODOS WEB Y RECEPTOR DE SEÑALES FORMATO MANDATORIO)
# ------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    ejecutar_arranque_atomico_secreto()
    return jsonify({"status": "Watson Online", "estado_bot": ESTADO_BOT}), 200

@app.route('/health', methods=['GET'])
def health_check():
    ejecutar_arranque_atomico_secreto()
    return jsonify({"status": "healthy", "estado_bot": ESTADO_BOT}), 200

@app.route('/webhook', methods=['POST'])
def webhook_receptor():
    global CONTADOR_MECHAZOS, ULTIMO_PRECIO_MONITOREO
    ejecutar_arranque_atomico_secreto()
    datos = request.get_json(force=True) or {}
    
    direccion = str(datos.get("direccion", "")).upper()
    fuerza_senal = float(datos.get("variacion", 0.0))
    
    client_local = obtener_cliente_binance()
    ticker = client_local.futures_symbol_ticker(symbol=SYMBOL) if client_local else {"price": "0.0"}
    precio_origen = float(ticker.get("price", 0.0))
    ULTIMO_PRECIO_MONITOREO = precio_origen
    
    if direccion not in ["LONG", "SHORT"] or precio_origen <= 0:
        return jsonify({"status": "error", "reason": "Parametros invalidos"}), 400
        
    if not evaluar_filtro_anti_mechazo_directo(client_local, precio_origen):
        CONTADOR_MECHAZOS = CONTADOR_MECHAZOS + 1
        enviar_telegram("DISPARO_CANCELADO > MOTIVO: MECHAZO DETECTADO EN ETH")
