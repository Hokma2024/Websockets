# ws_client_test.py
import socketio
import requests
import json

API_URL = "http://localhost:8000"


def get_token(user: str = "alice") -> str:
    """
    Берём токен у FastAPI-эндпоинта /token.
    """
    resp = requests.get(f"{API_URL}/token", params={"sub": user})
    resp.raise_for_status()
    return resp.text


def wait_event(sio: socketio.SimpleClient, wanted: str, max_steps: int = 10):
    """
    Читаем события через receive() до тех пор, пока не придёт нужное,
    либо сдаёмся после max_steps попыток.
    """
    for _ in range(max_steps):
        event, data = sio.receive()
        print(f"[client] got event={event!r}, data={data!r}")
        if event == wanted:
            return data
    raise RuntimeError(f"Не дождались события {wanted!r}")


def main():
    sio = socketio.SimpleClient()

    # 1) Берём JWT у FastAPI
    print("1) Получаем JWT-токен через /token")
    token = get_token("alice")
    print("   token (обрезано):", token[:32], "...")

    # 2) Подключаемся к Socket.IO-серверу
    print("\n2) Подключаемся к Socket.IO-серверу")
    sio.connect(API_URL, auth={"token": token})
    print("   Подключились")

    # 3) Ловим несколько первых событий (welcome + клиенты + онлайн)
    print("\n3) Ждём несколько первых событий от сервера (для отчётности)")
    for i in range(3):
        event, data = sio.receive()
        print(f"   [{i+1}] event={event!r}, data={data!r}")

    # 4) Тест get_users_online
    print("\n4) Тестируем get_users_online")
    # ВАЖНО: без {}, серверный хэндлер принимает только sid
    sio.emit("get_users_online")
    users_data = wait_event(sio, "users")
    print("   Ответ на get_users_online:", users_data)

    # 5) Тест create_product (валидный кейс)
    print("\n5) Тестируем create_product (валидный)")
    good_product = {
        "title": "Шоколадка",
        "price": 230.0,
        "discount": 5.0,
    }
    sio.emit("create_product", good_product)
    product = wait_event(sio, "product")
    print("   Продукт, который вернул сервер:")
    print("   ", json.dumps(product, ensure_ascii=False, indent=2))

    # 6) Тест create_product (НЕвалидный кейс)
    print("\n6) Тестируем create_product (НЕвалидный)")
    bad_product = {
        "title": "",        # пустой title -> min_length
        "price": -10.0,     # отрицательная цена
        "discount": -5.0,   # отрицательная скидка
    }
    sio.emit("create_product", bad_product)
    errors = wait_event(sio, "errors")
    print("   Ошибки валидации:")
    print("   ", json.dumps(errors, ensure_ascii=False, indent=2))

    # 7) Тест create_transfer (валидный кейс)
    print("\n7) Тестируем create_transfer (валидный)")
    good_transfer = {
        "ac_from": "4321432143214321",
        "ac_to": "7890789078907890",
        "amount": 330.2,
    }
    sio.emit("create_transfer", good_transfer)
    transfer = wait_event(sio, "transfer")
    print("   Успешный перевод:")
    print("   ", json.dumps(transfer, ensure_ascii=False, indent=2))

    print("\nГотово. Отключаемся.")
    sio.disconnect()


if __name__ == "__main__":
    main()
