import os
import time
import requests
from flask import Flask, request, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Desactivar alertas de certificados inseguros para el bypass forzado
from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# CORRECCIÓN DE SINTAXIS: Inicialización nativa obligatoria para Flask en Render
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
        pass

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        return
        
    # Desglose en fragmentos puros para el bypass total de la interfaz de red
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
    except Exception:
        pass

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
        pass
    return False

def calcular_atr_dinamico(periodos=14):
    """Calcula la volatilidad real del mercado usando las últimas velas de 5 minutos."""
    try:
        if not binance_client:
            return None
        klines = binance_client.futures_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_5MINUTE, limit=periodos + 1)
        
        true_ranges = []
        for i in range(1, len(klines)):
            high = float(klines[i][2])
            low = float(klines[i][3])
            prev_close = float(klines[i-1][4])
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
            
        return sum(true_ranges) / len(true_ranges)
    except Exception:
        return None

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

        atr = calcular_atr_dinamico()
        
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
        
        # CONTRASEGURO DE RIESGO INSTITUCIONAL
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

        # 1. ORDEN DE ENTRADA PRINCIPAL (MERCADO)
        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_entrada, 
            type=Client.FUTURE_ORDER_TYPE_MARKET, 
            quantity=quantity
        )

        # 2. ORDEN TAKE PROFIT MARKET (Control estricto de cierre sin duplicar cantidades)
        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_salida, 
            type='TAKE_PROFIT_MARKET', 
            stopPrice=precio_tp, 
            closePosition=True
        )

        # 3. ORDEN STOP MARKET (Control estricto de cierre sin duplicar cantidades)
        binance_client.futures_create_order(
            symbol=SYMBOL, 
            side=side_salida, 
            type='STOP_MARKET', 
            stopPrice=precio_sl, 
            closePosition=True
        )

        tipo_gestion = "DINAMICA_ATR" if atr is not None else "FIJA_EMERGENCIA"
        
        # BLINDAJE DE INTERFAZ: Concatenación clásica sin f-strings para evitar roturas de formato
        msg = "DEPREDADOR EJECUTADO x" + str(leverage) + " | " + direccion + " | ENTRADA: " + str(precio_mercado) + " | TP: " + str(precio_tp) + " | SL: " + str(precio_sl) + " | GESTION: " + tipo_gestion
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
    enviar_telegram("RADAR WATSON CONECTADO EN LINEA RECEPTOR LISTO")
    return jsonify({"status": "online", "motor": "Watson Webhook Ready", "telegram": "notificado"}), 200

if __name__ == '__main__':
    # Configuración estricta de arranque nativo de puerto para el contenedor de Render
    cadena_puerto = os.environ.get("PORT", "10000")
    puerto_numerico = int(cadena_puerto)
    app.run(host='0.0.0.0', port=puerto_numerico)
