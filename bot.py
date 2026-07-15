#!/usr/bin/env python3
"""
Bot de Telegram para Detector de Plagas
Corre en Railway.app - Independiente de Streamlit
"""

import os
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
CLASSES = ['Crítico', 'Nada Saludable', 'Saludable', 'media_saludable']
ecuador_tz = timezone(timedelta(hours=-5))

# ==========================================
# CARGAR MODELO
# ==========================================
print("🔄 Descargando modelo desde Hugging Face...")
model_url = "https://huggingface.co/EAMB2001/detector-plagas-modelo/resolve/main/modelo.pt"
response = requests.get(model_url)
model_path = "/tmp/modelo.pt"
with open(model_path, "wb") as f:
    f.write(response.content)

model = YOLO(model_path)
print("✅ Modelo cargado correctamente")

# ==========================================
# FUNCIONES DEL BOT
# ==========================================
def descargar_imagen_telegram(file_id):
    """Descarga imagen desde Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(url)
        file_path = response.json()['result']['file_path']
        
        url_download = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        response = requests.get(url_download)
        
        return response.content
    except Exception as e:
        print(f"❌ Error descargando imagen: {e}")
        return None

def analizar_imagen(imagen_bytes):
    """Analiza imagen con YOLO"""
    try:
        image = Image.open(BytesIO(imagen_bytes))
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
        print(f"❌ Error analizando imagen: {e}")
        return None, 0, None

def enviar_mensaje(chat_id, texto, imagen_bytes=None):
    """Envía mensaje a Telegram"""
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
        print(f"❌ Error enviando mensaje: {e}")
        return False

# ==========================================
# LOOP PRINCIPAL DEL BOT
# ==========================================
print("🤖 Bot iniciado. Esperando mensajes...")
last_update_id = 0

while True:
    try:
        offset = last_update_id + 1 if last_update_id > 0 else -1
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
        response = requests.get(url, timeout=35)
        
        if response.status_code == 200:
            updates = response.json().get('result', [])
            
            for update in updates:
                update_id = update.get('update_id')
                message = update.get('message', {})
                chat_id = message.get('chat', {}).get('id')
                
                if update_id > last_update_id:
                    last_update_id = update_id
                
                if 'photo' in message:
                    print(f"📸 Nueva imagen recibida de {chat_id}")
                    
                    photo = message['photo'][-1]
                    file_id = photo['file_id']
                    
                    enviar_mensaje(chat_id, "🔍 Analizando imagen...")
                    
                    imagen_bytes = descargar_imagen_telegram(file_id)
                    if imagen_bytes:
                        clase, conf, imagen_resultado = analizar_imagen(imagen_bytes)
                        
                        ahora = datetime.now(ecuador_tz)
                        
                        if clase:
                            respuesta = f"""
🍃 *Resultado del Análisis*

🎯 *Clase:* {clase}
📊 *Confianza:* {conf:.2f}%
⏰ *Hora:* {ahora.strftime('%H:%M:%S')}
📅 *Fecha:* {ahora.strftime('%d/%m/%Y')}

{'🚨 *¡ALERTA!* Revisa la planta inmediatamente' if clase in ['Crítico', 'Nada Saludable'] else '✅ Hoja en buen estado'}
                            """
                            enviar_mensaje(chat_id, respuesta, imagen_resultado)
                        else:
                            enviar_mensaje(chat_id, "❌ No se detectó ninguna hoja")
        
        time.sleep(1)
        
    except Exception as e:
        print(f"❌ Error en el loop: {e}")
        time.sleep(5)
