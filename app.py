# app.py
import jwt
import socketio
from textwrap import dedent
import datetime
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
import json
from pydantic import BaseModel
import random
from loguru import logger
import sys
from pydantic import BaseModel, Field, ValidationError
from typing import Annotated
from decimal import Decimal


class TrainTicket(BaseModel):
    train: Annotated[str, Field(description="Номер поезда")]
    caret: Annotated[int, Field(description="Номер вагона")]
    seat: Annotated[int, Field(description="Номер места")]
ticket_1 = TrainTicket(train="AC101", caret=4, seat=27)
ticket_2 = TrainTicket(train="RS101", caret=1, seat=51)


class CompanyShare(BaseModel):
    name: Annotated[str, Field(description="Название компании")]
    ticket: Annotated[str, Field(description="короткий код")]
    value: Annotated[float, Field(description="Стоимость")]
    
tesla_stock = CompanyShare(name="Tesla", ticket="TSLA", value=234.0)
apple_stock = CompanyShare(name="Apple", ticket="AAPL", value=113.4)
amazon_stock = CompanyShare(name="Amazon", ticket="AMZN", value=3225.5)

class Color(BaseModel):
    name: Annotated[str, Field(description="Название цвета")]
    hex: Annotated[str, Field(description="Hex-код цвета")]
    rgb: Annotated[tuple[int, int, int], Field(description="RGB-значение цвета")]
    
black = Color(name="black", hex="#000", rgb=(0,0,0))
red = Color(name="red", hex="#f00", rgb=(255,0,0))


class Product(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=140, description="Название продукта")]
    price: Annotated[float, Field(gt=0, description="Цена продукта")]
    discount: Annotated[float, Field(ge=0, default=0.0, description="Скидка на продукт")]



class Transfers(BaseModel):
    ac_from: Annotated[str, Field(min_length=16, max_length=16, description="Счёт отправителя")]
    ac_to: Annotated[str, Field(min_length=16, max_length=16, description="Счёт получателя")]
    amount: Annotated[float | Decimal, Field(gt=0, description="Сумма перевода")]



class Order(BaseModel):
    customer_name: Annotated[str, Field(min_length=1, max_length=64, description="Имя заказчика")]
    customer_address: Annotated[str, Field(min_length=1, max_length=64, description="Адрес заказчика")]
    total_price: Annotated[float | Decimal, Field(gt=0, description="Общая стоимость заказа")]


SECRET_KEY = "supersecret"  # демо-ключ, в проде храни в ENV
ALGO = "HS256"


# Настройка logger'а Loguru для вывода логов в консоль и файл
loguru_format = "<green>{time}</green> <level>{level}</level> {message}"
logger.remove()
logger.add(sys.stdout, colorize=True, level="DEBUG", format=loguru_format)
logger.add("logs.log", level="DEBUG", format=loguru_format, rotation="10 MB")


# === Модуль 2.2, Практика 2: учёт неизвестных событий ===
lost_queries = {"lost": 0}

# === Модуль 2.2, Практика 3: счётчик per-sid ===
scores = {}

# === Модуль 2.2 + 2.3: список клиентов, статус сервера, учёт времени сессий ===
clients: list[str] = []
sessions: dict[str, datetime.datetime] = {}

server_status = {
    0: "Сервер пуст",        # Модуль 2.3, Задание 4 — статус сервера
    1: "Пользователь один",
    2: "Команда в сборе",
}

# === Модуль 3.1, Практика 2–3: управление комнатами ===
rooms: dict[str, set[str]] = {}

# === Модуль 3.1, Задание 4: цветные комнаты red/green/blue ===
rooms_color = {
    "red": set(),
    "green": set(),
    "blue": set(),
}
sid_to_room_color: dict[str, str] = {}

# ====== (ASGI) ======
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

fastapi_app = FastAPI()

# ====== HTML для теста (для всех практик, где нужен фронт) ======
SOCKET_TEST_HTML = dedent("""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Socket.IO test</title>
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <style>
    body { font-family: sans-serif; padding: 16px; }
    h2 { margin-top: 16px; }
    section { border: 1px solid #ccc; padding: 8px; margin-bottom: 8px; }
    label { display: block; margin: 4px 0; }
    input { margin-right: 4px; }
    button { margin: 2px; }
    #log { border: 1px solid #000; padding: 8px; margin-top: 12px; height: 260px; overflow: auto; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Socket.IO тест (<span id="userHeader"></span>)</h1>

  <section>
    <h2>1. Подключение и онлайн</h2>
    <button id="btnUsers">get_users_online</button>
  </section>

  <section>
    <h2>2. Комнаты</h2>
    <label>
      Room:
      <input id="roomName" placeholder="room1 / lobby / red / ..." />
    </label>
    <button id="btnJoinRoom">join_room</button>
    <button id="btnLeaveRoom">leave_room</button>
    <button id="btnProfileOwns">profile (owns_rooms)</button>
  </section>

  <section>
    <h2>3. Профили (join / get_profile)</h2>
    <div>
      <label>name: <input id="profileName" placeholder="Alice" /></label>
      <label>surname: <input id="profileSurname" placeholder="Smith" /></label>
      <label>id: <input id="profileId" placeholder="123" /></label>
      <button id="btnSendJoinProfile">join (сохранить профиль в сессии)</button>
    </div>
    <div style="margin-top: 6px;">
      <label>target sid: <input id="targetSid" placeholder="вставь чужой sid" /></label>
      <button id="btnGetProfileBySid">get_profile по sid</button>
    </div>
  </section>

  <section>
    <h2>4. Счётчик неизвестных событий и score</h2>
    <button id="btnLost">unknown_event + count_queries</button>
    <button id="btnScoreInc">increase_score</button>
    <button id="btnScoreDec">decrese_score</button>
    <button id="btnScoreGet">get_score</button>
  </section>

  <section>
    <h2>5. Чат / message</h2>
    <label>
      Text:
      <input id="chatText" placeholder="Сообщение в свою цветную комнату" />
    </label>
    <button id="btnSendMessage">emit("message", {{ text }})</button>
    <button id="btnPing">ping_me</button>
  </section>

  <section>
    <h2>6. HTTP broadcast</h2>
    <label>
      Broadcast text:
      <input id="broadcastText" placeholder="через POST /broadcast" />
    </label>
    <button id="btnBroadcast">POST /broadcast</button>
  </section>

  <section>
    <h2>7. Pydantic модели: Product / Transfer / Order</h2>

    <h3>7.1 Product</h3>
    <label>title: <input id="prodTitle" placeholder="Шоколадка" /></label>
    <label>price: <input id="prodPrice" placeholder="230.0" /></label>
    <label>discount: <input id="prodDiscount" placeholder="5.0" /></label>
    <button id="btnCreateProduct">create_product</button>

    <h3>7.2 Transfer</h3>
    <label>ac_from: <input id="trFrom" placeholder="4321432143214321" /></label>
    <label>ac_to: <input id="trTo" placeholder="7890789078907890" /></label>
    <label>amount: <input id="trAmount" placeholder="330.2" /></label>
    <button id="btnCreateTransfer">create_transfer</button>

    <h3>7.3 Order</h3>
    <label>customer_name: <input id="ordName" placeholder="Алиса" /></label>
    <label>customer_address: <input id="ordAddress" placeholder="Random Street" /></label>
    <label>total_price: <input id="ordTotalPrice" placeholder="500.3" /></label>
    <button id="btnCreateOrder">create_order</button>
  </section>

  <pre id="log"></pre>

  <script>
    const log = (m) => {
      const el = document.getElementById("log");
      el.textContent += m + "\\n";
      el.scrollTop = el.scrollHeight;
    };

    // Берём user из query-параметра ?user=...
    const params = new URLSearchParams(window.location.search);
    const user = params.get("user") || "alice";
    document.getElementById("userHeader").textContent = 'user="' + user + '"';

    // 1) получаем токен от сервера для выбранного user
    fetch("/token?sub=" + encodeURIComponent(user))
      .then(r => r.text())
      .then(token => {
        log("token: " + token.slice(0, 32) + "...");

        // 2) коннектимся с auth.token
        const socket = io("/", {
          transports: ["websocket"],
          auth: { token }
        });

        // ===== СЛУШАЕМ СОБЫТИЯ =====
        socket.on("connect", () => log("connected: " + socket.id));
        socket.on("disconnect", (reason) => log("disconnected: " + reason));
        socket.on("connect_error", (err) => log("⚠ connect_error: " + err.message));

        socket.on("message",  (data) => log("message: "  + JSON.stringify(data)));
        socket.on("users",    (data) => log("users: "    + JSON.stringify(data)));
        socket.on("update",   (data) => log("update: "   + JSON.stringify(data)));
        socket.on("queries",  (data) => log("queries: "  + JSON.stringify(data)));
        socket.on("score",    (data) => log("score: "    + JSON.stringify(data)));
        socket.on("profile",  (data) => log("profile: "  + JSON.stringify(data)));

        // новые события
        socket.on("errors",   (data) => log("errors: "   + JSON.stringify(data)));
        socket.on("product",  (data) => log("product: "  + JSON.stringify(data)));
        socket.on("transfer", (data) => log("transfer: " + JSON.stringify(data)));
        socket.on("order",    (data) => log("order: "    + JSON.stringify(data)));

        // ===== КНОПКИ / ДЕЙСТВИЯ =====

        // 1. Онлайн
        document.getElementById("btnUsers").onclick = () => {
          socket.emit("get_users_online");
        };

        // 2. Комнаты
        document.getElementById("btnJoinRoom").onclick = () => {
          const room = document.getElementById("roomName").value || "room1";
          socket.emit("join_room", { room });
        };

        document.getElementById("btnLeaveRoom").onclick = () => {
          const room = document.getElementById("roomName").value || "room1";
          socket.emit("leave_room", { room_id: room });
        };

        document.getElementById("btnProfileOwns").onclick = () => {
          socket.emit("profile");
        };

        // 3. Профили
        document.getElementById("btnSendJoinProfile").onclick = () => {
          const name    = document.getElementById("profileName").value    || "Alice";
          const surname = document.getElementById("profileSurname").value || "Smith";
          const idVal   = document.getElementById("profileId").value      || "123";
          socket.emit("join", { name, surname, id: idVal });
        };

        document.getElementById("btnGetProfileBySid").onclick = () => {
          const target = document.getElementById("targetSid").value.trim();
          if (!target) {
            log("⚠ targetSid пуст");
            return;
          }
          socket.emit("get_profile", { sid: target });
        };

        // 4. Unknown + lost_queries + score
        document.getElementById("btnLost").onclick = () => {
          socket.emit("totally_unknown_event", { foo: 1 });
          socket.emit("count_queries");
        };

        document.getElementById("btnScoreInc").onclick = () => {
          socket.emit("increase_score");
        };
        document.getElementById("btnScoreDec").onclick = () => {
          socket.emit("decrese_score");
        };
        document.getElementById("btnScoreGet").onclick = () => {
          socket.emit("get_score");
        };

        // 5. message в цветную комнату + ping_me
        document.getElementById("btnSendMessage").onclick = () => {
          const text = document.getElementById("chatText").value || ("hello from " + user);
          socket.emit("message", { text });
        };

        document.getElementById("btnPing").onclick = () => {
          socket.emit("ping_me", {});
        };

        // 6. HTTP broadcast (через FastAPI)
        document.getElementById("btnBroadcast").onclick = () => {
          const text = document.getElementById("broadcastText").value || "Hi from HTTP client";
          fetch("/broadcast", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
          }).then(() => log("HTTP POST /broadcast sent"));
        };

        // 7. Pydantic модели

        // Product
        document.getElementById("btnCreateProduct").onclick = () => {
          const title    = document.getElementById("prodTitle").value || "Шоколадка";
          const priceStr = document.getElementById("prodPrice").value || "230.0";
          const discStr  = document.getElementById("prodDiscount").value || "5.0";

          const price = parseFloat(priceStr);
          const discount = parseFloat(discStr);

          socket.emit("create_product", {
            title,
            price,
            discount: isNaN(discount) ? 0 : discount,
          });
        };

        // Transfer
        document.getElementById("btnCreateTransfer").onclick = () => {
          const acFrom  = document.getElementById("trFrom").value    || "4321432143214321";
          const acTo    = document.getElementById("trTo").value      || "7890789078907890";
          const amtStr  = document.getElementById("trAmount").value  || "330.2";
          const amount  = parseFloat(amtStr);

          socket.emit("create_transfer", {
            ac_from: acFrom,
            ac_to: acTo,
            amount,
          });
        };

        // Order
        document.getElementById("btnCreateOrder").onclick = () => {
          const name  = document.getElementById("ordName").value        || "Алиса";
          const addr  = document.getElementById("ordAddress").value     || "Random Street";
          const total = document.getElementById("ordTotalPrice").value  || "500.3";
          const totalNum = parseFloat(total);

          socket.emit("create_order", {
            customer_name: name,
            customer_address: addr,
            total_price: totalNum,
          });
        };
      });
  </script>
</body>
</html>
""")





# === Модуль 2.5, Практика 1–2: HTTP главная страница + нотификация message ===
@fastapi_app.get("/", response_class=PlainTextResponse)
async def index():
    # Практика 2: при обращении к главной странице слать всем message {"text": "..."}
    await sio.emit("message", {"text": "someone visited over http"})
    # Практика 1: вывод списка активных клиентов по HTTP
    return json.dumps(clients, ensure_ascii=False)


@fastapi_app.get("/test", response_class=HTMLResponse)
async def test_page(user: str = Query(default="alice")):
    """
    Тестовая страница для проверки Socket.IO-подключения и JWT-аутентификации.
    """
    return SOCKET_TEST_HTML



# ====== JWT helpers ======
def create_jwt(sub: str) -> str:
    """
    Создать JWT-токен для указанного пользователя.
    """
    token = jwt.encode({"sub": sub}, SECRET_KEY, algorithm=ALGO)
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_jwt(token: str):
    """
    Проверить JWT-токен и вернуть payload, либо None, если токен невалиден.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
    except jwt.InvalidTokenError:
        return None


# === Endpoint для выдачи демо-JWT (поддержка всех практик с авторизацией) ===
@fastapi_app.get("/token", response_class=PlainTextResponse)
async def issue_token(sub: str = Query(..., description="User identifier")):
    """
    Endpoint для выдачи демо-JWT по идентификатору пользователя.
    """
    return create_jwt(sub)


# === Модуль 2.5, Практика 3: трансляция по HTTP POST /broadcast ===
class BroadcastIn(BaseModel):
    message: str


@fastapi_app.post("/broadcast")
async def broadcast(payload: BroadcastIn):
    await sio.emit("message", {"text": payload.message})


# обернуть FastAPI в Socket.IO-приложение
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

# ====== Хранилище состояния (общая инфраструктура) ======
online_sids: set[str] = set()          # все активные соединения (по вкладкам)
user_to_sids: dict[str, set[str]] = {} # user_id -> множество sid


def add_user_sid(user_id: str, sid: str) -> None:
    """
    Зарегистрировать новое соединение sid для пользователя user_id.
    """
    online_sids.add(sid)
    user_to_sids.setdefault(user_id, set()).add(sid)


def remove_sid(sid: str) -> None:
    """
    Удалить соединение sid и почистить привязку к пользователю, если нужно.
    """
    online_sids.discard(sid)
    for uid, sids in list(user_to_sids.items()):
        if sid in sids:
            sids.discard(sid)
            if not sids:
                user_to_sids.pop(uid, None)


def count_unique_users() -> int:
    """
    Количество уникальных пользователей онлайн.
    """
    return len(user_to_sids)


# === Модуль 2.3, Задание 4: статус сервера ===
def get_status(n: int) -> str:
    key = min(n, 2)
    return server_status[key]


# === Модуль 3.1, Практика 2–3: сериализация состояния комнат ===
def build_rooms_state() -> dict[str, list[str]]:
    return {room: list(sids) for room, sids in rooms.items()}


# ====== Обработчики Socket.IO ======

# === Модуль 2.2/2.3/3.1/3.1(цветные) — основной connect с авторизацией и логикой ===
@sio.event
async def connect(sid, environ, auth):
    """
    Аутентифицировать новое Socket.IO-подключение по JWT и отметить пользователя онлайн.
    """
    # 1) достаём токен
    token = None
    if isinstance(auth, dict):
        token = auth.get("token")
    if not token:
        token = environ.get("HTTP_AUTHORIZATION")
        if token and token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]

    # 2) верификация (JWT)
    payload = decode_jwt(token) if token else None
    if not payload or "sub" not in payload:
        return False

    user_id = str(payload["sub"])

    # === Модуль 2.2, Практика 1: список клиентов ===
    clients.append(sid)

    # === Модуль 2.3, Задание 1: приветствие / Welcome to the server (по смыслу) ===
    await sio.emit("message", {"content": f"User {user_id} connected."}, room=sid)

    # сохранить user_id в сессии сокета
    await sio.save_session(sid, {"user_id": user_id})
    add_user_sid(user_id, sid)
    session = await sio.get_session(sid)
    session["messages_sent"] = 0
    await sio.save_session(sid, session)
    # === Модуль 3.2, Задание 3: добавить owns_rooms ===
    session = await sio.get_session(sid)
    session["owns_rooms"] = []
    await sio.save_session(sid, session)


    # === Модуль 3.1, Задание 1: добавить в lobby и оповестить остальных ===
    await sio.enter_room(sid, "lobby")
    await sio.emit("update", {"message": "user_joined"}, room="lobby", skip_sid=sid)

    # === Модуль 2.3, Задание 5: учёт времени подключения ===
    sessions[sid] = datetime.datetime.now()

    # === Модуль 2.3, Задания 2–3: вывести список и онлайн ===
    await sio.emit("message", {"clients": clients}, to=sid)
    await sio.emit("message", {"online": len(clients)})

    logger.debug(f"Клиент {sid} подключился")
    logger.info(get_status(len(clients)))
    logger.info(clients)
    logger.info(
        f"connect: sid={sid}, user={user_id}, "
        f"online_sids={len(online_sids)}, users={count_unique_users()}"
    )

    # === Модуль 3.1, Задание 2: вести словарь rooms и рассылать state ===
    rooms.setdefault("lobby", set()).add(sid)
    state = build_rooms_state()
    await sio.emit("update", state)

    # === Модуль 3.1, Задание 4: распределение в цветные комнаты ===
    room = random.choice(["red", "green", "blue"])
    await sio.enter_room(sid, room)
    rooms_color[room].add(sid)
    sid_to_room_color[sid] = room
    
    logger.info(f"Пользователь {sid} добавлен в цветную комнату '{room}'")


# === Модуль 2.2, Практика 3: счётчик per-sid ===
@sio.event
async def increase_score(sid):
    """
    Увеличить счёт пользователя на 1.
    """
    scores.setdefault(sid, 0)
    scores[sid] += 1


@sio.event
async def decrese_score(sid):
    """
    Уменьшить счёт пользователя на 1.
    """
    scores.setdefault(sid, 0)
    scores[sid] -= 1


@sio.event
async def get_score(sid):
    """
    Отправить значение счёта для текущего sid.
    """
    await sio.emit("score", {"score": scores.get(sid, 0)}, room=sid)


@sio.event
async def ping_me(sid, data):
    await sio.emit("message", {"content": "pong"}, room=sid)
    


# === Модуль 2.2, Практика 1; Модуль 2.3, Задания 3–5 ===
@sio.event
async def disconnect(sid):
    """
    Обработать разрыв соединения, убрать sid из онлайна и вывести статус.
    """
    try:
        session = await sio.get_session(sid)
        user_id = session.get("user_id")
    except KeyError:
        user_id = None

    if sid in clients:
        clients.remove(sid)

    remove_sid(sid)

    logger.debug("Клиент отключился!")
    logger.debug(f"Клиент {sid} отключился")
    logger.info(get_status(len(clients)))
    logger.info(clients)

    # Модуль 2.3, Задание 5 — время сессии
    start = sessions.pop(sid, None)
    if start is not None:
        duration = datetime.datetime.now() - start
        logger.info(f"Клиент {sid} отключился, время сессии: {duration}")
    else:
        logger.error(f"Клиент {sid} отключился, но время старта не найдено")

    logger.info(
        f"disconnect: sid={sid}, user={user_id}, "
        f"online_sids={len(online_sids)}, users={count_unique_users()}"
    )


# === Модуль 2.2, Практика 1: get_users_online ===
@sio.event
async def get_users_online(sid):
    """
    Отправить запрашивающему количество соединений и уникальных пользователей онлайн.
    """
    data = {"connections": len(online_sids), "users": count_unique_users()}
    await sio.emit("users", data, room=sid)


# === Модуль 2.2, Практика 2: учёт неизвестных событий ===
@sio.on("*")
async def unknown_event(event, sid, data):
    """
    Обработчик неизвестных событий для отладки и статистики.
    """
    lost_queries["lost"] += 1


@sio.event
async def count_queries(sid):
    """
    Отправить количество потерянных запросов.
    """
    await sio.emit("queries", {"lost": lost_queries["lost"]}, room=sid)


# === Модуль 3.1, Практика 2–3: join с обновлением карты комнат ===
@sio.event
async def join_room(sid, data):
    """
    Переместить пользователя в указанную комнату и разослать всем список комнат.
    """
    room = data.get("room") or data.get("room_id")
    if not room:
        return

    for r in list(sio.rooms(sid)):
        if r != sid:
            await sio.leave_room(sid, r)

    for room_name, sids in list(rooms.items()):
        sids.discard(sid)
        if not sids:
            rooms.pop(room_name)
            
    current_members = rooms.get(room)
    is_new_room = (current_members is None) or (len(current_members) == 0)

    await sio.enter_room(sid, room)
    rooms.setdefault(room, set()).add(sid)
    
    logger.info(f"Пользователь {sid} присоединился к комнате '{room}'")

    
    if is_new_room:
        session = await sio.get_session(sid)
        owns = session.get("owns_rooms", [])
        if room not in owns:
            owns.append(room)
        session["owns_rooms"] = owns
        await sio.save_session(sid, session)
    
    
    state = build_rooms_state()
    await sio.emit("update", state)



# Старый leave_room из ранних задач
@sio.event
async def leave_room(sid, data):
    """
    Убрать текущее соединение из комнаты и разослать системное сообщение.
    """
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    room_id = str(data.get("room_id"))
    if not room_id:
        return
    await sio.leave_room(sid, room_id)
    await sio.emit(
        "chat",
        {"sys": True, "text": f"{user_id} left {room_id}"},
        room=room_id,
        skip_sid=None,
    )


# === Модуль 3.X, Задание 2: join + get_profile через сессию ===

@sio.event
async def join(sid, data):
    """
    Клиент присылает:
      join {"name": "...", "surname": "...", "id": ...}

    Сервер НИЧЕГО не отправляет в ответ,
    только сохраняет профиль пользователя в его сессии.
    """
    
    name = data.get("name")
    surname = data.get("surname")
    user_id = data.get("id")

    session = await sio.get_session(sid)

    session["profile"] = {
        "name": name,
        "surname": surname,
        "id": user_id,
    }

    await sio.save_session(sid, session)


@sio.event
async def get_profile(sid, data):
    """
    Клиент присылает:
      get_profile {"sid": "...."}

    Сервер находит профиль по этому sid и отправляет
    только запросившему событие profile с профилем пользователя.
    """
    target_sid = data.get("sid")
    if not target_sid:
        return

    try:
        target_session = await sio.get_session(target_sid)
    except KeyError:
        return

    profile = target_session.get("profile")
    if not profile:
        return

    await sio.emit("profile", profile, room=sid)

# === Модуль 3.2, Задание 3: profile -> owns_rooms ===
@sio.event
async def profile(sid):
    """
    Клиент присылает:
      profile

    В ответ получает:
      profile {"owns_rooms": [...]}
    """
    session = await sio.get_session(sid)
    owns = session.get("owns_rooms", [])
    await sio.emit("profile", {"owns_rooms": owns}, room=sid)


# === Модуль 3.1, Задания 4–5: message + молчаливая lobby ===
@sio.event
async def message(sid, data):
    """
    Если пользователь в lobby — выкинуть его из lobby и не слать сообщение.
    Иначе — разослать текст всем в его цветной комнате, кроме него.
    """
    text = data.get("text")
    if text is None:
        logger.error(f"Событие 'message' без поля 'text' от sid={sid}: {data!r}")
        return

    text = str(text).strip()
    if not text:
        logger.error(f"Событие 'message' с пустым 'text' от sid={sid}: {data!r}")
        return

    session = await sio.get_session(sid)
    current = session.get("messages_sent", 0)
    session["messages_sent"] = current + 1
    await sio.save_session(sid, session)
    
    
    # Задание 5: lobby — комната, где нельзя говорить
    user_rooms = sio.rooms(sid)
    if "lobby" in user_rooms:
        await sio.leave_room(sid, "lobby")

        lobby_set = rooms.get("lobby")
        if lobby_set:
            lobby_set.discard(sid)
            if not lobby_set:
                rooms.pop("lobby")

        return  # сообщение не отправляем

    # Задание 4: цветные комнаты red/green/blue
    room = sid_to_room_color.get(sid)
    if not room:
        return

    await sio.emit(
        "message",
        {"text": text},
        room=room,
        skip_sid=sid,
    )


@sio.event
async def create_product(sid, data):
    logger.debug(f"create_product от sid={sid}: {data!r}")
    try:
        product = Product(**data)
    except ValidationError as e:
        logger.error(f"Ошибка валидации Product от sid={sid}: {e}")
        await sio.emit(
            "errors",
            {"errors": e.errors()},
            room=sid,
        )
        return

    product_dict = product.model_dump()
    logger.info(f"Продукт успешно создан для sid={sid}: {product_dict}")

    await sio.emit(
        "product",
        product_dict,
        room=sid,
    )
    
    
@sio.event    
async def create_transfer(sid, data):
    logger.debug(f"create_transfer от sid={sid}: {data!r}")
    try:
        transfer = Transfers(**data)
    except ValidationError as e:
        logger.error(f"Ошибка валидации Transfers от sid={sid}: {e}")
        await sio.emit(
            "errors",
            {"errors": e.errors()},
            room=sid,
        )
        return

    transfer_dict = transfer.model_dump()
    logger.info(f"Перевод успешно создан для sid={sid}: {transfer_dict}")

    await sio.emit(
        "transfer",
        transfer_dict,
        room=sid,
    )
    
@sio.event
async def create_order(sid, data):
    logger.debug(f"create_transfer1 от sid={sid}: {data!r}")
    try:
        order = Order(**data)
    except ValidationError as e:
        logger.error(f"Ошибка валидации Order от sid={sid}: {e}")
        await sio.emit(
            "errors",
            {"errors": e.errors()},
            room=sid,
        )
        return

    order_dict = order.model_dump()
    logger.info(f"Заказ успешно создан для sid={sid}: {order_dict}")

    await sio.emit(
        "order",
        order_dict,
        room=sid,
    )



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
