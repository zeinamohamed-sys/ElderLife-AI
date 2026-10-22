# ElderLife AI

AI-powered safety platform for older adults living alone: daily check-ins, fall and activity events, a personal behaviour baseline,
risk scoring with explanations ("Why?"), smart escalation, a care plan, caregiver coordination and analytics.
All demo data is synthetic. Only events, keypoints and scores are stored, never video or images.
The care plan shows recorded reminders only. It does not diagnose or change doses.

## Run it (Windows, VS Code)
Backend (Python 3.10+), first terminal:

    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1          (PowerShell)   |   .venv\Scripts\activate.bat (CMD)   |   source .venv/bin/activate (Mac/Linux)
    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload

API docs: http://localhost:8000/docs

Frontend (Node 18+), second terminal:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. Sign in as `admin / admin123`, press "Load sample data". Caregiver demo accounts: `sara / care123`, `omar / care123`.
The person's own screen: http://localhost:5173/#/elder (6 digit code is shown on the person's page and in Admin).

## What is inside
| Area | What it does |
|---|---|
| Roles | Admin sees everyone, caregivers see only their people. Admin page: add caregivers and people, assign who looks after whom. |
| Languages | English and العربية. Settings switches the whole app (menus, alerts, risk reasons and the person's screen) and turns the layout right-to-left for Arabic. Alerts by email/Telegram follow the account language. |
| Person's screen | Large buttons: check in, "I'm OK", care-plan checkboxes, "I need help" (immediate caregiver notification). |
| Check-ins | Scheduled daily. The system learns each person's usual check-in delay and flags later than usual. |
| Baseline | Personal activity baseline learned from each person's history. Deviation is part of the risk. |
| Fall handling | Low-confidence falls are ignored. A fall first asks the person (verification window, default 60 s). Only no answer raises the risk. |
| Escalation | Ask the person, reminder, caregiver notified, emergency contact. Cancelled by "I'm OK" or by a caregiver. After an acknowledgement the person is snoozed for 30 min. |
| Notifications | In-app log, optional Telegram (`TELEGRAM_BOT_TOKEN`) and Email (`SMTP_*`). |
| Pose endpoint | `POST /vision/pose` takes body keypoints and returns walking / standing / sitting / bending / lying / falling (rule-based placeholder with the contract a trained model would use). |
| AI models | Learned risk model (with safety rules and per-prediction explanations), learned activity and fall model, personal-baseline anomaly detection, all evaluated in `ml/reports/REPORT.md` (synthetic data). `ML_MODE=off` switches back to the rules. |
| Analytics | Alerts per day, response time, false-alarm rate, falls by hour, CSV exports for Power BI (see docs/POWER_BI.md). |
| Data tools | `tools/generate_dataset.py` makes a labelled synthetic dataset for EDA and anomaly experiments. `tools/simulate_pose.py` plays a walking-then-fall sequence against the API. |

## Research and evaluation
- `docs/RESEARCH.md`: existing products, papers, datasets, gap, risks, draft decision, sources.
- `ml/README.md` and `ml/reports/REPORT.md`: how the models are trained and how they compare with the rules. Retrain with `python ml/run_all.py`.

## Where the AI team plugs in
- `backend/app/risk.py`: the hybrid `assess()` loads `models/risk_model.json`. Swap in a stronger model but keep `features_from_signals()` and the safety floor.
- `backend/app/vision.py`: `classify_auto()` uses `models/pose_model.json`. Replace it with a CV model, or call `POST /events` directly
  with `{elderly_id, kind: "fall"|"activity"|"ok"|"sos", value}`. For falls `value` is the model confidence (0 to 1).
- Services authenticate with the header `X-Device-Key` (env `DEVICE_KEY`, default `dev-key`).

## Settings (environment variables, all optional)
`DATABASE_URL`, `SECRET_KEY`, `DEVICE_KEY`, `ESCALATION_STEP_SECONDS` (30), `VERIFY_SECONDS` (60), `FALL_MIN_CONFIDENCE` (0.6),
`ACK_SNOOZE_MINUTES` (30), `ML_MODE` (auto or off), `DEFAULT_LANG` (en), `TELEGRAM_BOT_TOKEN`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.
Change `SECRET_KEY` and `DEVICE_KEY` before any real deployment.

## Languages (English / العربية)
- The screen language is chosen in **Settings** (also on the sign-in screen and on the person's own screen). It is remembered on the device and saved on the account with `PUT /auth/lang`; `GET /languages` lists what is available.
- Every request carries `Accept-Language`, and the API answers in that language: risk reasons, the next step, alert stage texts, API errors and notifications. Client code can pass the header itself (`Accept-Language: ar`).
- Nothing user-facing is stored as a finished sentence. Alerts and notifications keep a message key plus its parameters (`backend/app/i18n.py`), so the CSV exports and older rows stay readable in English and translations can be improved later.
- Emails and Telegram messages go out in the caregiver's account language. `DEFAULT_LANG` picks the language used when a request asks for none.
- Adding a third language means adding a table in `backend/app/i18n.py` and `frontend/src/locales/`; the test `backend/tests/test_i18n.py` fails if the two frontend tables or the backend tables drift apart.

## Tests
    cd backend
    python -m unittest discover -s tests

## Docker
    docker compose up --build      # frontend http://localhost:5173, API http://localhost:8000 (PostgreSQL inside)

## Known limits
Models are trained on synthetic data only (not validated on real older adults), demo-grade security (see settings), SQLite by default,
no SMS, no mobile app, only English and Arabic are translated. The database file is `elderlife4.db`; older `elderlife*.db` files are not used.
