# HW5 — External NBU tool: real examples

Generated: `2026-08-11` (Europe/Kyiv).

The tool is read-only and uses the fixed official NBU HTTPS endpoint. It does not require an API key or confirmation.

## 1. Current USD rate

**User question:** Який офіційний курс USD сьогодні?

**Tool called:** `get_nbu_exchange_rate`

**Input:**

```json
{
  "currency_code": "USD",
  "date": null,
  "amount": 1.0
}
```

**Result:**

```json
{
  "tool_name": "get_nbu_exchange_rate",
  "source": "National Bank of Ukraine",
  "source_url": "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json=",
  "currency_code": "USD",
  "currency_name": "Долар США",
  "requested_date": "2026-08-11",
  "effective_date": "2026-08-11",
  "rate_uah": 44.8305,
  "amount": 1.0,
  "converted_amount_uah": 44.83,
  "special_conditions": false,
  "retrieved_at_utc": "2026-08-10T23:27:08.982561Z"
}
```

**Final answer:** За офіційним курсом НБУ на 2026-08-11: 1 USD = 44.8305 грн.

**Why tool is better than retrieval:** The local knowledge base cannot contain a current official rate.

## 2. Convert 100 EUR to UAH

**User question:** Скільки гривень потрібно для 100 EUR сьогодні?

**Tool called:** `get_nbu_exchange_rate`

**Input:**

```json
{
  "currency_code": "EUR",
  "date": null,
  "amount": 100.0
}
```

**Result:**

```json
{
  "tool_name": "get_nbu_exchange_rate",
  "source": "National Bank of Ukraine",
  "source_url": "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json=",
  "currency_code": "EUR",
  "currency_name": "Євро",
  "requested_date": "2026-08-11",
  "effective_date": "2026-08-11",
  "rate_uah": 51.7815,
  "amount": 100.0,
  "converted_amount_uah": 5178.15,
  "special_conditions": false,
  "retrieved_at_utc": "2026-08-10T23:27:09.263065Z"
}
```

**Final answer:** За офіційним курсом НБУ на 2026-08-11: 1 EUR = 51.7815 грн. 100 EUR = 5178.15 грн.

**Why tool is better than retrieval:** NBU provides the authoritative rate and Decimal performs the calculation.

## 3. Historical PLN rate

**User question:** Який був офіційний курс PLN 1 серпня 2026 року?

**Tool called:** `get_nbu_exchange_rate`

**Input:**

```json
{
  "currency_code": "PLN",
  "date": "2026-08-01",
  "amount": 1.0
}
```

**Result:**

```json
{
  "tool_name": "get_nbu_exchange_rate",
  "source": "National Bank of Ukraine",
  "source_url": "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=PLN&json=&date=20260801",
  "currency_code": "PLN",
  "currency_name": "Злотий",
  "requested_date": "2026-08-01",
  "effective_date": "2026-08-01",
  "rate_uah": 11.8975,
  "amount": 1.0,
  "converted_amount_uah": 11.9,
  "special_conditions": false,
  "retrieved_at_utc": "2026-08-10T23:27:09.533197Z"
}
```

**Final answer:** За офіційним курсом НБУ на 2026-08-01: 1 PLN = 11.8975 грн.

**Why tool is better than retrieval:** The requested historical date is explicit and independently verifiable.

## 4. English GBP request through LLM router

**User question:** How much is 50 GBP in UAH at today's official NBU rate?

**Tool called:** `get_nbu_exchange_rate`

**Input:**

```json
{
  "currency_code": "GBP",
  "date": "2026-08-11",
  "amount": 50.0
}
```

**Result:**

```json
{
  "tool_name": "get_nbu_exchange_rate",
  "source": "National Bank of Ukraine",
  "source_url": "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=GBP&json=&date=20260811",
  "currency_code": "GBP",
  "currency_name": "Фунт стерлінгів",
  "requested_date": "2026-08-11",
  "effective_date": "2026-08-11",
  "rate_uah": 60.5167,
  "amount": 50.0,
  "converted_amount_uah": 3025.84,
  "special_conditions": false,
  "retrieved_at_utc": "2026-08-10T23:27:37.135769Z"
}
```

**Final answer:** According to the official NBU rate effective 2026-08-11, 1 GBP = 60.5167 UAH. 50 GBP = 3025.84 UAH.

**Why tool is better than retrieval:** The router extracts validated parameters, while the final number still comes only from NBU and is formatted deterministically.

## 5. Invalid currency code rejected before HTTP

**User question:** `/rate US`

**Tool called:** no

**Input:**

```json
{
  "currency_code": "US",
  "amount": 1
}
```

**Result:** Pydantic validation error: Value error, currency_code повинен містити рівно 3 латинські літери

**Final answer:** The request is rejected with `/rate` usage guidance.

**Why tool is better than retrieval:** validation prevents an invalid external call; retrieval cannot validate an API input contract.

## RAG control example

**User question:** Як скласти реалістичний план підготовки до іспиту?

**Router decision:** `rag` (currency prefilter did not call the LLM router).

**NBU tool called:** no.

This confirms that ordinary study questions continue through the existing grounded RAG pipeline.
