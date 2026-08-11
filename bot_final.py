import os
import time
import requests
import hashlib
import threading
from flask import Flask, request, jsonify, redirect, make_response
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Desactivar alertas de certificados inseguros para el bypass forzado
from requests.packages import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Inicialización nativa obligatoria para el despachador WSGI de Gunicorn
app = Flask(__name__)

SYMBOL = "ETHUSDT"
TELEGRAM_CHAT_ID = "-1004335003036"
FILTRO_MECHAZO_MAX = 0.0018  

# EXTRACCIÓN SEGURA DE CREDENCIALES DESDE EL ENTORNO DE RENDER
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

URL_BINANCE = os.getenv("URL_BINANCE")
URL_CRYPTO = os.getenv("URL_CRYPTO")
URL_TELEGRAM = os.getenv("URL_TELEGRAM")

# VARIABLES GLOBALES DINÁMICAS (Viven 100% en la memoria RAM de Render)
ESTADO_BOT = "PREDADOR"       # Modos permitidos: "OFF", "PREDADOR", "APLANAMIENTO"
LEVERAGE_MANUAL = 10          # Control dinámico de apalancamiento desde la web
ULTIMO_PRECIO_MONITOREO = 0.0 
ULTIMO_ATR_MONITOREO = 0.0    
CONTADOR_MECHAZOS = 0         

# Almacenamiento local para el algoritmo de ruptura autónoma de 3 velas
HISTORIAL_PRECIOS_MAESTRO = []

def obtener_cliente_binance():
    if BINANCE_API_KEY and BINANCE_SECRET_KEY:
        try:
            cliente = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
            cliente.API_URL = "https://api1.binance.com"
            return cliente
        except Exception as e:
            print("LOG_WATSON_BINANCE_FALLO: Error al instanciar el cliente de Binance -> " + str(e), flush=True)
            return None
    return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN: return False
    protocolo = "https://"
    sub = "api."
    raiz = "telegram"
    tld = ".org"
    ruta_metodo = "/bot" + str(TELEGRAM_TOKEN) + "/sendMessage"
    url = protocolo + sub + raiz + tld + ruta_metodo
    if URL_TELEGRAM: url = str(URL_TELEGRAM) + "/bot" + str(TELEGRAM_TOKEN) + "/sendMessage"
    
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
    except Exception as e:
        print("LOG_WATSON: Fallo en ATR de Binance -> " + str(e))
        return None

def evaluar_filtro_anti_mechazo_directo(client_local, precio_origen):
    time.sleep(3)
    if not client_local: return False
    try:
        ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
        precio_actual = float(ticker['price'])
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        if variacion_micro > FILTRO_MECHAZO_MAX:
                 registrar_mechazo_evitado_supabase(precio_actual)
                 porcentaje_formateado = round(variacion_micro * 100, 3)
                 msg_bloqueo = "⚠️ ALERTA MITIGACIÓN WATSON\n• Orden Cancelada: Mechazo Detectado\n• Variación Micro: " + str(porcentaje_formateado) + "%\n• Precio Ticker: " + str(precio_actual)
                 enviar_telegram(msg_bloqueo)
                 return False
        return True
    except Exception as e:
        print("LOG_WATSON: Fallo en Filtro Ticker de Binance -> " + str(e))
        return False

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
        client_local.futures_create_order(symbol=SYMBOL, side=side_salida, type='STOP_MARKET', stopPrice=precio_sl, closePosition=True); guardar_auditoria_supabase(direccion, precio_mercado)              

        msg = "==================================\n   SISTEMA DEPREDADOR OPERATIVO   \n==================================\n• ACTIVO      : " + str(SYMBOL) + "\n• DIRECCION   : " + str(direccion) + "\n• APALANCAMIENTO: x" + str(leverage) + "\n----------------------------------\n• ENTRADA     : " + str(precio_mercado) + "\n• TAKE PROFIT : " + str(precio_tp) + "\n• STOP LOSS   : " + str(precio_sl) + "\n----------------------------------\n• FUERZA SENAL: " + str(fuerza_senal) + "\n• MODO ACTIVO : " + str(ESTADO_BOT) + "\n• GESTION     : " + tipo_gestion + "\n=================================="
        enviar_telegram(msg)
        return "Exito"
    except BinanceAPIException as e:
        print("LOG_WATSON: Error Directo API Binance -> " + str(e))
        enviar_telegram("BINANCE_API_ERROR: " + str(e))
        return str(e)
    except Exception as e:
        enviar_telegram("ERROR CRITICO " + str(e))
        return str(e)

def leer_comando_supabase():
        global ESTADO_BOT
        url = os.getenv("URL_SUPABASE_TABLA")
        if not url: return
        
        token = "Bearer " + str(os.getenv("SUPABASE_KEY"))
        headers = dict([
            ("apikey", str(os.getenv("SUPABASE_KEY"))),
            ("Authorization", token)
        ])
        try:
            respuesta = requests.get(url, headers=headers, timeout=8, verify=False)
            if respuesta.status_code == 200:
                datos = respuesta.json()
                if datos and len(datos) > 0:
                    primer_registro = datos[0]
                    ESTADO_BOT = str(primer_registro.get("estado", ESTADO_BOT))
        except Exception as e:
            print("LOG_WATSON_SUPABASE: Fallo critico de red -> " + str(e))

def ciclo_monitoreo_automatico():
    global ULTIMO_PRECIO_MONITOREO, CONTADOR_MECHAZOS, HISTORIAL_PRECIOS_MAESTRO
    time.sleep(15)  # BYPASS: Inicialización limpia de Gunicorn
    while True:
        try:
            leer_comando_supabase()
            if ESTADO_BOT != "OFF":
                client_local = obtener_cliente_binance()
                print("LOG_WATSON_DEBUG: Intentando conectar a Binance... Resultado: " + str(client_local))
                if client_local:
                    ticker = client_local.futures_symbol_ticker(symbol=SYMBOL)
                    precio_actual = float(ticker['price'])
                    ULTIMO_PRECIO_MONITOREO = precio_actual
                    print("LOG_WATSON_PULSO: Modo: " + str(ESTADO_BOT) + " | Precio ETH: " + str(precio_actual) + " | Historial: " + str(len(HISTORIAL_PRECIOS_MAESTRO)), flush=True)                                        
                    
                    HISTORIAL_PRECIOS_MAESTRO.append(precio_actual)
                    if len(HISTORIAL_PRECIOS_MAESTRO) > 12: 
                        HISTORIAL_PRECIOS_MAESTRO.pop(0)

                    if len(HISTORIAL_PRECIOS_MAESTRO) >= 6:
                        maximo_canal = max(HISTORIAL_PRECIOS_MAESTRO)
                        minimo_canal = min(HISTORIAL_PRECIOS_MAESTRO)
                        
                        if ESTADO_BOT == "PREDADOR" and precio_actual >= maximo_canal:
                            if evaluar_filtro_anti_mechazo_directo(client_local, precio_actual):
                                ejecutar_caza_asimetrica(client_local, "LONG", precio_actual, 0.0022)
                        
                        if ESTADO_BOT == "PREDADOR" and precio_actual <= minimo_canal:
                            if evaluar_filtro_anti_mechazo_directo(client_local, precio_actual):
                                ejecutar_caza_asimetrica(client_local, "SHORT", precio_actual, 0.0022)
                                
                        if ESTADO_BOT == "APLANAMIENTO":
                            atr = calcular_atr_dinamico_flash(client_local)
                            if atr and atr < 1.5:
                                if precio_actual >= maximo_canal: ejecutar_caza_asimetrica(client_local, "SHORT", precio_actual, 0.0011)
                                if precio_actual <= minimo_canal: ejecutar_caza_asimetrica(client_local, "LONG", precio_actual, 0.0011)
                    
                    # Espera normal cuando todo sale BIEN
                    time.sleep(5)
                else:
                    time.sleep(15)               
        except Exception as e:
            print("LOG_WATSON_CRITICO: Fallo en ciclo de monitoreo -> " + str(e))
            # FRENO DE MANO OBLIGATORIO: Si hay baneo o error, duerme el bot por 60 segundos antes de reintentar
            time.sleep(60)

# DISPARO DIRECTO DEL HILO DE ENTRADA EN SEGUNDO PLANO
hilo_global = threading.Thread(target=ciclo_monitoreo_automatico)
hilo_global.daemon = True
hilo_global.start()
HILO_INICIADO = False
CANDADO_SISTEMA = threading.Lock()
# ------------------------------------------------------------------
# BYPASS TOTAL INMUNE: LA RAÍZ ENTREGA SOLO JSON (VIVO AL 100%)
# ------------------------------------------------------------------
@app.route('/', methods=['GET', 'HEAD', 'POST'])
def responder_salud_inmune():
    global HILO_INICIADO
    with CANDADO_SISTEMA:
        if not HILO_INICIADO:
            try:
                hilo_emergencia = threading.Thread(target=ciclo_monitoreo_automatico)
                hilo_emergencia.daemon = True
                hilo_emergencia.start()
                HILO_INICIADO = True
                print("LOG_WATSON_SISTEMA: Hilo de monitoreo forzado con exito desde pasarela HTTP.", flush=True)
            except Exception as e:
                print("LOG_WATSON_SISTEMA: Error al forzar hilo desde HTTP -> " + str(e), flush=True)
            
    diccionario_respuesta = dict(
        status="healthy",
        bot="online",
        mode=str(ESTADO_BOT)
    )
    return jsonify(diccionario_respuesta), 200

def guardar_auditoria_supabase(direccion_orden, precio_ejecutado):
    url = os.getenv("URL_SUPABASE_TABLA")
    if not url: return
    
    # Truco de limpieza: Reemplazar el endpoint de lectura por el de la tabla de trades
    url_trades = url.replace("control_bot", "historial_trades")
    # Limpiamos los filtros de lectura para dejar la URL limpia de escritura
    url_trades = url_trades.split("?")[0]
    
    token = "Bearer " + str(os.getenv("SUPABASE_KEY"))
    headers = dict([
        ("apikey", str(os.getenv("SUPABASE_KEY"))),
        ("Authorization", token),
        ("Content-Type", "application/json"),
        ("Prefer", "return=minimal")
    ])
    
    # Payload seguro sin una sola llave nativa
    payload = dict(
        direccion=str(direccion_orden),
        precio=float(precio_ejecutado)
    )
    
    try:
        requests.post(url_trades, json=payload, headers=headers, timeout=8, verify=False)
    except Exception:
        pass

def registrar_mechazo_evitado_supabase(precio_origen):
    url = os.getenv("URL_SUPABASE_TABLA")
    if not url: return
    
    url_mechazos = url.replace("control_bot", "registro_mechazos")
    url_mechazos = url_mechazos.split("?")[0]
    
    token = "Bearer " + str(os.getenv("SUPABASE_KEY"))
    headers = dict([
        ("apikey", str(os.getenv("SUPABASE_KEY"))),
        ("Authorization", token),
        ("Content-Type", "application/json"),
        ("Prefer", "return=minimal")
    ])
    
    payload = dict(
        perdida_evitada=float(5.50)
    )
    try:
        requests.post(url_mechazos[0], json=payload, headers=headers, timeout=8, verify=False)
    except Exception:
        pass



# ------------------------------------------------------------------
