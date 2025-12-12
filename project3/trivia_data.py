from typing import List
from models import Topic, Question

# Данные из Google таблицы (упрощенная версия)
# Для полной реализации можно использовать библиотеку gspread для получения данных из Google таблиц
RAW_TOPICS = [
    {
        "pk": 1,
        "name": "Python",
        "questions": [
            {
                "text": "Какой тип данных в Python является неизменяемым?",
                "options": ["Список", "Словарь", "Кортеж", "Множество"],
                "correct": 3  # 1-based index
            },
            {
                "text": "Что возвращает функция type() в Python?",
                "options": ["Значение переменной", "Тип объекта", "Длину объекта", "Хэш объекта"],
                "correct": 2
            },
            {
                "text": "Какой оператор используется для наследования класса в Python?",
                "options": ["implements", "extends", "inherits", "Нет специального оператора"],
                "correct": 4
            }
        ]
    },
    {
        "pk": 2,
        "name": "Git",
        "questions": [
            {
                "text": "Какая команда создает новую ветку в Git?",
                "options": ["git branch new", "git checkout -b new", "git new branch", "git create branch"],
                "correct": 2
            },
            {
                "text": "Что делает команда git stash?",
                "options": ["Сохраняет изменения во временное хранилище", "Отправляет изменения на сервер", "Создает новую ветку", "Удаляет локальные изменения"],
                "correct": 1
            }
        ]
    },
    {
        "pk": 3,
        "name": "Веб-технологии",
        "questions": [
            {
                "text": "Что означает аббревиатура API?",
                "options": ["Application Programming Interface", "Advanced Programming Instructions", "Automated Processing Integration", "Application Protocol Interface"],
                "correct": 1
            },
            {
                "text": "Какой протокол используется для безопасной передачи данных в вебе?",
                "options": ["HTTP", "FTP", "HTTPS", "SMTP"],
                "correct": 3
            },
            {
                "text": "Что такое DOM в веб-разработке?",
                "options": ["Система управления базами данных", "Объектная модель документа", "Методология разработки", "Фреймворк для фронтенда"],
                "correct": 2
            }
        ]
    }
]

def load_topics() -> List[Topic]:
    topics = []
    for raw in RAW_TOPICS:
        questions = [
            Question(
                text=q["text"],
                options=q["options"],
                correct_index=q["correct"]
            )
            for q in raw["questions"]
        ]
        topics.append(Topic(pk=raw["pk"], name=raw["name"], questions=questions))
    return topics