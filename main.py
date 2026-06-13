import os
import json
import asyncio
import sqlite3
import threading
import subprocess
import sys

try:
    import flask
    import flask_cors
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "flask-cors"])

from flask import Flask, jsonify
from flask_cors import CORS
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ai_client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,ngrok-skip-browser-warning'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

def init_db():
    conn = sqlite3.connect("city_issues.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            category TEXT,
            address TEXT,
            lat REAL,
            lng REAL,
            radius REAL,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/api/issues', methods=['GET'])
def get_issues():
    conn = sqlite3.connect("city_issues.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, category, address, lat, lng, radius, status FROM issues")
    rows = cursor.fetchall()
    conn.close()
    
    issues = []
    for row in rows:
        issues.append({
            "id": row[0],
            "text": row[1],
            "category": row[2],
            "address": row[3],
            "lat": row[4],
            "lng": row[5],
            "radius": row[6] if row[6] is not None else 100,
            "status": row[7]
        })
    return jsonify(issues)
@app.route('/api/issues/clear', methods=['POST'])
def clear_issues():
    conn = sqlite3.connect("city_issues.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM issues")
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Карта успешно очищена"})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

async def analyze_text_with_ai(user_text):
    text_lower = user_text.lower()
    
    if "акимат" in text_lower:
        return "Благоустройство", "мкр. Нурсат, Здание Акимата", 42.3648, 69.6152, 150
    elif "плаза" in text_lower or "plaza" in text_lower:
        return "Благоустройство", "проспект Кунаева, ТРЦ Shymkent Plaza", 42.3204, 69.5915, 100
    elif "цум" in text_lower:
        return "Освещение", "проспект Кунаева, 17 (ЦУМ)", 42.3215, 69.5908, 100
    elif "север" in text_lower and "тц" in text_lower:
        return "Мусор", "ТЦ Север", 42.3495, 69.6210, 100
    elif "байдибек" in text_lower or "казына" in text_lower:
        return "Дороги", "проспект Байдибек би, Этнопарк", 42.3582, 69.5931, 300
    elif "площадь" in text_lower and "аль-фараби" in text_lower:
        return "Мусор", "площадь Аль-Фараби", 42.3155, 69.5852, 150
    elif "улица" in text_lower and "аль-фараби" in text_lower:
        return "Другое", "проспект Аль-Фараби", 42.3198, 69.5750, 500

    microrayons = {
        "туран": ("мкр. Туран", 42.3480, 69.5350, 900),
        "нурсат": ("мкр. Нурсат", 42.3620, 69.6120, 800),
        "асар": ("мкр. Асар", 42.4020, 69.6130, 850),
        "самал": ("мкр. Самал", 42.3450, 69.5650, 750),
        "восток": ("мкр. Восток", 42.3390, 69.6380, 500),
        "карасу": ("мкр. Карасу", 42.3160, 69.6210, 450),
        "север": ("мкр. Север", 42.3480, 69.6230, 500),
        "достык": ("мкр. Достык", 42.3850, 69.5180, 900),
        "кайтпас": ("мкр. Кайтпас", 42.3780, 69.5920, 800),
        "бозарык": ("мкр. Бозарык", 42.4350, 69.6180, 1000),
        "куншыгыс": ("мкр. Куншыгыс", 42.3320, 69.6370, 400),
        "сайрам": ("мкр. Сайрам / ж.м. Сайрам", 42.3120, 69.6950, 1000),
        "забадам": ("ж.м. Забадам", 42.2780, 69.5720, 850),
        "чапаевка": ("ж.м. Чапаевка", 42.3480, 69.6650, 700),
        "онтустик": ("ж.м. Онтустик (Фосфорный)", 42.2590, 69.6250, 1000),
        "тассай": ("ж.м. Тассай", 42.3550, 69.6880, 900),
        "катын копр": ("ж.м. Катын Копр", 42.3250, 69.5380, 700),
        "кызылжар": ("ж.м. Кызылжар", 42.2750, 69.5150, 850),
        "акжайык": ("мкр. Акжайык", 42.3780, 69.5550, 750),
        "жанаталап": ("ж.м. Жанаталап", 42.4250, 69.4650, 1100),
        "отрар": ("мкр. Отырар", 42.3370, 69.6050, 350),
        "спорт": ("мкр. Спорт / Спорткомплекс", 42.3250, 69.6120, 300),
        "наурыз": ("мкр. Наурыз", 42.3520, 69.5780, 500)
    }

    for key, (name, lat, lng, radius) in microrayons.items():
        if key in text_lower:
            category = "Другое"
            if "свет" in text_lower or "фонар" in text_lower or "освещен" in text_lower:
                category = "Освещение"
            elif "дорог" in text_lower or "ям" in text_lower or "асфальт" in text_lower:
                category = "Дороги"
            elif "мусор" in text_lower or "бак" in text_lower or "свалка" in text_lower:
                category = "Мусор"
            elif "вода" in text_lower or "отоплен" in text_lower or "труб" in text_lower:
                category = "ЖКХ"
            elif "парк" in text_lower or "детск" in text_lower or "площадк" in text_lower:
                category = "Благоустройство"
                
            return category, name, lat, lng, radius

    prompt = f"""
    Ты — ИИ-модуль городской системы Шымкента. Твоя задача — извлечь из текста категорию, адрес, координаты центра (lat, lng), а ТАКЖЕ определить приблизительный РАДИУС зоны происшествия в метрах (поле "radius").
    
    Правила для поля "radius" (в метрах):
    - Если указан точный объект, ТЦ, или конкретный дом (например: ул. Рыскулова 45) -> ставь radius от 50 до 150.
    - Если указана просто длинная улица без номера дома (например: пр. Республики, ул. Тауке хана, ул. Жибек Жолы) -> ставь radius от 400 до 600.

    Категории: "ЖКХ", "Дороги", "Благоустройство", "Мусор", "Освещение", "Другое".
    
    Верни СТРОГО JSON без markdown разметки:
    {{"category": "категория", "address": "адрес", "lat": 42.3417, "lng": 69.5901, "radius": 200}}

    Текст жителя: "{user_text}"
    """
    try:
        response = await ai_client.chat.completions.create(
            model="mixtral-8x7b-32768", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        result_text = response.choices[0].message.content.strip()
        
        if result_text.startswith("```json"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()
            
        data = json.loads(result_text)
        return (
            data.get("category", "Другое"), 
            data.get("address", "Шымкент"),
            float(data.get("lat", 42.3417)),
            float(data.get("lng", 69.5901)),
            float(data.get("radius", 200))
        )
    except Exception as e:
        print(f"⚠️ Сработал Fallback: {e}")
        return "Другое", "Шымкент", 42.3417, 69.5901, 300

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("👋 Привет! Я ИИ-помощник Шымкента. Напишите, что случилось и укажите адрес.")

@dp.message()
async def handle_message(message: types.Message):
    user_text = message.text
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    category, address, lat, lng, radius = await analyze_text_with_ai(user_text)
    
    conn = sqlite3.connect("city_issues.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO issues (text, category, address, lat, lng, radius, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_text, category, address, lat, lng, radius, "Новая")
    )
    conn.commit()
    conn.close()
    
    reply = f"✅ **Жалоба зафиксирована!**\n\n🗂 **Категория:** {category}\n📍 **Адрес:** {address}\n⭕️ **Зона охвата:** ~{int(radius)} метров"
    await message.answer(reply, parse_mode="Markdown")

async def main():
    init_db()
    print("🚀 ИИ-сервер запущен! Ждем сообщения...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    asyncio.run(main())
