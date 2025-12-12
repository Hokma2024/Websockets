import asyncio
import json
import logging
from uuid import uuid4
from typing import Dict, List, Optional, Set
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import socketio
from loguru import logger
from pydantic import BaseModel

from models import Player, Game, Topic
from trivia_data import load_topics


from fastapi.responses import HTMLResponse
import os


# Настройка логгера
logger.add("quiz_server.log", rotation="10 MB", level="INFO")

# Инициализация FastAPI
app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация Socket.IO
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)

# Обертка ASGI для Socket.IO
app_with_socket = socketio.ASGIApp(sio, app)

# Сначала монтируем статику
app.mount("/static", StaticFiles(directory="static"), name="static")

# Потом — корневой маршрут
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join("static", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# === Глобальные хранилища ===
TOPICS = {t.pk: t for t in load_topics()}

# Ожидающие игроки: topic_pk → [sid]
waiting_players: Dict[int, List[str]] = {}

# Активные игры: game_uid → Game
active_games: Dict[str, Game] = {}

# sid → player info
sid_to_player: Dict[str, Player] = {}

# sid → game_uid
sid_to_game: Dict[str, str] = {}

# === Вспомогательные функции ===
def find_or_create_waiting_list(topic_pk: int) -> List[str]:
    """Получить или создать список ожидающих игроков для темы"""
    if topic_pk not in waiting_players:
        waiting_players[topic_pk] = []
    return waiting_players[topic_pk]

async def start_game(topic_pk: int, player1_sid: str, player2_sid: str):
    """Начать игру между двумя игроками"""
    if topic_pk not in TOPICS:
        logger.error(f"Тема с pk={topic_pk} не найдена")
        return
    
    topic = TOPICS[topic_pk]
    game_uid = str(uuid4())
    
    # Создаем игроков
    player1 = sid_to_player[player1_sid]
    player2 = sid_to_player[player2_sid]
    
    # Создаем игру
    game = Game(
        uid=game_uid,
        topic=topic,
        players=[player1, player2]
    )
    
    # Сохраняем игру
    active_games[game_uid] = game
    sid_to_game[player1_sid] = game_uid
    sid_to_game[player2_sid] = game_uid
    
    # Отправляем данные игры обоим игрокам
    game_data = game.to_dict()
    await sio.emit("game", game_data, to=player1_sid)
    await sio.emit("game", game_data, to=player2_sid)
    
    logger.info(f"Начата игра {game_uid} в теме {topic.name} между {player1.name} и {player2.name}")

async def send_next_question(game_uid: str):
    """Отправить следующий вопрос после задержки"""
    if game_uid not in active_games:
        return
    
    game = active_games[game_uid]
    
    # Задержка перед отправкой следующего вопроса
    await asyncio.sleep(3.0)
    
    if game_uid not in active_games:
        return
    
    game.advance()
    
    # Проверяем, есть ли еще вопросы
    if game.question_count <= 0:
        # Игра окончена
        results = {
            "players": [
                {"name": p.name, "score": p.score}
                for p in game.players
            ]
        }
        for p in game.players:
            await sio.emit("over", results, to=p.sid)
        
        # Удаляем игру
        if game_uid in active_games:
            del active_games[game_uid]
        return
    
    # Отправляем следующий вопрос
    game_data = game.to_dict()
    for p in game.players:
        await sio.emit("game", game_data, to=p.sid)

# === Обработчики Socket.IO событий ===

@sio.event
async def connect(sid, environ, auth):
    """Обработка подключения клиента"""
    logger.info(f"Клиент подключился: {sid}")
    await sio.emit("connected", {"message": "Connected to quiz server"}, to=sid)

@sio.event
async def disconnect(sid):
    """Обработка отключения клиента"""
    logger.info(f"Клиент отключился: {sid}")
    
    # Удаляем из списка ожидающих
    for topic_pk, sids in waiting_players.items():
        if sid in sids:
            sids.remove(sid)
            if not sids:
                del waiting_players[topic_pk]
            break
    
    # Удаляем из активных игр
    if sid in sid_to_game:
        game_uid = sid_to_game[sid]
        if game_uid in active_games:
            game = active_games[game_uid]
            
            # Находим другого игрока
            other_player = None
            for p in game.players:
                if p.sid != sid:
                    other_player = p
                    break
            
            if other_player:
                # Уведомляем оставшегося игрока
                await sio.emit("error", {
                    "error": "opponent_disconnected",
                    "message": "Ваш соперник отключился. Игра завершена."
                }, to=other_player.sid)
            
            # Удаляем игру
            if game_uid in active_games:
                del active_games[game_uid]
        
        del sid_to_game[sid]
    
    # Удаляем информацию об игроке
    if sid in sid_to_player:
        del sid_to_player[sid]

@sio.event
async def get_topics(sid, data=None):
    """Обработка запроса списка тем"""
    logger.info(f"Запрос списка тем от {sid}, данные: {data}")
    
    # Сериализуем темы вручную
    topics_list = []
    for t in TOPICS.values():
        serialized_questions = [
            {
                "text": q.text,
                "options": q.options,
                "correct_index": q.correct_index
            }
            for q in t.questions
        ]
        
        topics_list.append({
            "pk": t.pk,
            "name": t.name,
            "questions": serialized_questions,
            "has_players": len(find_or_create_waiting_list(t.pk)) > 0
        })
    
    await sio.emit("topics", topics_list, to=sid)
    logger.debug(f"Отправлены темы: {topics_list}")

@sio.event
async def join_game(sid, data):
    """Присоединение к игре в выбранной теме"""
    logger.info(f"Запрос на присоединение к игре от {sid}: {data}")
    
    # Валидация данных
    if not isinstance(data, dict):
        logger.warning(f"Неверный формат данных от {sid}: {data}")
        await sio.emit("error", {"error": "invalid_data", "message": "Invalid data format"}, to=sid)
        return
    
    topic_pk = data.get("topic_pk")
    name = data.get("name", "").strip()
    
    # Валидация темы
    if not isinstance(topic_pk, int) or topic_pk not in TOPICS:
        logger.warning(f"Неверная тема от {sid}: {topic_pk}")
        await sio.emit("error", {"error": "invalid_topic", "message": "Invalid topic selected"}, to=sid)
        return
    
    # Валидация имени
    if not name or len(name) > 20:
        logger.warning(f"Неверное имя от {sid}: {name}")
        await sio.emit("error", {"error": "invalid_name", "message": "Invalid player name"}, to=sid)
        return
    
    # Сохраняем информацию об игроке
    sid_to_player[sid] = Player(sid=sid, name=name)
    
    # Получаем список ожидающих для этой темы
    waiting_list = find_or_create_waiting_list(topic_pk)
    
    if len(waiting_list) == 0:
        # Первый игрок - добавляем в список ожидающих
        waiting_list.append(sid)
        logger.info(f"Игрок {sid} ({name}) ожидает партнера в теме {topic_pk}")
        return
    
    # Есть партнер - начинаем игру
    partner_sid = waiting_list.pop(0)
    
    # Удаляем тему из waiting_players если список пуст
    if not waiting_list:
        del waiting_players[topic_pk]
    
    logger.info(f"Найден партнер для {sid} ({name}) в теме {topic_pk}")
    await start_game(topic_pk, partner_sid, sid)

@sio.event
async def answer(sid, data):
    """Обработка ответа игрока на вопрос"""
    logger.info(f"Ответ от {sid}: {data}")
    
    # Валидация данных
    if not isinstance(data, dict):
        logger.warning(f"Неверный формат ответа от {sid}: {data}")
        await sio.emit("error", {"error": "invalid_data", "message": "Invalid answer format"}, to=sid)
        return
    
    index = data.get("index")
    game_uid = data.get("game_uid")
    
    # Проверка существования игры
    if not game_uid or game_uid not in active_games:
        logger.warning(f"Игра не найдена для {sid}: {game_uid}")
        await sio.emit("error", {"error": "game_not_found", "message": "Game not found"}, to=sid)
        return
    
    # Проверка корректности индекса ответа
    if not isinstance(index, int) or index < 1 or index > 4:
        logger.warning(f"Неверный индекс ответа от {sid}: {index}")
        await sio.emit("error", {"error": "invalid_answer_index", "message": "Invalid answer index"}, to=sid)
        return
    
    game = active_games[game_uid]
    player = next((p for p in game.players if p.sid == sid), None)
    
    if not player:
        logger.warning(f"Игрок не найден в игре {game_uid} для sid={sid}")
        return
    
    # Записываем ответ
    game.record_answer(sid, index)
    
    # Проверяем, ответили ли оба игрока
    if not game.both_answered():
        logger.info(f"Ожидание ответа второго игрока в игре {game_uid}")
        return
    
    # Оба игрока ответили - обрабатываем результаты
    feedback = game.evaluate_answers()
    
    # Отправляем результаты обоим игрокам
    for p in game.players:
        await sio.emit("game", {
            "uid": game.uid,
            "question_count": game.question_count,
            "feedback": feedback,
            "players": [{"name": pl.name, "score": pl.score} for pl in game.players]
        }, to=p.sid)
    
    # Проверяем, остались ли еще вопросы
    if game.question_count <= 0:
        logger.info(f"Игра {game_uid} завершена")
        results = {
            "players": [
                {"name": p.name, "score": p.score}
                for p in game.players
            ]
        }
        for p in game.players:
            await sio.emit("over", results, to=p.sid)
        
        # Удаляем игру
        if game_uid in active_games:
            del active_games[game_uid]
        return
    
    # Запускаем задачу для отправки следующего вопроса
    asyncio.create_task(send_next_question(game_uid))

# === Точка входа ===
if __name__ == "__main__":
    import uvicorn
    logger.info("Запуск сервера викторины на http://0.0.0.0:8000")
    uvicorn.run(app_with_socket, host="0.0.0.0", port=8000, log_level="info")