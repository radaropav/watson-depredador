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

# REGLA 3: Carga nativa del bypass regional desde tus variables de entorno de Render
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

def obtener_cliente_binance():
    if BINANCE_API_KEY and BINANCE_SECRET_KEY:
        try:
            # Inicialización del cliente usando la variable de entorno base de Binance si es necesario
            return Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        except Exception:
            return None
    return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not URL_TELEGRAM:
        return False
    
    # REGLA DE ORO MANDATORIA: Ensamblaje puro usando tu variable proxy URL_TELEGRAM externa
    # Se concatena de forma limpia mediante (+ str()) libre de llaves o f-strings
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
            high = float(klines[i])      # Índice 2: Precio Máximo
            low = float(klines[i])       # Índice 3: Precio Mínimo
            prev_close = float(klines[i-1]) # Índice 4: Precio de Cierre anterior
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
        leverage = LEVERAGE_MANUAL
        
        if ESTADO_BOT == "OFF":
            return "ORDEN BLOQUEADA: El bot se encuentra en MODO OFF"

        # ------------------------------------------------------------------
        # CONMUTADOR DE MOTORES ALGORÍTMICOS EN TIEMPO REAL (BOT DE EJECUCIÓN)
        # ------------------------------------------------------------------
        if ESTADO_BOT == "APLANAMIENTO":
            tp_porcentaje = 0.0025
            sl_porcentaje = 0.0018
            if direccion == "LONG":
                precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2)
            else:
                precio_tp = round(precio_mercado * (1 - tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 + sl_porcentaje), 2)
            tipo_gestion = "RANGOS_COMPRIMIDOS_REVERSION"
        else:
            atr = calcular_atr_dinamico_flash(client_local)
            ULTIMO_ATR_MONITOREO = atr if atr is not None else 0.0
            if atr is not None and atr > 0:
                multiplicador_tp = 2.0 if fuerza_senal >= 0.0040 else 1.5
                multiplicador_sl = 1.2 if fuerza_senal >= 0.0040 else 1.0
                distancia_tp = atr * multiplicador_tp
                distancia_sl = atr * multiplicador_sl
                precio_tp = round(precio_mercado + distancia_tp, 2) if direccion == "LONG" else round(precio_mercado - distancia_tp, 2)
                precio_sl = round(precio_mercado - distancia_sl, 2) if direccion == "LONG" else round(precio_mercado + distancia_sl, 2)
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
        cantidad_nocional = (capital_operativo * leverage) / precio_mercado
        quantity = round(cantidad_nocional, 3) 
        if quantity <= 0:
            return "Capital insuficiente"

        side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
        side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

        client_local.futures_create_order(symbol=SYMBOL, side=side_entrada, type=Client.FUTURE_ORDER_TYPE_MARKET, quantity=quantity)
        client_local.futures_create_order(symbol=SYMBOL, side=side_salida, type='TAKE_PROFIT_MARKET', stopPrice=precio_tp, closePosition=True)
        client_local.futures_create_order(symbol=SYMBOL, side=side_salida, type='STOP_MARKET', stopPrice=precio_sl, closePosition=True)

        # REGLA DE ORO MANDATORIA: Mensajería con concatenación clásica uniendo variables mediante (+ str())
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
    hash_ingresado = hashlib.sha256(password_plano.encode('utf-8')).hexdigest()
    return hash_ingresado == PASSWORD_HASH_SECRETO

# ------------------------------------------------------------------
# MOTOR DE AUTO-GENERACIÓN DE SEÑALES (BOT FUERTE ANALÍTICO CON CACHÉ)
# ------------------------------------------------------------------
def ciclo_monitoreo_automatico():
    global ULTIMO_PRECIO_MONITOREO
    # Retardo asíncrono para asegurar el correcto bindeo del proxy de Render
    time.sleep(10)
    enviar_telegram("SISTEMA WATSON: Conectividad proxy restaurada con exito. Canales activos.")
    
    while True:
        try:
            if ESTADO_BOT != "OFF":
                client_local = obtener_cliente_binance()
                if client_local:
                    ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
                    precio_actual = float(ticker['price'])
                    ULTIMO_PRECIO_MONITOREO = precio_actual
                    
                    # --- INTERFAZ NEUTRA DE TU ESTRATEGIA FUERTE ---
                    
            time.sleep(5)  
        except Exception:
            time.sleep(5)

# ------------------------------------------------------------------
# VÍAS DE ENTRADA (MÉTODOS WEB Y DASHBOARD CRIPTOGRÁFICO PLANO)
# ------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Watson Online", "estado_bot": ESTADO_BOT}), 200

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "estado_bot": ESTADO_BOT}), 200

@app.route('/webhook', methods=['POST'])
def webhook_receptor():
    global CONTADOR_MECHAZOS
    datos = request.get_json(force=True) or {}
    
    if "action" not in datos or "price" not in datos:
