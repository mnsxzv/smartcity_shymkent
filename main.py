import os
import json
import asyncio
import sqlite3
import threading
import subprocess
import sys
import re

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
        # Номерные микрорайоны
        "18": ("18-й микрорайон", 42.337959, 69.626564, 400),
        "11": ("11-й микрорайон", 42.322699, 69.637644, 400),
        "16": ("16-й микрорайон", 42.33601, 69.638991, 400),
        "15": ("15-й микрорайон", 42.331861, 69.635299, 400),
        "17": ("17-й микрорайон", 42.336902, 69.633515, 400),
        "12": ("12-й микрорайон", 42.327919, 69.64157, 400),
        "13": ("13-й микрорайон", 42.324118, 69.646798, 400),
        "3": ("3-й микрорайон", 42.328147, 69.576976, 400),
        "8": ("8-й микрорайон", 42.321715, 69.5788, 400),
        "4": ("4-й микрорайон", 42.336563, 69.568249, 400),
        "21": ("21-й микрорайон", 42.300115, 69.589666, 400),

        # Именные микрорайоны и жилые массивы
        "нурсат": ("мкр. Нурсат", 42.360921, 69.627692, 600),
        "сауле": ("мкр. Сауле", 42.279216, 69.575454, 900),
        "нуртас": ("мкр. Нуртас", 42.367181, 69.669978, 800),
        "казыгурт": ("мкр. Казыгурт", 42.288807, 69.548352, 900),
        "сайрам": ("мкр. Сайрам / ж.м. Сайрам", 42.342778, 69.635925, 1200),
        "курсай": ("мкр. Курсай", 42.307195, 69.533707, 1000),
        "северозапад": ("мкр. Северо-Запад", 42.372766, 69.584105, 800),
        "достык": ("мкр. Достык", 42.415466, 69.557711, 900),
        "асар": ("мкр. Асар", 42.406461, 69.599542, 850),
        "азат": ("мкр. Азат", 42.326623, 69.673356, 850),
        "восток": ("мкр. Восток", 42.336796, 69.646322, 500),
        "нижний отрар": ("мкр. Нижний Отырар", 42.346802, 69.615646, 400),
        "верхний отрар": ("мкр. Верхний Отырар", 42.345988, 69.622541, 400),
        "отрар": ("мкр. Отырар", 42.345965, 69.620652, 350),
        "наурыз": ("мкр. Наурыз", 42.351309, 69.607904, 500),
        "туркестан": ("мкр. Туркестан", 42.353178, 69.621541, 500),
        "северо восток": ("мкр. Северо-Восток", 42.348955, 69.640442, 500),
        "тараз": ("мкр. Тараз", 42.348158, 69.630923, 450),
        "терискей": ("мкр. Терискей", 42.34238, 69.642594, 500),
        "астана": ("мкр. Астана", 42.353494, 69.654199, 600),
        "шапагат-2": ("мкр. Шапагат-2", 42.347761, 69.50153, 500),
        "шапагат": ("мкр. Шапагат", 42.338494, 69.65521, 550),
        "мирас": ("мкр. Мирас", 42.348764, 69.67429, 700),
        "кайтпас-1": ("мкр. Кайтпас-1", 42.380121, 69.640333, 800),
        "кайтпас-2": ("мкр. Кайтпас-2", 42.393962, 69.579277, 850),
        "кайтпас": ("мкр. Кайтпас", 42.3814, 69.5955, 800),
        "малый самал": ("мкр. Малый Самал", 42.344392, 69.598295, 450),
        "самал-1": ("мкр. Самал-1", 42.352, 69.588174, 650),
        "самал-3": ("мкр. Самал-3", 42.370225, 69.548713, 800),
        "самал-2": ("мкр. Самал-2", 42.366986, 69.612225, 750),
        "улагаat": ("мкр. Улагат", 42.337661, 69.674808, 600),
        "тассай": ("ж.м. Тассай", 42.362069, 69.705891, 950),
        "бозарык": ("мкр. Бозарык", 42.427946, 69.624233, 1100),
        "таскен": ("мкр. Таскен", 42.377084, 69.718032, 1200),
        "катын копр": ("ж.м. Катын Копр", 42.346304, 69.550517, 750),
        "шугыла": ("мкр. Шугыла", 42.360077, 69.574676, 550),
        "спортивный": ("Спортивный мкр.", 42.335862, 69.599538, 400),
        "спорт": ("Спортивный мкр.", 442.335862, 69.599538, 400),
        "нуршуак": ("мкр. Нуршуак", 42.379675, 69.53125, 900),
        "зеленая балка": ("мкр. Зеленая Балка", 42.291458, 69.606253, 600),
        "еламан": ("мкр. Еламан", 42.282037, 69.627171, 750),
        "жайлау": ("мкр. Жайлау", 42.33858, 69.538836, 700),
        "ынтымак": ("мкр. Ынтымак", 42.369869, 69.521007, 950),
        "онтустик": ("ж.м. Онтустик (Фосфорный)", 42.28265, 69.605188, 1000),
        "карасу": ("мкр. Карасу", 42.305583, 69.587189, 500),
        "север": ("мкр. Север", 42.34238, 69.642594, 600),
        "туран": ("мкр. Туран", 42.400765, 69.64526, 950),
        "куншыгыс": ("мкр. Куншыгыс", 42.3331, 69.6385, 450),
        "забадам": ("ж.м. Забадам", 42.265719, 69.595633, 850),
        "чапаевка": ("ж.м. Чапаевка", 42.3452, 69.6640, 750),
        "кызылжар": ("ж.м. Кызылжар", 42.2714, 69.5120, 850),
        "акжайык": ("мкр. Акжайык", 42.3752, 69.5531, 750),
        "жанаталап": ("ж.м. Жанаталап", 42.4221, 69.4624, 1100)
    }

    # Сортируем ключи по длине от самых длинных к коротким
    # Благодаря этому "самал-3" проверится НАМНОГО раньше, чем одиночная цифра "3"
    sorted_keys = sorted(microrayons.keys(), key=len, reverse=True)
    
    found_key = None
    for key in sorted_keys:
        # Если ключ состоит только из цифр, проверяем его как отдельное число
        if key.isdigit():
            if re.search(r'\b' + re.escape(key) + r'\b', text_lower):
                found_key = key
                break
        else:
            # Текстовые ключи (включая составные "самал-3") ищем обычным вхождением
            if key in text_lower:
                found_key = key
                break

    if found_key:
        name, lat, lng, radius = microrayons[found_key]
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
