import os
import time
import requests
from flask import Flask, request, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException

app = Flask(__name__)

SYMBOL = "ETHUSDT"
TELEGRAM_TOKEN = "8991347344:AAHDSp718hsWqd8uxceBN9D0_n5ZXqR6V1Q"
TELEGRAM_CHAT_ID = "-1004335003036"

FILTRO_MECHAZO_MAX = 0.0018  

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

binance_client = None
if BINANCE_API_KEY and BINANCE_SECRET_KEY:
    try:
        binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    except Exception:
        pass

def enviar_telegram(mensaje):
    url = "https://telegram.org" + TELEGRAM_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=4)
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

def ejecutar_caza_asimetrica(direccion, precio_mercado, fuerza_senal):
    if not binance_client:
        return "Cliente Binance no inicializado"

    try:
        if fuerza_senal >= 0.0040:
            leverage = 20
            tp_porcentaje = 0.0050  
            sl_porcentaje = 0.0030  
        else:
            leverage = 10
            tp_porcentaje = 0.0022  
            sl_porcentaje = 0.0015  

        binance_client.futures_change_leverage(symbol=SYMBOL, leverage=leverage)

        account = binance_client.futures_account()
        balance_disponible = float(account.get('availableBalance', 0))
        
        capital_operativo = balance_disponible * 0.50 if balance_disponible > 400.0 else balance_disponible * 1.00
        
        cantidad_nocional = (capital_operativo * leverage) / precio_mercado
        quantity = round(cantidad_nocional, 3)
        
        if quantity <= 0:
            return "Capital insuficiente para el lote"

        side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
        side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

        binance_client.futures_create_order(
            symbol=SYMBOL, side=side_entrada, type=Client.FUTURE_ORDER_TYPE_MARKET, quantity=quantity
        )

        if direccion == "LONG":
            precio_tp = round(precio_mercado * (1 + tp_porcentaje), 2)
            precio_sl = round(precio_mercado * (1 - sl_porcentaje), 2)
        else:
            precio_tp = round(precio_mercado * (1 - tp_porcentaje), 2)
            precio_sl = round(precio_mercado * (1 + sl_porcentaje), 2)

        binance_client.futures_create_order(
            symbol=SYMBOL, side=side_salida, type='TAKE_PROFIT_MARKET', stopPrice=precio_tp, closePosition=True, reduceOnly=True
        )
        binance_client.futures_create_order(
            symbol=SYMBOL, side=side_salida, type='STOP_MARKET', stopPrice=precio_sl, closePosition=True, reduceOnly=True
        )

        msg = f"🦅 *DEPREDADOR EJECUTADO* (x{leverage})\n💥 Accion: *{direccion}*\n💰 Precio Entrada: ${precio_mercado}\n🎯 TP Objetivo: ${precio_tp}\n🛑 SL Seguridad: ${precio_sl}"
        enviar_telegram(msg)
        return "Exito"

    except BinanceAPIException as e:
        enviar_telegram(f"❌ *API Binance:* {e.message}")
        return e.message
    except Exception as e:
        enviar_telegram(f"❌ *Error:* {str(e)}")
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
        enviar_telegram(f"⚠️ *Disparo Cancelado:* Mechazo o Inestabilidad detectada en {SYMBOL}.")
        return jsonify({"status": "cancelado", "reason": "Filtro anti-mechazos activado"}), 200

    resultado = ejecutar_caza_asimetrica(direccion, precio_actual, fuerza)
    return jsonify({"status": "procesado", "resultado": resultado}), 200

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return jsonify({"status": "live", "service": "webhook_active"}), 200

@app.route('/health', methods=['GET'])
def health():
    # AUDITORIA OBLIGATORIA: Forza el disparo de Telegram en cada pulso de red
    enviar_telegram("🦅 *Radar Watson Conectado*\n\nEstado: Receptor Webhook En Linea\nEstructura: Nivel 2 Calibrado")
    return jsonify({"status": "online", "motor": "Watson Webhook Ready", "telegram": "notificado"}), 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
