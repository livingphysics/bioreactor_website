# Bioreactor API Reference

Base URL: `https://issued-fantasy-fighter-specials.trycloudflare.com`

All endpoints require authentication:
```
Authorization: Bearer <API_KEY>
```

---

## System

### Health Check
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/health
```

### List Capabilities
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/capabilities
```

---

## Actuators

### LED

**Get state:**
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/led/state
```

**Set power (0-100%):**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"power": 50}' https://<host>/api/led/control
```

---

### Peltier (Temperature Control)

**Get state:**
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/peltier_driver/state
```

**Set duty cycle and direction:**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"duty_cycle": 50, "direction": "heat"}' https://<host>/api/peltier_driver/control
```

Direction options: `heat`, `cool`, `forward`, `reverse`

---

### Stirrer

**Get state:**
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/stirrer/state
```

**Set duty cycle (0-100%):**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"duty_cycle": 50}' https://<host>/api/stirrer/control
```

---

### Ring Light

**Get state:**
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/ring_light/state
```

**Set color (RGB 0-255):**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"red": 30, "green": 30, "blue": 30}' https://<host>/api/ring_light/control
```

**Set specific pixel:**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"red": 255, "green": 0, "blue": 0, "pixel_index": 0}' https://<host>/api/ring_light/control
```

---

### Pumps

**Get state:**
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/pumps/state
```

**Control pump (velocity in mL/s, negative for reverse):**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"pump_name": "inflow", "velocity": 1.5}' https://<host>/api/pumps/control
```

---

### Relays

**Get state:**
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/relays/state
```

**Set relay state:**
```bash
curl -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"relay_name": "heater", "state": true}' https://<host>/api/relays/control
```

---

## Sensors

### Temperature
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/temp_sensor/state
```
Response: `{"status": "success", "temperature": 23.5, "unit": "celsius"}`

---

### CO2
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/co2_sensor/state
```
Response: `{"status": "success", "co2_ppm": 415.2, "unit": "ppm"}`

---

### O2
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/o2_sensor/state
```
Response: `{"status": "success", "o2_percent": 20.9, "unit": "percent"}`

---

### Optical Density
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/optical_density/state
```
Response: `{"status": "success", "voltages": [1.23, 2.45, 0.98], "unit": "volts"}`

---

### Eyespy ADC
```bash
curl -H "Authorization: Bearer $API_KEY" https://<host>/api/eyespy_adc/state
```
Response: `{"status": "success", "voltages": [2.1, 1.8], "unit": "volts"}`

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 401 | Missing authorization header |
| 403 | Invalid API key |
| 429 | Rate limit exceeded (100 req/min) |
| 503 | Component not available |
