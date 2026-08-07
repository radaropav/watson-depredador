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

# VARIABLES GLOBALES DINÁMICAS (Viven 100% en la memoria RAM de Render)
ESTADO_BOT = "PREDADOR"       # Modos permitidos: "OFF", "PREDADOR", "APLANAMIENTO"
LEVERAGE_MANUAL = 10          # Control dinámico de apalancamiento desde la web
ULTIMO_PRECIO_MONITOREO = 0.0 
ULTIMO_ATR_MONITOREO = 0.0    
CONTADOR_MECHAZOS = 0         

# Almacenamiento local para el algoritmo de ruptura autónoma de 3 velas
HISTORIAL_PRECIOS_MAESTRO = []

# Cerrojeros de inicialización atómica en memoria RAM
BOT_INICIALIZADO = False
BLOQUEO_ARRANQUE = threading.Lock()

def obtener_cliente_binance():
    if BINANCE_API_KEY and BINANCE_SECRET_KEY:
        try: return Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        except Exception: return None
    return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN: return False
    protocolo = "https://"
    sub = "api."
    raiz = "telegram"
    tld = ".org"
    ruta_metodo = "/bot" + str(TELEGRAM_TOKEN) + "/sendMessage"
    url = protocolo + sub + raiz + tld + ruta_metodo
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=12, verify=False)
        return True
    except Exception: return False

def calcular_atr_dinamico_flash(client_local, periodos=14):
    if not client_local: return None
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
    except Exception: return None

def evaluar_filtro_anti_mechazo_directo(client_local, precio_origen):
    time.sleep(3)
    if not client_local: return False
    try:
        ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
        precio_actual = float(ticker['price'])
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        return variacion_micro <= FILTRO_MECHAZO_MAX
    except Exception: return False

def ejecutar_caza_asimetrica(client_local, direccion, precio_mercado, fuerza_senal):
    global ULTIMO_ATR_MONITOREO
    if not client_local: return "Cliente Binance no inicializado"
    try:
        leverage = 20 if fuerza_senal >= 0.0040 else LEVERAGE_MANUAL
        if ESTADO_BOT == "OFF": return "ORDEN BLOQUEADA: El bot se encuentra en MODO OFF"

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
        if quantity <= 0: return "Capital insuficiente"

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

# ------------------------------------------------------------------
# MOTOR DE TRADING AUTÓNOMO E INYECTOR HISTÓRICO
# ------------------------------------------------------------------
def ciclo_monitoreo_automatico():
    global ULTIMO_PRECIO_MONITOREO, CONTADOR_MECHAZOS, HISTORIAL_PRECIOS_MAESTRO
    while True:
        try:
            if ESTADO_BOT != "OFF":
                client_local = obtener_cliente_binance()
                if client_local:
                    ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
                    precio_actual = float(ticker['price'])
                    ULTIMO_PRECIO_MONITOREO = precio_actual
                    
                    HISTORIAL_PRECIOS_MAESTRO.append(precio_actual)
                    if len(HISTORIAL_PRECIOS_MAESTRO) > 12: HISTORIAL_PRECIOS_MAESTRO.pop(0)
                    
                    if len(HISTORIAL_PRECIOS_MAESTRO) >= 6:
                        maximo_canal = max(HISTORIAL_PRECIOS_MAESTRO[:-1])
                        minimo_canal = min(HISTORIAL_PRECIOS_MAESTRO[:-1])
                        
                        if precio_actual > maximo_canal:
                            fuerza = abs((precio_actual - maximo_canal) / maximo_canal)
                            if evaluar_filtro_anti_mechazo_directo(client_local, precio_actual):
                                ordenar = ejecutar_caza_asimetrica(client_local, "LONG", precio_actual, fuerza)
                            else:
                                CONTADOR_MECHAZOS = CONTADOR_MECHAZOS + 1
                                enviar_telegram("DISPARO_CANCELADO > MOTIVO: MECHAZO EN BREAKOUT LONG")
                        
                        elif precio_actual < minimo_canal:
                            fuerza = abs((minimo_canal - precio_actual) / minimo_canal)
                            if evaluar_filtro_anti_mechazo_directo(client_local, precio_actual):
                                ordenar = ejecutar_caza_asimetrica(client_local, "SHORT", precio_actual, fuerza)
                            else:
                                CONTADOR_MECHAZOS = CONTADOR_MECHAZOS + 1
                                enviar_telegram("DISPARO_CANCELADO > MOTIVO: MECHAZO EN BREAKOUT SHORT")
            time.sleep(5)
        except Exception: time.sleep(5)

def ejecutar_arranque_atomico_secreto():
    global BOT_INICIALIZADO
    if not BOT_INICIALIZADO:
        with BLOQUEO_ARRANQUE:
            if not BOT_INICIALIZADO:
                BOT_INICIALIZADO = True
                enviar_telegram("SISTEMA WATSON: Conectividad proxy restaurada con exito. Obra maestra online.")
                threading.Thread(target=ciclo_monitoreo_automatico, daemon=True).start()

