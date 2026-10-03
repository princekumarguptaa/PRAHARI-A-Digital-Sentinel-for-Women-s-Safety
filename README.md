# PRAHARI
### प्रहरी — A Digital Sentinel for Women's Safety

## MVP v2 — Emergency System
- Landing page
- Registration/login/logout
- SQLite user database
- Emergency contacts
- One-tap SOS UI
- Browser geolocation capture
- SOS incident creation
- Active incident state
- Resolve/Mark Safe flow

## Run
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Important
This is a development prototype. The SOS endpoint currently records an incident in the local database and optionally receives browser geolocation. It does **not** contact police, emergency services, or real emergency contacts. Do not use it as a real emergency service.
