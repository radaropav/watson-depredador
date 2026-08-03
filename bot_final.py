import os
import time
import threading
import requests
from flask import Flask, request, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance.streams import BinanceSocketManager

# Desactivar alertas de certificados inseguros para el bypass forzado
from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Inicialización nativa con guiones dobles para Flask
app = Flask(__name__)

SYMBOL = "ETHUSDT"
TELEGRAM_CHAT_ID = "-1004335003036"
FILTRO_MECHAZO_MAX = 0.0018  

# EXTRACCIÓN SEGURA DE CREDENCIALES DESDE EL ENTORNO DE RENDER
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# MEMORIA RAM EN TIEMPO REAL (WEBSOCKET DATA)
PRECIO_EN_VIVO = 0.0
HISTORIAL_VELAS = []

binance_client = None
if BINANCE_API_KEY and BINANCE_SECRET_KEY:
    try:
        binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    except Exception:
        pass

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        return False
        
    protocolo = "https://"
    sub = "api."
    raiz = "telegram"
    tld = ".org"
    ruta_metodo = "/bot" + TELEGRAM_TOKEN + "/sendMessage"
    url = protocolo + sub + raiz + tld + ruta_metodo
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }
    
    try:
        requests.post(url, json=payload, headers=headers, timeout=5, verify=False)
        return True
    except Exception:
        return False

def manejar_flujo_websocket():
    """Hilo secundario que corre 24/7 leyendo el mercado de Binance en tiempo real."""
    global PRECIO_EN_VIVO, HISTORIAL_VELAS
    if not binance_client:
        return

    while True:
        try:
            klines = binance_client.futures_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_5MINUTE, limit=15)
            
            HISTORIAL_VELAS = []
            for k in klines[:-1]:
                HISTORIAL_VELAS.append([
                    k[0],
                    float(k[1]),
                    float(k[2]),
                    float(k[3]),
                    float(k[4]),
                    float(k[5])
                ])
            
            bsm = BinanceSocketManager(binance_client)
            
            stream_ticker = SYMBOL.lower() + "@ticker"
            stream_kline = SYMBOL.lower() + "@kline_5m"
            
            socket_stream = bsm.multiplex_socket([stream_ticker, stream_kline])
            
            with socket_stream as stream:
                while True:
                    res = stream.recv()
                    if not res:
                        continue
                        
                    stream_name = res.get('stream', '')
                    data = res.get('data', {})
                    
                    if 'ticker' in stream_name:
                        PRECIO_EN_VIVO = float(data.get('c', 0.0))
                        
                    elif 'kline' in stream_name:
                        kline_data = data.get('k', {})
                        es_vela_cerrada = kline_data.get('x', False)
                        
                        if es_vela_cerrada:
                            nueva_vela = [
                                kline_data.get('t'),
                                float(kline_data.get('o', 0.0)),
                                float(kline_data.get('h', 0.0)),
                                float(kline_data.get('l', 0.0)),
                                float(kline_data.get('c', 0.0)),
                                float(kline_data.get('v', 0.0))
                            ]
                            HISTORIAL_VELAS.append(nueva_vela)
                            if len(HISTORIAL_VELAS) > 15:
                                HISTORIAL_VELAS.pop(0)
                                
        except Exception:
            time.sleep(5)

def calcular_atr_dinamico_websocket(periodos=14):
    """Calcula la volatilidad usando las velas 100% pre-cargadas en la memoria RAM."""
    try:
        if len(HISTORIAL_VELAS) < periodos:
            return None
            
        true_ranges = []
        velas_analisis = HISTORIAL_VELAS[-periodos-1:]
        
        for i in range(1, len(velas_analisis)):
            # CORRECCIÓN INDUSTRIAL: Acceso estricto por índices de sublista
            high = velas_analisis[i][2]
            low = velas_analisis[i][3]
            prev_close = velas_analisis[i-1][4]
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
            
        return sum(true_ranges) / len(true_ranges)
    except Exception:
        return None

def evaluar_filtro_anti_mechazo_directo(precio_origen):
    time.sleep(3)
    try:
        precio_actual = PRECIO_EN_VIVO if PRECIO_EN_VIVO > 0 else precio_origen
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        return variacion_micro <= FILTRO_MECHAZO_MAX
    except Exception:
        pass
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

        atr = calcular_atr_dinamico_websocket()
        
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
            return "Capital insuficiente para el lote minimo de ETH"

        side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
        side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_entrada, 
            type=Client.FUTURE_ORDER_TYPE_MARKET, 
            quantity=quantity
        )

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
        
        msg = "DEPREDADOR EJECUTADO x" + str(leverage) + " | " + direccion + " | ENTRADA: " + str(precio_mercado) + " | TP: " + str(precio_tp) + " | SL: " + str(precio_sl) + " | GESTION: " + tipo_gestion + " (F2_STREAM)"
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

    precio_actual = PRECIO_EN_VIVO
    
    if precio_actual == 0.0:
        try:
            ticker = binance_client.futures_symbol_ticker(symbol=SYMBOL)
            precio_actual = float(ticker['price'])
        except Exception:
            return jsonify({"status": "error", "reason": "No se pudo obtener precio base de Binance"}), 500

    if not evaluar_filtro_anti_mechazo_directo(precio_actual):
        enviar_telegram("DISPARO CANCELADO MECHAZO DETECTADO EN ETH")
        return jsonify({"status": "cancelado", "reason": "Filtro anti-mechazos activado"}), 200

    resultado = ejecutar_caza_asimetrica(direccion, precio_actual, fuerza)
    return jsonify({"status": "procesado", "resultado": resultado}), 200

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return jsonify({"status": "live", "service": "webhook_active"}), 200

@app.route('/health', methods=['GET'])
def health():
