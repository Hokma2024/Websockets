document.addEventListener("DOMContentLoaded", () => {
  // Шаблоны Handlebars для разных экранов
  const templates = {
    loader: `
            <div class="screen">
                <div class="status-message">Загрузка...</div>
                <div class="loader"></div>
            </div>
        `,

    topics: `
            <div class="screen">
                <h2>Выберите тему</h2>
                <div class="topics-list">
                    {{#each topics}}
                    <div class="topic-card" data-pk="{{this.pk}}">
                        <div class="name">{{this.name}}</div>
                        <div class="questions-count">{{this.questions.length}} вопросов</div>
                        {{#if this.has_players}}
                        <div class="status">Ищет соперника</div>
                        {{/if}}
                    </div>
                    {{/each}}
                </div>
            </div>
        `,

    playerForm: `
            <div class="screen">
                <a class="back-link" id="back-to-topics">&larr; Назад к темам</a>
                <h2>Введите ваше имя</h2>
                <p class="topic-name">Тема: {{topic.name}}</p>
                <div class="player-form">
                    <div class="input-group">
                        <label for="player-name">Ваше имя</label>
                        <input type="text" id="player-name" placeholder="Например, Алиса" maxlength="20">
                    </div>
                    <button class="submit-btn" id="join-game">Начать игру</button>
                </div>
            </div>
        `,

    waiting: `
            <div class="screen">
                <a class="back-link" id="back-to-topics">&larr; Назад к темам</a>
                <h2>Поиск соперника</h2>
                <div class="status-message">Ожидание другого игрока в теме "{{topic.name}}"</div>
                <div class="loader"></div>
                <p class="hint">Вы будете уведомлены, когда найдется соперник</p>
            </div>
        `,

    game: `
            <div class="screen">
                <div class="players-container">
                    {{#each game.players}}
                    <div class="player-score">
                        <div>{{this.name}}</div>
                        <div>Очки: {{this.score}}</div>
                    </div>
                    {{/each}}
                </div>
                
                <div class="questions-container">
                    <div class="question-text">{{game.current_question.text}}</div>
                    <p class="questions-left">Осталось вопросов: {{game.question_count}}</p>
                    
                    <div class="options-container">
                        {{#each game.current_question.options}}
                        <div class="option" data-index="{{@index}}">
                            {{addOne @index}}. {{this}}
                        </div>
                        {{/each}}
                    </div>
                </div>
            </div>
        `,

    results: `
            <div class="screen results-container">
                <h2 class="results-title">Игра окончена!</h2>
                <p class="final-message">{{message}}</p>
                
                <div class="player-results">
                    {{#each players}}
                    <div class="player-result {{#if winner}}winner{{/if}}">
                        {{name}}: {{score}} очков
                    </div>
                    {{/each}}
                </div>
                
                <button class="submit-btn" id="play-again">Сыграть еще раз</button>
            </div>
        `,

    disconnected: `
            <div class="screen">
                <h2>Соединение потеряно</h2>
                <div class="status-message">Попытка переподключения...</div>
                <div class="loader"></div>
                <p class="hint">Пожалуйста, подождите, мы пытаемся восстановить соединение с сервером</p>
            </div>
        `,

    error: `
            <div class="screen">
                <h2>Ошибка</h2>
                <p class="status-message">{{message}}</p>
                <button class="submit-btn" id="back-to-main">Вернуться на главную</button>
            </div>
        `,
  };

  // Регистрация вспомогательных функций Handlebars
  Handlebars.registerHelper("addOne", function (index) {
    return index + 1;
  });

  // Глобальное состояние приложения
  const state = {
    socket: null,
    topics: [],
    selectedTopic: null,
    game: null,
    playerId: null,
  };

  // Функция для отображения шаблона
  function render(templateName, data = {}) {
    const template = Handlebars.compile(templates[templateName]);
    document.getElementById("app").innerHTML = template(data);
    attachEventListeners();
  }

  // Подключение к Socket.IO
  function connectToServer() {
    state.socket = io("/", {
      transports: ["websocket"],
    });

    // Обработчики событий сокета
    state.socket.on("connect", () => {
      console.log("Подключено к серверу");
      state.socket.emit("get_topics");
    });

    state.socket.on("disconnect", () => {
      console.log("Отключено от сервера");
      render("disconnected");
    });

    state.socket.on("connect_error", (err) => {
      console.error("Ошибка подключения:", err);
      render("error", {
        message: "Не удалось подключиться к серверу. Проверьте соединение.",
      });
    });

    // Получение списка тем
    state.socket.on("topics", (topics) => {
      console.log("Получены темы:", topics);
      state.topics = topics;
      render("topics", { topics: state.topics });
    });

    // Начало игры
    state.socket.on("game", (gameData) => {
      console.log("Получены данные игры:", gameData);
      state.game = gameData;
      render("game", { game: state.game });
    });

    // Завершение игры
    state.socket.on("over", (results) => {
      console.log("Игра завершена:", results);

      let maxScore = Math.max(...results.players.map((p) => p.score));
      let message = "";

      if (results.players[0].score === results.players[1].score) {
        message = "Ничья!";
      } else {
        const winner = results.players.find((p) => p.score === maxScore);
        message = `Победил ${winner.name}!`;
      }

      render("results", {
        message: message,
        players: results.players.map((p) => ({
          ...p,
          winner: p.score === maxScore,
        })),
      });
    });

    // Обработка ошибок
    state.socket.on("error", (error) => {
      console.error("Ошибка от сервера:", error);
      let message = "Произошла ошибка";

      if (error.error === "invalid_name") {
        message = "Пожалуйста, введите ваше имя";
      } else if (error.error === "invalid_topic") {
        message = "Выбрана неверная тема";
      }

      render("error", { message: message });
    });
  }

  // Привязка обработчиков событий
  function attachEventListeners() {
    // Выбор темы
    document.querySelectorAll(".topic-card").forEach((card) => {
      card.addEventListener("click", () => {
        const pk = parseInt(card.getAttribute("data-pk"));
        const topic = state.topics.find((t) => t.pk === pk);

        if (topic) {
          state.selectedTopic = topic;
          render("playerForm", { topic: state.selectedTopic });
        }
      });
    });

    // Кнопка "Назад к темам"
    const backToTopics = document.getElementById("back-to-topics");
    if (backToTopics) {
      backToTopics.addEventListener("click", () => {
        render("topics", { topics: state.topics });
      });
    }

    // Кнопка "Начать игру"
    const joinGameBtn = document.getElementById("join-game");
    if (joinGameBtn) {
      joinGameBtn.addEventListener("click", () => {
        const playerName = document.getElementById("player-name").value.trim();

        if (!playerName) {
          alert("Пожалуйста, введите ваше имя");
          return;
        }

        // Отправляем запрос на присоединение к игре
        state.socket.emit("join_game", {
          topic_pk: state.selectedTopic.pk,
          name: playerName,
        });

        render("waiting", { topic: state.selectedTopic });
      });
    }

    // Выбор ответа
    document.querySelectorAll(".option").forEach((option) => {
      option.addEventListener("click", () => {
        if (
          state.game &&
          !option.classList.contains("selected") &&
          !option.classList.contains("correct")
        ) {
          const index = parseInt(option.getAttribute("data-index"));

          // Отправляем ответ
          state.socket.emit("answer", {
            index: index + 1, // Преобразуем в 1-based индекс
            game_uid: state.game.uid,
          });

          // Визуально помечаем выбранный ответ
          document.querySelectorAll(".option").forEach((opt) => {
            opt.classList.remove("selected");
          });
          option.classList.add("selected");
        }
      });
    });

    // Кнопка "Сыграть еще раз"
    const playAgainBtn = document.getElementById("play-again");
    if (playAgainBtn) {
      playAgainBtn.addEventListener("click", () => {
        state.socket.emit("get_topics");
      });
    }

    // Кнопка "Вернуться на главную" при ошибке
    const backToMainBtn = document.getElementById("back-to-main");
    if (backToMainBtn) {
      backToMainBtn.addEventListener("click", () => {
        state.socket.emit("get_topics");
      });
    }
  }

  // Инициализация приложения
  function init() {
    render("loader");
    connectToServer();
  }

  // Запуск приложения
  init();
});
