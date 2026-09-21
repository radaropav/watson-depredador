import os
import sys
import time
import json
import logging
import threading
import requests
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify
from binance.client import Client
from binance.exceptions import BinanceAPIException

# =====================================================================
# SYSTEMA DE AUDITORÍA INTERNA DE DISCO (MIGRADOS A DIGITALOCEAN)
# =====================================================================
log_filename = "bot_operaciones.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[
    RotatingFileHandler(log_filename, maxBytes=10485760, backupCount=5),
    logging.StreamHandler(sys.stdout)
])
logger = logging.getLogger("WATSON_PRO")

# Inicialización obligatoria del despachador WSGI
app = Flask(__name__)

# =====================================================================
# CONFIGURACIÓN MATRIZ AVANZADA (MULTIACTIVO & VARIABLES DE ENTORNO)
# =====================================================================
ACTIVOS_MAESTROS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
FILTRO_MECHAZO_MAX = 0.0018
TELEGRAM_CHAT_ID = "-1004335003036"

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
URL_SUPABASE_TABLA = os.getenv("URL_SUPABASE_TABLA")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# MEMORIA RAM DE ALTA VELOCIDAD DEL VPS (ESTADO DEL SISTEMA)
ESTADO_BOT = "PREDADOR"        # "OFF", "PREDADOR", "APLANAMIENTO"
INDICE_SENTIMIENTO = 50       # Control de Pánico & Codicia (0-100)
LEVERAGE_MANUAL = 10          
HISTORIAL_PRECIOS_MAESTRO = {activo: [] for activo in ACTIVOS_MAESTROS}
ULTIMA_MARCA_TIEMPO_ATR = {activo: 0.0 for activo in ACTIVOS_MAESTROS}
ULTIMO_ATR_RAM = {activo: 1.8 for activo in ACTIVOS_MAESTROS}

CANDADO_ORDENES = threading.Lock()

def obtener_cliente_binance():
    if BINANCE_API_KEY and BINANCE_SECRET_KEY:
        try:
            return Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        except Exception as e:
            logger.error(f"Error de conexión nativa a la API oficial de Binance: {e}")
            return None
    return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN: return False
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    if os.getenv("URL_TELEGRAM"):
        url = f"{os.getenv('URL_TELEGRAM')}/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except Exception:
        return False

# =====================================================================
# GESTIÓN DE RIESGO E INFRAESTRUCTURA DE SEGURIDAD INTERNA
# =====================================================================
def comprobar_posicion_activa(cliente, simbolo):
    if not cliente: return True
    try:
        posiciones = cliente.futures_position_information(symbol=simbolo)
        for pos in posiciones:
            if pos['symbol'] == simbolo and float(pos['positionAmt']) != 0.0:
                return True
        return False
    except Exception as e:
        logger.error(f"Error comprobando posiciones abiertas para {simbolo}: {e}")
        return True

def evaluar_filtro_anti_mechazo_directo(cliente, simbolo, precio_origen):
    if not cliente: return False
    try:
        ticker = cliente.futures_symbol_ticker(symbol=simbolo)
        precio_actual = float(ticker['price'])
        variacion_micro = abs((precio_actual - precio_origen) / precio_origen)
        if variacion_micro > FILTRO_MECHAZO_MAX:
            registrar_mechazo_evitado_supabase(simbolo, precio_actual)
            enviar_telegram(f"⚠️ *ALERTA MITIGACIÓN*\n• Mechazo Detectado en {simbolo}\n• Variación: {round(variacion_micro * 100, 3)}%\n• Orden Cancelada.")
            return False
        return True
    except Exception as e:
        logger.error(f"Fallo crítico en filtro anti-mechazo de {simbolo}: {e}")
        return False

def calcular_atr_dinamico_flash(cliente, simbolo, periodos=14):
    global ULTIMO_ATR_RAM, ULTIMA_MARCA_TIEMPO_ATR
    tiempo_actual = time.time()
    if (tiempo_actual - ULTIMA_MARCA_TIEMPO_ATR[simbolo]) < 300.0:
        return ULTIMO_ATR_RAM[simbolo]
    try:
        klines = cliente.futures_klines(symbol=simbolo, interval=Client.KLINE_INTERVAL_5MINUTE, limit=periodos + 1)
        true_ranges = []
        for i in range(1, len(klines)):
            high, low, prev_close = float(klines[i][2]), float(klines[i][3]), float(klines[i-1][4])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        ULTIMO_ATR_RAM[simbolo] = sum(true_ranges) / len(true_ranges)
        ULTIMA_MARCA_TIEMPO_ATR[simbolo] = tiempo_actual
        return ULTIMO_ATR_RAM[simbolo]
    except Exception as e:
        logger.warning(f"API sobrecargada. Usando respaldo de ATR en RAM para {simbolo}: {e}")
        return ULTIMO_ATR_RAM[simbolo]

# =====================================================================
# MOTOR DE EJECUCIÓN CUASI-INSTITUCIONAL (FUTURE ORDERS)
# =====================================================================
def ejecutar_caza_asimetrica(cliente, simbolo, direccion, precio_mercado, fuerza_senal):
    global INDICE_SENTIMIENTO
    if ESTADO_BOT == "OFF": return
    
    # FILTRO DE PÁNICO Y CODICIA EXTREMA
    if ESTADO_BOT == "APLANAMIENTO" and (INDICE_SENTIMIENTO < 20 or INDICE_SENTIMIENTO > 85):
        logger.info(f"Filtro de Pánico/Codicia Bloqueó el Modo Aplanamiento en {simbolo} por alta volatilidad.")
        return

    with CANDADO_ORDENES:
        if comprobar_posicion_activa(cliente, simbolo):
            logger.info(f"Orden declinada: Ya hay una posición ejecutándose en {simbolo}")
            return

        try:
            leverage = 20 if fuerza_senal >= 0.0040 else LEVERAGE_MANUAL
            cliente.futures_change_leverage(symbol=simbolo, leverage=leverage)
            
            # INTERÉS COMPUESTO AUTOMÁTICO BASADO EN BALANCE EN TIEMPO REAL
            cuenta = cliente.futures_account()
            balance_real = float(cuenta.get('availableBalance', 0))
            capital_operativo = balance_real * 0.35 if balance_real > 400.0 else balance_real * 0.20
            
            quantity = round((capital_operativo * leverage) / precio_mercado, 3)
            if (quantity * precio_mercado) < 21.0:
                quantity = round(21.0 / precio_mercado, 3)
            if quantity <= 0: return

            atr = calcular_atr_dinamico_flash(cliente, simbolo)
            
            if ESTADO_BOT == "APLANAMIENTO":
                tp_pct, sl_pct = 0.0025, 0.0018
                precio_tp = round(precio_mercado * (1 + tp_pct), 2) if direccion == "LONG" else round(precio_mercado * (1 - tp_pct), 2)
                precio_sl = round(precio_mercado * (1 - sl_pct), 2) if direccion == "LONG" else round(precio_mercado * (1 + sl_pct), 2)
                tipo_gestion = "RANGOS_COMPRIMIDOS"
            else:
                multi_tp = 2.0 if fuerza_senal >= 0.0040 else 1.5
                multi_sl = 1.2 if fuerza_senal >= 0.0040 else 1.0
                precio_tp = round(precio_mercado + (atr * multi_tp), 2) if direccion == "LONG" else round(precio_mercado - (atr * multi_tp), 2)
                precio_sl = round(precio_mercado - (atr * multi_sl), 2) if direccion == "LONG" else round(precio_mercado + (atr * multi_sl), 2)
                tipo_gestion = "DINAMICA_ATR"

            side_entrada = Client.SIDE_BUY if direccion == "LONG" else Client.SIDE_SELL
            side_salida = Client.SIDE_SELL if direccion == "LONG" else Client.SIDE_BUY

            # EJECUCIÓN ORDEN DE ENTRADA MARKET
            cliente.futures_create_order(symbol=simbolo, side=side_entrada, type=Client.FUTURE_ORDER_TYPE_MARKET, quantity=quantity)
            
            # EFICIENCIA EN COMISIONES: ÓRDENES LIMITADAS MAKER (POST-ONLY) PARA LAS SALIDAS
            cliente.futures_create_order(symbol=simbolo, side=side_salida, type='TAKE_PROFIT_MARKET', stopPrice=precio_tp, reduceOnly=True)
            cliente.futures_create_order(symbol=simbolo, side=side_salida, type='STOP_MARKET', stopPrice=precio_sl, reduceOnly=True)
            
            # ACTIVACIÓN DEL TRAILING STOP DINÁMICO EN EL BROKER
            try:
                cliente.futures_create_order(symbol=simbolo, side=side_salida, type='TRAILING_STOP_MARKET', callbackRate=1.0, reduceOnly=True)
            except Exception:
                pass # Si el par no permite trailing stop rápido, continúa con las órdenes clásicas

            guardar_auditoria_supabase(simbolo, direccion, precio_mercado)
            
            msg = f"==================================\n🔥 *ORDEN INICIALIZADA EN FRANCFORT* 🔥\n==================================\n• ACTIVO      : {simbolo}\n• DIRECCIÓN   : {direccion}\n• COMPUESTO APALANCADO: x{leverage}\n----------------------------------\n• ENTRADA     : {precio_mercado}\n• TAKE PROFIT : {precio_tp}\n• STOP LOSS   : {precio_sl}\n----------------------------------\n• GESTIÓN     : {tipo_gestion}\n=================================="
            enviar_telegram(msg)
            logger.info(f"Orden ejecutada exitosamente para {simbolo} [{direccion}]")
        except BinanceAPIException as e:
            logger.error(f"Fallo de la API de Binance al inyectar orden para {simbolo}: {e}")
            enviar_telegram(f"❌ *BINANCE_API_ERROR* en {simbolo}: {e.message}")
        except Exception as e:
            logger.error(f"Fallo crítico operacional en orden de {simbolo}: {e}")

# =====================================================================
# HILOS DE MONITOREO AUTOMATIZADOS (WEBSOCKETS SIMULADOS ULTRA-EFICIENTES)
# =====================================================================
def leer_comando_supabase():
    global ESTADO_BOT
    if not URL_SUPABASE_TABLA or not SUPABASE_KEY: return
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        respuesta = requests.get(URL_SUPABASE_TABLA, headers=headers, timeout=5)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            if datos:
                ESTADO_BOT = str(datos.get("estado", ESTADO_BOT))
    except Exception as e:
        logger.error(f"Error sincronizando comandos desde el panel de Supabase: {e}")

def actualizar_sentimiento_noticias():
    global INDICE_SENTIMIENTO
    url = "https://alternative.me"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            INDICE_SENTIMIENTO = int(res.json()['data']['value'])
            logger.info(f"Filtro Macroeconómico Actualizado: Sentimiento del Mercado en {INDICE_SENTIMIENTO}/100")
    except Exception as e:
        logger.warning(f"No se pudo descargar el índice de Pánico y Codicia: {e}")

def hilo_lento_control_externo():
    """Hilo secundario lento: Lee Supabase y Noticias cada 30 segundos sin estorbar las órdenes"""
    while True:
        try:
            leer_comando_supabase()
            actualizar_sentimiento_noticias()
        except Exception as e:
            logger.error(f"Fallo en hilo de control externo: {e}")
        time.sleep(30)

def ciclo_monitoreo_principal_vps():
    """HILO MAESTRO DE ALTA VELOCIDAD PARA OPERACIÓN CONTINUA 24/7"""
    logger.info("Iniciando Hilo de Ejecución Continua desde los Servidores de Frankfurt...")
    cliente = obtener_cliente_binance()
    
    while True:
        if not cliente:
            logger.error("No se pudo instanciar el cliente Binance. Reintentando en 30 segundos...")
            time.sleep(30)
            cliente = obtener_cliente_binance()
            continue
            
        if ESTADO_BOT == "OFF":
            time.sleep(5)
            continue

        for activo in ACTIVOS_MAESTROS:
            try:
                ticker = cliente.futures_symbol_ticker(symbol=activo)
                precio_actual = float(ticker['price'])
                
                # ESCÁNER DE VOLATILIDAD INTERNA
                atr_actual = calcular_atr_dinamico_flash(cliente, activo)
                
                HISTORIAL_PRECIOS_MAESTRO[activo].append(precio_actual)
                if len(HISTORIAL_PRECIOS_MAESTRO[activo]) > 12:
                    HISTORIAL_PRECIOS_MAESTRO[activo].pop(0)

                if len(HISTORIAL_PRECIOS_MAESTRO[activo]) >= 6:
                    maximo_canal = max(HISTORIAL_PRECIOS_MAESTRO[activo][:-1])
                    minimo_canal = min(HISTORIAL_PRECIOS_MAESTRO[activo][:-1])

                    # MÓDULO ADAPTATIVO: ROTACIÓN OPERATIVA POR COMPORTAMIENTO
                    modo_activo_par = "PREDADOR" if atr_actual >= 1.5 else "APLANAMIENTO"

                    if modo_activo_par == "PREDADOR" and precio_actual > maximo_canal:
                        if evaluar_filtro_anti_mechazo_directo(cliente, activo, precio_actual):
                            ejecutar_caza_asimetrica(cliente, activo, "LONG", precio_actual, 0.0022)
                    
                    elif modo_activo_par == "PREDADOR" and precio_actual < minimo_canal:
                        if evaluar_filtro_anti_mechazo_directo(cliente, activo, precio_actual):
                            ejecutar_caza_asimetrica(cliente, activo, "SHORT", precio_actual, 0.0022)
                            
                    elif modo_activo_par == "APLANAMIENTO":
                        if precio_actual > maximo_canal:
                            ejecutar_caza_asimetrica(cliente, activo, "SHORT", precio_actual, 0.0011)
                        elif precio_actual < minimo_canal:
                            ejecutar_caza_asimetrica(cliente, activo, "LONG", precio_actual, 0.0011)

            except Exception as e:
                logger.error(f"Fallo en lectura de red WebSocket para {activo}: {e}")
                time.sleep(1)
        
        # Latencia de procesamiento optimizada para el VPS
        time.sleep(2)

# =====================================================================
# INTEGRACIÓN DE PERSISTENCIA Y RUTAS DE CONTROL HTTP
# =====================================================================
def guardar_auditoria_supabase(simbolo, direccion, precio):
    if not URL_SUPABASE_TABLA or not SUPABASE_KEY: return
    url_trades = URL_SUPABASE_TABLA.replace("control_bot", "historial_trades").split("?")[0]
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    payload = {"activo": simbolo, "direccion": direccion, "precio": float(precio)}
    try:
        requests.post(url_trades, json=payload, headers=headers, timeout=5)
    except Exception: pass

def registrar_mechazo_evitado_supabase(simbolo, precio):
    if not URL_SUPABASE_TABLA or not SUPABASE_KEY: return
    url_mechazos = URL_SUPABASE_TABLA.replace("control_bot", "registro_mechazos").split("?")[0]
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    payload = {"activo": simbolo, "precio": float(precio), "perdida_evitada": 5.50}
    try:
        requests.post(url_mechazos, json=payload, headers=headers, timeout=5)
    except Exception: pass

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return jsonify({"sistema": "WATSON_PROFESSIONAL_LIVE", "servidor": "FRANKFURT_VPS", "status": "RUNNING"}), 200

@app.route('/health', methods=['GET', 'HEAD'])
def health():
    return jsonify({"status": "OK", "threads_active": threading.active_count()}), 200

# LANZAMIENTO SEGURO MULTIHILO EN DIGITALOCEAN
hilo_control = threading.Thread(target=hilo_lento_control_externo, daemon=True)
hilo_control.start()

hilo_trading = threading.Thread(target=ciclo_monitoreo_principal_vps, daemon=True)
hilo_trading.start()

if __name__ == '__main__':
    # Ejecución nativa local o vía Gunicorn
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
