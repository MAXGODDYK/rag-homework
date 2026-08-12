# HW5: перевірка Telegram-бота

Дата автоматичної live-перевірки: 11 серпня 2026 року.

## Перевірено з Telegram API

- локальний ignored `TELEGRAM_BOT_TOKEN` завантажується;
- `Application.initialize()` успішно виконав Telegram `getMe`;
- підтверджений bot username: `maxgoddyk_rag_homework_bot`;
- application містить 9 handlers;
- зареєстровані команди: `start`, `help`, `provider`, `rate`,
  `status`, `sources`, `reset`.

Токен у output і Git не записувався.

## Перевірено integration tests

| Сценарій | Результат |
|---|---|
| `/rate EUR 100 2026-08-11` | direct validated tool call |
| Natural-language EUR question | NBU tool, RAG не викликано |
| `/sources` після tool | name, input, НБУ, URL, effective date |
| `/reset` | RAG і tool result очищено |
| `/rate US` | validation error, без tool result |
| Rate limiting | збережена логіка 5 запитів / 10 хвилин |
| Звичайний RAG result | попередній chunk output не змінено |

Integration tests використовують fake Telegram objects, providers
та NBU transport, тому не витрачають API і не записують питання.

## Live handler path

Окремо handlers були викликані через контрольований Telegram update
object, але з реальними FreeModel і НБУ API:

| Запит | Фактичний результат |
|---|---|
| `/rate EUR 100` | `get_nbu_exchange_rate`, 5178.15 UAH |
| Natural English GBP question | FreeModel → tool |
| `/sources` після GBP | містить National Bank of Ukraine |

Таким чином перевірено повний command/natural routing path до
зовнішнього API; підмінявся тільки мережевий transport повідомлення
Telegram, щоб тест не надсилав повідомлення реальному користувачу.

## Ручна smoke-перевірка

Для додаткової перевірки відображення при запущеному polling можна
надіслати боту два повідомлення:

```text
/rate EUR 100
How much is 50 GBP in UAH at today's official NBU rate?
```

Після кожного запиту `/sources` має показати
`get_nbu_exchange_rate`, validated input, National Bank of Ukraine
та effective date. Це єдина частина, яку не можна імітувати від
імені реального Telegram-користувача через Bot API.
