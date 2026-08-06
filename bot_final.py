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

# CONFIGURACIÓN DE SEGURIDAD CRIPTOGRÁFICA (Clave por defecto: admin123)
PASSWORD_HASH_SECRETO = os.getenv("DASHBOARD_PASSWORD_HASH", "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92")

# VARIABLES GLOBALES DINÁMICAS (Viven 100% en la memoria RAM de Render)
ESTADO_BOT = "PREDADOR"       # Modos permitidos: "OFF", "PREDADOR", "APLANAMIENTO"
LEVERAGE_MANUAL = 10          # Control dinámico de apalancamiento desde la web
ULTIMO_PRECIO_MONITOREO = 0.0 
ULTIMO_ATR_MONITOREO = 0.0    
CONTADOR_MECHAZOS = 0         

binance_client = None
if BINANCE_API_KEY and BINANCE_SECRET_KEY:
    try:
        binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    except Exception:
        binance_client = None

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

def calcular_atr_dinamico_flash(periodos=14):
    try:
        if not binance_client:
            return None
        klines = binance_client.futures_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_5MINUTE, limit=periodos + 1)
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

def evaluar_filtro_anti_mechazo_directo(precio_origen):
    time.sleep(3)
    try:
        if not binance_client:
            return False
        ticker = binance_client.futures_symbol_ticker(symbol=SYMBOL)
        precio_actual = float(ticker['price'])
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        return variacion_micro <= FILTRO_MECHAZO_MAX
    except Exception:
        return False

def ejecutar_caza_asimetrica(direccion, precio_mercado, fuerza_senal):
    global ULTIMO_ATR_MONITOREO
    if not binance_client:
        return "Cliente Binance no inicializado"
    try:
        leverage = LEVERAGE_MANUAL

        # ------------------------------------------------------------------
        # INTEGRACIÓN TOTAL DE AMBOS BOTS SEGÚN EL RÉGIMEN SELECCIONADO
        # ------------------------------------------------------------------
        if ESTADO_BOT == "APLANAMIENTO":
            # BOT 2 NUEVO: Configuración para exprimir días planos (Rangos Cortos de Reversión)
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
            # BOT 1 CLÁSICO: Depredador Flash Asimétrico por volatilidad de ATR
            atr = calcular_atr_dinamico_flash()
            ULTIMO_ATR_MONITOREO = atr if atr is not None else 0.0
            if atr is not None and atr > 0:
                multiplicador_tp = 2.0 if fuerza_senal >= 0.0040 else 1.5
                multiplicador_sl = 1.2 if fuerza_senal >= 0.0040 else 1.0
                distancia_tp = atr * multiplicador_tp
                distancia_sl = atr * multiplicador_sl
                precio_tp = round(precio_mercado + distancia_tp, 2) if direccion == "LONG" else round(precio_mercado - distancia_tp, 2)
                precio_sl = round(precio_mercado - distancia_sl, 2) if direccion == "LONG" else round(precio_mercado + distancia_sl, 2)
            else:
                tp_porcentaje = 0.0050 if fuerza_senal >= 0.0040 else 0.0022
                sl_porcentaje = 0.0030 if fuerza_senal >= 0.0040 else 0.0015
                precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 - tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2) if direccion == "LONG" else round(precio_mercado * (1 + sl_porcentaje), 2)
            tipo_gestion = "DINAMICA_ATR" if atr is not None else "FIJA_EMERGENCIA"

        binance_client.futures_change_leverage(symbol=SYMBOL, leverage=leverage)
        account = binance_client.futures_account()
        balance_disponible = float(account.get('availableBalance', 0))
        
        capital_operativo = balance_disponible * 0.25 if balance_disponible > 400.0 else balance_disponible * 0.10
        cantidad_nocional = (capital_operativo * leverage) / precio_mercado
        quantity = round(cantidad_nocional, 3) 
        if quantity <= 0:
            return "Capital insuficiente"

        side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
        side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

        binance_client.futures_create_order(symbol=SYMBOL, side=side_entrada, type=Client.FUTURE_ORDER_TYPE_MARKET, quantity=quantity)
        binance_client.futures_create_order(symbol=SYMBOL, side=side_salida, type='TAKE_PROFIT_MARKET', stopPrice=precio_tp, closePosition=True)
        binance_client.futures_create_order(symbol=SYMBOL, side=side_salida, type='STOP_MARKET', stopPrice=precio_sl, closePosition=True)

        # REGLA DE ORO MANDATORIA: Concatenación clásica sin llaves nativas o f-strings
        msg = "==================================\n   SISTEMA DEPREDADOR OPERATIVO   \n==================================\n• ACTIVO      : " + str(SYMBOL) + "\n• DIRECCION   : " + str(direccion) + "\n• APALANCAMIENTO: x" + str(leverage) + "\n----------------------------------\n• ENTRADA     : " + str(precio_mercado) + "\n• TAKE PROFIT : " + str(precio_tp) + "\n• STOP LOSS   : " + str(precio_sl) + "\n----------------------------------\n• FUERZA SENAL: " + str(fuerza_senal) + "\n• MODO ACTIVO : " + str(ESTADO_BOT) + "\n• GESTION     : " + tipo_gestion + "\n=================================="
        enviar_telegram(msg)
        return "Exito"
    except BinanceAPIException as e:
        enviar_telegram("ERROR BINANCE API " + str(e.message))
        return e.message
    except Exception as e:
        enviar_telegram("ERROR CRITICO " + str(e))
        return str(e)

def verificar_credenciales(password_plano):
    if not password_plano:
        return False
    hash_ingresado = hashlib.sha256(password_plano.encode('utf-8')).hexdigest()
    return hash_ingresado == PASSWORD_HASH_SECRETO

@app.route('/dashboard-secreto-watson', methods=['GET', 'POST'])
def dashboard_secreto():
    global ESTADO_BOT, LEVERAGE_MANUAL
    
    password_ingresado = request.args.get('auth') or request.headers.get('Authorization')
    if not verificar_credenciales(password_ingresado):
        return jsonify({"status": "error", "reason": "Acceso denegado. Auth invalida."}), 401

    if request.method == 'POST':
        data = request.get_json() or {}
        nuevo_modo = data.get("modo_bot")
        nuevo_leverage = data.get("leverage")
        
        if nuevo_modo in ["OFF", "PREDADOR", "APLANAMIENTO"]:
            ESTADO_BOT = nuevo_modo
        if nuevo_leverage:
            LEVERAGE_MANUAL = int(nuevo_leverage)
            
        return jsonify({"status": "success", "cambio_aplicado": ESTADO_BOT, "leverage_actual": LEVERAGE_MANUAL}), 200

    balance_usdt = 89.81
    global ULTIMO_PRECIO_MONITOREO
    try:
        if binance_client:
            account = binance_client.futures_account()
            balance_usdt = float(account.get('availableBalance', 0.0))
            ticker = binance_client.futures_symbol_ticker(symbol=SYMBOL)
            ULTIMO_PRECIO_MONITOREO = float(ticker['price'])
    except Exception:
        pass

    return jsonify({
        "SISTEMA": "WATSON CONTROL CENTER",
        "ESTRATEGIA_ACTIVA": ESTADO_BOT,
        "SALDO_DISPONIBLE_USDT": balance_usdt,
        "PRECIO_ETH_BASE": ULTIMO_PRECIO_MONITOREO,
        "MODULO_ATR_VOLATILIDAD": ULTIMO_ATR_MONITOREO,
        "ESCUDOS_MECHAZO_EVADIDOS": CONTADOR_MECHAZOS,
        "APALANCAMIENTO_BASE": LEVERAGE_MANUAL
    }), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    global ULTIMO_PRECIO_MONITOREO, CONTADOR_MECHAZOS
    if ESTADO_BOT == "OFF":
        return jsonify({"status": "paused", "reason": "La ejecucion del bot se encuentra congelada desde el Dashboard"}), 200
        
    data = request.get_json() or {}
    direccion = data.get("direccion")  
    fuerza = float(data.get("variacion", 0.0))  
    
