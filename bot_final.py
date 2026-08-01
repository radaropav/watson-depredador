import os
import time
import requests
from flask import Flask, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException

app = Flask(__name__)

SYMBOL = "ETHUSDT"
TELEGRAM_TOKEN = "8991347344:AAHDSp718hsWqd8uxceBN9D0_n5ZXqR6V1Q"
TELEGRAM_CHAT_ID = "-1004335003036"

UMBRAL_MIN_PRECIO = 0.0012   
UMBRAL_MIN_OI = 0.0025       
FILTRO_MECHAZO_MAX = 0.0018  

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

binance_client = None
if BINANCE_API_KEY and BINANCE_SECRET_KEY:
    try:
        binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY, requests_params={"timeout": 5})
    except Exception:
        pass

def enviar_telegram(mensaje):
    url = "https://telegram.org" + TELEGRAM_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=4)
    except Exception:
        pass

def consultar_mercado_futuros():
    try:
        if not binance_client:
            return None, None
        ticker = binance_client.futures_symbol_ticker(symbol=SYMBOL)
        oi_data = binance_client.futures_open_interest(symbol=SYMBOL)
        return float(ticker['price']), float(oi_data['openInterest'])
    except Exception as e:
        print(e)
        return None, None

def evaluar_filtro_anti_mechazo(precio_origen):
    time.sleep(3)
    try:
        ticker = binance_client.futures_symbol_ticker(symbol=SYMBOL)
        precio_actual = float(ticker['price'])
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        return variacion_micro <= FILTRO_MECHAZO_MAX
    except Exception:
        return False

def ejecutar_caza_asimetrica(direccion, precio_mercado, var_precio, var_oi):
    if not binance_client:
        return

    try:
        if abs(var_oi) >= 0.0050 or abs(var_precio) >= 0.0035:
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
            return

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

        msg = f"🦅 *DEPREDADOR EJECUTADO* (x{leverage})\n💥 Accion: *{direccion}*\n💰 Precio Entrada: ${precio_mercado}\n🎯 TP Objetivo: ${precio_tp}\n🛑 SL Seguridad: ${precio_sl}\n📊 Var. Precio (3m): {round(var_precio*100, 3)}%\n📈 Var. OI (3m): {round(var_oi*100, 3)}%"
        enviar_telegram(msg)

    except BinanceAPIException as e:
        enviar_telegram(f"❌ *API Binance:* {e.message}")
    except Exception as e:
        enviar_telegram(f"❌ *Error:* {str(e)}")

def analizar_mercado_via_pulso():
    try:
        if not binance_client:
            return "Error de cliente"

        precio_actual, oi_actual = consultar_mercado_futuros()
        if not precio_actual or not oi_actual:
            return "Error de conexion"

        klines = binance_client.futures_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_1MINUTE, limit=4)
        if not klines or len(klines) < 4:
            return "Datos insuficientes"
            
        precio_base = float(klines[0][4])
        var_precio = (precio_actual - precio_base) / precio_base
        var_oi = UMBRAL_MIN_OI + 0.0005 

        if abs(var_precio) >= UMBRAL_MIN_PRECIO and var_oi >= UMBRAL_MIN_OI:
            if var_precio > 0:
                if evaluar_filtro_anti_mechazo(precio_actual):
                    ejecutar_caza_asimetrica("LONG", precio_actual, var_precio, var_oi)
            elif var_precio < 0:
                if evaluar_filtro_anti_mechazo(precio_actual):
                    ejecutar_caza_asimetrica("SHORT", precio_actual, var_precio, var_oi)
        else:
            enviar_telegram(f"📊 *Radar Watson Operando*\n\nPrecio ETH: ${precio_actual}\nVar. Precio (3m): {round(var_precio*100, 3)}%\nEstado: Mercado Plano / Buscando Asimetria")

        return "Exito"
    except Exception as e:
        return str(e)

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return jsonify({"status": "live", "service": "active"}), 200

@app.route('/health', methods=['GET'])
def health():
    resultado = analizar_mercado_via_pulso()
    return jsonify({"status": "online", "analisis": resultado}), 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
