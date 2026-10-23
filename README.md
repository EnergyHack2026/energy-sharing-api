# Zdieľňa – FastAPI backend

Prvé API nad existujúcou PostgreSQL databázou. Vyžaduje Python 3.10+ a databázu so schémami, tabuľkami a funkciami zo súboru `../energy-sharing-database/structura.sql`. Tento SQL výpis neobsahuje kompletné DDL; detaily sú v [BACKEND_PLAN.md](BACKEND_PLAN.md).

## Spustenie vo Windows PowerShell

Spúšťaj z priečinka `energy-sharing-api`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

V `.env` nastav `DATABASE_URL` podľa svojej databázy, vygenerovaný token vlož do `DEMO_API_TOKEN` a nastav `DEMO_CUSTOMER_ID` na existujúceho zákazníka (napríklad `2`). Heslo v URL musí mať špeciálne znaky URL zakódované. Použi databázový účet s právom čítať potrebné tabuľky a vykonávať funkcie `energy_app`, vrátane práv na ich podkladové tabuľky. API samo nič nevytvára ani nemení; pripojenia používajú read-only transakcie.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8001
```

Dokumentácia: [Swagger UI](http://127.0.0.1:8001/docs). Klikni **Authorize** a vlož samotný token. Chýbajúci alebo nesprávny token vráti 401, iný zákazník než `DEMO_CUSTOMER_ID` vráti 403. Token predstavuje iba lokálnu testovaciu identitu; pred nasadením treba nahradiť `app/security.py` skutočným prihlásením a overením identity. Token nevkladaj do verejného frontendového kódu.

## Endpointy

| GET | Výsledok |
| --- | --- |
| `/health` | Stav API bez prístupu do DB |
| `/ready` | Kontrola DB, pri nedostupnosti 503 |
| `/api/v1/customers/2` | Základné údaje zákazníka |
| `/api/v1/customers/2/connections` | Odberné miesta cez `get_customer_connections` |
| `/api/v1/customers/2/meters` | Meradlá cez `get_customer_meters` |
| `/api/v1/customers/2/meters/10/measurements?from=2025-01-01T00:00:00&to=2025-01-02T00:00:00` | Merania priradeného meradla |

Čísla `2` a `10` sú príklady; pri meraniach použi `measurement_meter_id` z endpointu `/meters`. Časy zadávaj bez časového pásma, pretože jeho význam v zdrojovej DB nie je potvrdený. Interval je od `from` vrátane po `to` bez koncového okamihu, najviac 31 dní. Číselné hodnoty PostgreSQL `numeric` sa vracajú ako desatinné reťazce, aby sa nestratila presnosť. Merania sú už v kWh za 15 minút.

Duplicity zostávajú zachované, historické priradenie vychádza zo snímky registra. Prázdne `items` neznamená nulovú spotrebu. Odpoveď obsahuje `truncated`: pri `true` zúž časový interval. Parameter `limit` má rozsah 1–10000, predvolene 10000. Agregácie zatiaľ nie sú implementované.

Príklad volania bez uloženia tokenu do kódu:

```powershell
$demoToken = Read-Host 'Token z .env'
Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/customers/2/meters' -Headers @{ Authorization = "Bearer $demoToken" }
```

`/ready` kontroluje iba dostupnosť DB. Chýbajúca tabuľka, funkcia alebo oprávnenie sa prejaví pri zákazníckom dotaze ako 500 s neutrálnou správou. SQL výpis automaticky nespúšťaj ako migráciu.

## Testy

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Testy používajú náhradu DB pripojenia; overujú autorizáciu, chybové stavy, intervaly, priradenie meradla, presnosť a obmedzenie odpovedí. Skutočné pripojenie a kompatibilitu s cieľovou DB treba overiť po vyplnení `.env` cez `/ready` a zákaznícke endpointy.

Správa pripojení vychádza z dokumentácie [Psycopg pool](https://www.psycopg.org/psycopg3/docs/advanced/pool.html) a životný cyklus aplikácie z [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).
