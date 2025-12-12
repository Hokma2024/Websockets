import json
import socketio
import requests
import pytest

API_URL = "http://localhost:8000"


def get_token(user: str = "alice") -> str:
    """Берём JWT у FastAPI-эндпоинта /token."""
    resp = requests.get(f"{API_URL}/token", params={"sub": user})
    resp.raise_for_status()
    return resp.text


def wait_event(sio: socketio.SimpleClient, wanted: str, max_steps: int = 10):
    """
    Ждём, пока от сервера не придёт событие с именем wanted.
    Если не пришло за max_steps – падаем.
    """
    for _ in range(max_steps):
        event, data = sio.receive()
        if event == wanted:
            return data
    raise AssertionError(f"Не дождались события {wanted!r}")


@pytest.fixture(scope="module")
def sio():
    """
    Один Socket.IO-клиент на весь модуль тестов.
    Подключаемся с JWT, читаем первые сервисные события и отдаём объект тестам.
    """
    token = get_token("alice")
    client = socketio.SimpleClient()
    client.connect(API_URL, auth={"token": token})

    for _ in range(3):
        event, data = client.receive()
        # print("INIT:", event, data)

    yield client

    client.disconnect()


def test_get_users_online(sio: socketio.SimpleClient):
    """Проверка, что сервер корректно возвращает статистику онлайн-пользователей."""
    sio.emit("get_users_online")
    data = wait_event(sio, "users")

    assert isinstance(data, dict)
    assert "connections" in data
    assert "users" in data
    assert data["connections"] >= 1
    assert data["users"] >= 1


def test_create_product_valid(sio: socketio.SimpleClient):
    """Проверка успешного создания валидного продукта."""
    payload = {
        "title": "Шоколадка",
        "price": 230.0,
        "discount": 5.0,
    }

    sio.emit("create_product", payload)
    product = wait_event(sio, "product")

    assert product["title"] == payload["title"]
    assert product["price"] == payload["price"]
    assert product["discount"] == payload["discount"]


def test_create_product_invalid(sio: socketio.SimpleClient):
    """Проверка, что при невалидных данных сервер возвращает errors."""
    payload = {
        "title": "",        # пусто
        "price": -10.0,     # отрицательная
        "discount": -5.0,   # отрицательная
    }

    sio.emit("create_product", payload)
    errors = wait_event(sio, "errors")

    assert "errors" in errors
    err_list = errors["errors"]
    assert any(e["loc"] == ["title"] for e in err_list)
    assert any(e["loc"] == ["price"] for e in err_list)
    assert any(e["loc"] == ["discount"] for e in err_list)


def test_create_transfer_valid(sio: socketio.SimpleClient):
    """Проверка успешного перевода."""
    payload = {
        "ac_from": "4321432143214321",
        "ac_to": "7890789078907890",
        "amount": 330.2,
    }

    sio.emit("create_transfer", payload)
    transfer = wait_event(sio, "transfer")

    assert transfer["ac_from"] == payload["ac_from"]
    assert transfer["ac_to"] == payload["ac_to"]
    assert transfer["amount"] == payload["amount"]
