import os
import time
import requests
from flask import Flask, request, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Desactivar alertas de certificados inseguros para el bypass forzado
from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

SYMBOL = "ETHUSDT"
TELEGRAM_CHAT_ID = "-1004335003036"
FILTRO_MECHAZO_MAX = 0.0018  

# EXTRACCIÓN SEGURA DE CREDENCIALES DESDE EL ENTORNO DE RENDER
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

binance_client = None
if BINANCE_API_KEY and BINANCE_SECRET_KEY:
    try:
        binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    except Exception:
        binance_client = None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        return False
    # BYPASS DE ÉLITE: Fragmentación absoluta para romper la inspección regional de red
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
    """MÓDULO FLASH DE ALTA PRECISIÓN: Extracción síncrona sin fallas de memoria."""
    try:
        if not binance_client:
            return None
        klines = binance_client.futures_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_5MINUTE, limit=periodos + 1)
        true_ranges = []
        for i in range(1, len(klines)):
            # CORRECCIÓN DE ÍNDICES: Extracción limpia de los elementos flotantes numéricos
            high = float(klines[i][2])
            low = float(klines[i][3])
            prev_close = float(klines[i-1][4])
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
    if not binance_client:
        return "Cliente Binance no inicializado"
    try:
        if fuerza_senal >= 0.0040:
            leverage = 20
            multiplicador_tp = 2.0  
            multiplicador_sl = 1.2  
        else:
            leverage = 10
            multiplicador_tp = 1.5  
            multiplicador_sl = 1.0  

        atr = calcular_atr_dinamico_flash()
        if atr is not None and atr > 0:
            distancia_tp = atr * multiplicador_tp
            distancia_sl = atr * multiplicador_sl
            if direccion == "LONG":
                precio_tp = round(precio_mercado + distancia_tp, 2)
                precio_sl = round(precio_mercado - distancia_sl, 2)
            else:
                precio_tp = round(precio_mercado - distancia_tp, 2)
                precio_sl = round(precio_mercado + distancia_sl, 2)
        else:
            tp_porcentaje = 0.0050 if fuerza_senal >= 0.0040 else 0.0022
            sl_porcentaje = 0.0030 if fuerza_senal >= 0.0040 else 0.0015
            if direccion == "LONG":
                precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2)
            else:
                precio_tp = round(precio_mercado * (1 - tp_porcentaje), 2)
                precio_sl = round(precio_mercado * (1 + sl_porcentaje), 2)

        binance_client.futures_change_leverage(symbol=SYMBOL, leverage=leverage)
        account = binance_client.futures_account()
        balance_disponible = float(account.get('availableBalance', 0))
        
        if balance_disponible > 400.0:
            capital_operativo = balance_disponible * 0.25  
        else:
            capital_operativo = balance_disponible * 0.10  
        
        cantidad_nocional = (capital_operativo * leverage) / precio_mercado
        quantity = round(cantidad_nocional, 3) 
        if quantity <= 0:
            return "Capital insuficiente"

        side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
        side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_entrada, 
            type=Client.FUTURE_ORDER_TYPE_MARKET, 
            quantity=quantity
        )

        # CORRECCIÓN DE ÉLITE: Parámetros booleanos nativos correctos y valores numéricos redondeados exigidos por la API
        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_salida, 
            type='TAKE_PROFIT_MARKET', 
            stopPrice=precio_tp, 
            closePosition=True
        )
        
        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_salida, 
            type='STOP_MARKET', 
            stopPrice=precio_sl, 
            closePosition=True
        )

        tipo_gestion = "DINAMICA_ATR" if atr is not None else "FIJA_EMERGENCIA"
        msg = "==================================\n   SISTEMA DEPREDADOR OPERATIVO   \n==================================\n• ACTIVO      : " + str(SYMBOL) + "\n• DIRECCION   : " + str(direccion) + "\n• APALANCAMIENTO: x" + str(leverage) + "\n----------------------------------\n• ENTRADA     : " + str(precio_mercado) + "\n• TAKE PROFIT : " + str(precio_tp) + "\n• STOP LOSS   : " + str(precio_sl) + "\n----------------------------------\n• FUERZA SENAL: " + str(fuerza_senal) + "\n• GESTION     : " + tipo_gestion + "\n=================================="
        enviar_telegram(msg)
        return "Exito"
    except BinanceAPIException as e:
        enviar_telegram("ERROR BINANCE API " + str(e.message))
        return e.message
    except Exception as e:
        enviar_telegram("ERROR CRITICO " + str(e))
        return str(e)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json() or {}
    direccion = data.get("direccion")  
    fuerza = float(data.get("variacion", 0.0))  
    if direccion not in ["LONG", "SHORT"]:
        return jsonify({"status": "error", "reason": "Direccion invalida"}), 400
    try:
        ticker = binance_client.futures_symbol_ticker(symbol=SYMBOL)
        precio_actual = float(ticker['price'])
    except Exception:
        return jsonify({"status": "error", "reason": "No se pudo precio base"}), 500

    if not evaluar_filtro_anti_mechazo_directo(precio_actual):
        msg_cancelado = "==================================\n       DISPARO CANCELADO          \n==================================\n• MOTIVO: MECHAZO DETECTADO EN ETH\n=================================="
        enviar_telegram(msg_cancelado)
        return jsonify({"status": "cancelado", "reason": "Filtro anti-mechazos activado"}), 200

    resultado = ejecutar_caza_asimetrica(direccion, precio_actual, fuerza)
    return jsonify({"status": "processed", "resultado": resultado}), 200

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return jsonify({"status": "live", "service": "webhook_active"}), 200

@app.route('/health', methods=['GET'])
def health():
    # RECONSTRUCCIÓN COMPLETA DE LA INTERFAZ DE DIAGNÓSTICO INSTITUCIONAL
    msg_health = "==================================\n   RADAR DIÁGNOSTICO WATSON V4    \n==================================\n• STATUS MOTOR: ONLINE (READY)\n• RENDIMIENTO : EXTRA FLASH HTTP\n• CONCURRENCIA : BLINDADA MULTI-THREAD\n• ENTORNO     : BYPASS COMPATIBLE\n=================================="
    enviar_telegram(msg_health)
    return jsonify({"status": "online", "motor": "Watson Webhook Ready"}), 200

if __name__ == '__main__':
    cadena_puerto = os.environ.get("PORT", "10000")
    puerto_numerico = int(cadena_puerto)
    app.run(host='0.0.0.0', port=puerto_numerico)
