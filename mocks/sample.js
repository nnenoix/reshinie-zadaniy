// Пример ответа /api/forecast: Москва — Сочи, 01.06.2026, цена 8000 ₽ (получен из реального расчёта).
window.SAMPLE = {
  "route": {
    "code": "MOW-AER",
    "name": "Москва — Сочи",
    "base_price": 9000.0,
    "price_sensitivity": 0.141
  },
  "date": "2026-06-01",
  "price": 8000.0,
  "seats": 900,
  "wanted": 916.0,
  "sold": 900.0,
  "sold_out": true,
  "scenarios": [
    {
      "quantile": 0.1,
      "base_demand": 656.0,
      "wanted": 797.0,
      "sold": 797.0,
      "sold_out": false
    },
    {
      "quantile": 0.2,
      "base_demand": 694.0,
      "wanted": 835.0,
      "sold": 835.0,
      "sold_out": false
    },
    {
      "quantile": 0.3,
      "base_demand": 723.0,
      "wanted": 864.0,
      "sold": 864.0,
      "sold_out": false
    },
    {
      "quantile": 0.4,
      "base_demand": 742.0,
      "wanted": 883.0,
      "sold": 883.0,
      "sold_out": false
    },
    {
      "quantile": 0.5,
      "base_demand": 775.0,
      "wanted": 916.0,
      "sold": 900.0,
      "sold_out": true
    },
    {
      "quantile": 0.6,
      "base_demand": 802.0,
      "wanted": 943.0,
      "sold": 900.0,
      "sold_out": true
    },
    {
      "quantile": 0.7,
      "base_demand": 835.0,
      "wanted": 976.0,
      "sold": 900.0,
      "sold_out": true
    },
    {
      "quantile": 0.8,
      "base_demand": 863.0,
      "wanted": 1004.0,
      "sold": 900.0,
      "sold_out": true
    },
    {
      "quantile": 0.9,
      "base_demand": 923.0,
      "wanted": 1064.0,
      "sold": 900.0,
      "sold_out": true
    }
  ]
};
