#!/usr/bin/env python3
"""
Bot de Telegram para Detector de Plagas
Corre en Railway.app - Independiente de Streamlit
"""

import os
import sys
import requests
from PIL import Image
from ultralytics import YOLO
from io import BytesIO
from datetime import datetime, timezone, timedelta
import time

# ==========================================
# CONFIGURACIÓN DESDE VARIABLES DE ENTORNO
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("❌ ERROR CRÍTICO: La variable TELEGRAM_BOT_TOKEN no está configurada.", flush=True)
    sys.exit(1)

CLASSES = ['Crítico', 'Nada Saludable', 'Saludable', 'media_saludable']
ecuador_tz = timezone(timedelta(hours=-5))

# ==========================================
# CARGAR MODELO
# ==========================================
print(" Descargando modelo desde Hugging Face...", flush=True)
try:
    model_url = "https://huggingface.co/EAMB2001/detector-plagas-modelo/resolve/main/modelo.pt"
    response = requests.get(model_url, timeout=60)
    response.raise_for_status()
    
    model_path = "/tmp/modelo.pt"
    with open(model_path, "wb") as f:
        f.write(response.content)
    
    print(" Inicializando modelo YOLO...", flush=True)
    model = YOLO(model_path)
    print("✅ Modelo cargado correctamente", flush=True)
except Exception as e:
    print(f"❌ ERROR al cargar el modelo: {e}", flush=True)
    sys.exit(1)

# ==========================================
# FUNCIONES DEL BOT
# ==========================================
def descargar_imagen_telegram(file_id):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        file_path = response.json()['result']['file_path']
        
        url_download = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        response = requests.get(url_download, timeout=30)
        response.raise_for_status()
        
        return response.content
    except Exception as e:
        print(f"❌ Error descargando imagen: {e}", flush=True)
        return None

def analizar_imagen(imagen_bytes):
    try:
        image = Image.open(BytesIO(imagen_bytes)).convert('RGB')
        temp_path = "/tmp/telegram_analysis.jpg"
        image.save(temp_path)
        
        results = model(temp_path, verbose=False)
        boxes = results[0].boxes
        
        if len(boxes) > 0:
            mejor = max(boxes, key=lambda b: float(b.conf[0]))
            clase = CLASSES[int(mejor.cls[0])]
            conf = float(mejor.conf[0]) * 100
            
            result_img = results[0].plot()
            img_byte_arr = BytesIO()
            Image.fromarray(result_img).save(img_byte_arr, format='JPEG')
            
            return clase, conf, img_byte_arr.getvalue()
        else:
            return None, 0, None
    except Exception as e:
        print(f"❌ Error analizando imagen: {e}", flush=True)
        return None, 0, None

def enviar_mensaje(chat_id, texto, imagen_bytes=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "Markdown"
        }, timeout=10)
        
        if imagen_bytes:
            url_foto = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {'photo': ('image.jpg', imagen_bytes, 'image/jpeg')}
            requests.post(url_foto, files=files, 
                         data={"chat_id": chat_id}, timeout=10)
        return True
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}", flush=True)
        return False

# ==========================================
# LOOP PRINCIPAL DEL BOT
# ==========================================
print("🤖 Bot iniciado. Esperando mensajes...", flush=True)
last_update_id = 0
processed_updates = set()

while True:
    try:
        offset = last_update_id + 1 if last_update_id > 0 else -1
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
        response = requests.get(url, timeout=35)
        
        if response.status_code == 200:
            updates = response.json().get('result', [])
            
            for update in updates:
                update_id = update.get('update_id')
                
                # Evitar procesar el mismo update múltiples veces
                if update_id in processed_updates:
                    continue
                
                message = update.get('message', {})
                chat_id = message.get('chat', {}).get('id')
                
                # Actualizar último update procesado
                if update_id > last_update_id:
                    last_update_id = update_id
                    processed_updates.add(update_id)
                    
                    # Limpiar el set periódicamente
                    if len(processed_updates) > 100:
                        processed_updates.clear()
                
                if 'photo' in message:
                    print(f"📸 Nueva imagen recibida de {chat_id}", flush=True)
                    
                    # Obtener foto de mayor resolución
                    photo = message['photo'][-1]
                    file_id = photo['file_id']
                    
                    enviar_mensaje(chat_id, "🔍 Analizando imagen...")
                    
                    imagen_bytes = descargar_imagen_telegram(file_id)
                    if imagen_bytes:
                        clase, conf, imagen_resultado = analizar_imagen(imagen_bytes)
                        ahora = datetime.now(ecuador_tz)
                        
                        if clase:
                            # Formato según la clase detectada
                            if clase in ['Crítico', 'Nada Saludable']:
                                titulo = "*ALERTA DE PLAGA DETECTADA*"
                                accion = "⚠️ Acción recomendada: Revisar planta inmediatamente"
                            else:
                                titulo = "*HOJA EN BUEN ESTADO*"
                                accion = " No se requieren acciones inmediatas"
                            
                            respuesta = f"""
{titulo}

 Clase: {clase}
📊 Confianza: {conf:.2f}%
⏰ Hora: {ahora.strftime('%H:%M:%S')}
📅 Fecha: {ahora.strftime('%d/%m/%Y')}

{accion}
                            """
                            enviar_mensaje(chat_id, respuesta, imagen_resultado)
                        else:
                            enviar_mensaje(chat_id, "❌ No se detectó ninguna hoja")
        
        time.sleep(1)
        
    except Exception as e:
        print(f"❌ Error en el loop: {e}", flush=True)
        time.sleep(5)
