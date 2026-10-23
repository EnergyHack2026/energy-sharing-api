# Návrh založenia backendu

Tento dokument je iba plán. Backend zatiaľ nie je implementovaný a databáza ani frontend sa nemenia. Vychádza zo súboru `../energy-sharing-database/structura.sql` a z existujúceho README, ktoré pre API určuje FastAPI.

## 1. Čo už máme

- PostgreSQL so schémou `energy` pre merania a schémou `energy_registry_20261023` pre zákaznícky register.
- `energy.measurements`: `meter_id`, `observed_at`, `energy_kwh`, `source_file_id`. Merania sú rozdelené do mesačných partícií od januára 2025 po september 2026.
- Funkcie v `energy_app`, ktoré vracajú JSON:
  - `get_customer_by_number(text)` – základné údaje zákazníka;
  - `get_customer_connections(integer)` – odberné miesta a ich parametre;
  - `get_customer_meters(integer)` – meradlá vrátane prepojenia na merania.
- Statický frontend, ktorý zatiaľ používa demo dáta.

## 2. Čo treba overiť pred implementáciou

SQL súbor nie je kompletný inicializačný skript novej databázy. Používa objekty, ktorých vytvorenie neobsahuje:

- schémy `energy`, `energy_registry_20261023`, `energy_app`;
- tabuľky registra `customers`, `customer_connections`, `connection_meters`, `meter_points`;
- tabuľky `energy.meter_points` a `energy.source_files`.

Najprv overiť ich existenciu v cieľovej databáze a získať úplné definície, dátové typy, kľúče a oprávnenia. Existujúci súbor nespúšťať automaticky pri štarte API: obsahuje aj `DROP FUNCTION`, zmeny vlastníka a ukážkové dotazy. Prípravu prázdnej databázy neskôr oddeliť do kontrolovaných migrácií v databázovom projekte.

Pri dátach treba dohodnúť:

- **Časové pásmo:** `observed_at` je bez časového pásma a komentár uvádza, že pásmo nie je potvrdené. Pred prevodmi na UTC a dennými súčtami potvrdiť význam časov aj prechod letného času.
- **Duplicity:** podľa komentára sú ponechané. Bez pravidla ich nesmieme automaticky odstrániť ani prezentovať súčet ako očistenú spotrebu.
- **Jednotky:** `energy_kwh` už obsahuje energiu za 15 minút; znovu ju nenásobiť 250. Ročná očakávaná spotreba je podľa názvu stĺpca v MWh.
- **Väzby:** zákazník môže mať viac odberných miest a meradiel. `registry_meter_id` a `measurement_meter_id` sú odlišné identifikátory; merania filtrovať podľa druhého. Chýbajúce mapovanie neznamená nulovú spotrebu.
- **História:** prepojenie na zákazníka je snímka registra, nie história vlastníctva. Podľa toho označiť historické výsledky.
- **Pokrytie:** pre dáta od októbra 2026 treba preveriť ďalšie partície; vo výpise nie sú. Chýbajúce merania odlíšiť od skutočnej nuly.
- **Druh meradla:** overiť hodnoty `kind` pred rozdelením dát na spotrebu a výrobu.

## 3. Navrhovaná kostra projektu

Pripraviť ju až pri začatí implementácie:

```text
energy-sharing-api/
  app/
    main.py                  # aplikácia, routre, CORS
    config.py                # konfigurácia z prostredia
    db.py                    # pripojenia a connection pool
    routers/
      health.py
      customers.py
      measurements.py
    schemas/                 # validácia vstupov a odpovedí
    services/                # pravidlá a kontrola prístupu
    repositories/            # parametrizované SQL a volania DB funkcií
  tests/
  pyproject.toml             # závislosti a nastavenie projektu
  .env.example              # iba názvy premenných a ukážkové hodnoty
  README.md                 # postup lokálneho spustenia
```

Základ bude FastAPI, server Uvicorn, validácia cez Pydantic a PostgreSQL ovládač s poolom pripojení. Konkrétne verzie vybrať a uzamknúť pri implementácii. Existujúce SQL funkcie umožňujú začať bez zavádzania ORM.

Konfigurácia: `DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV`, `LOG_LEVEL`. Skutočné heslá držať mimo Gitu. API má používať vlastného DB používateľa s minimálnymi právami, nie účet `postgres`. Pre prvú etapu stačí čítanie potrebných dát a vykonanie uvedených funkcií.

## 4. Prvé API rozhranie

Prefix: `/api/v1`. Zákaznícke endpointy sprístupniť až s overením identity a oprávnenia ku konkrétnemu zákazníkovi.

| Metóda a cesta | Účel | Zdroj |
| --- | --- | --- |
| `GET /health` | Stav procesu bez citlivých údajov | API |
| `GET /ready` | Dostupnosť DB; pri výpadku HTTP 503 | Jednoduchý DB dotaz |
| `GET /api/v1/customers/{customer_id}` | Základné údaje oprávneného zákazníka | Dotaz do `customers`, po overení DDL |
| `GET /api/v1/customers/{customer_id}/connections` | Odberné miesta | `energy_app.get_customer_connections` |
| `GET /api/v1/customers/{customer_id}/meters` | Meradlá a mapovanie | `energy_app.get_customer_meters` |
| `GET /api/v1/customers/{customer_id}/meters/{meter_id}/measurements?from=...&to=...` | Časový rad jedného meradla | `energy.measurements` po kontrole väzby na zákazníka |

Funkciu `get_customer_by_number` možno použiť interne na dohľadanie zákazníka po overení identity. Samotné zákaznícke číslo nie je heslo ani dôkaz identity; verejný endpoint na vyhľadávanie zákazníkov podľa čísla zatiaľ nezavádzať. Spôsob prihlásenia cez ZSE/VSE treba dohodnúť osobitne, pretože SQL autentifikáciu nerieši.

Pravidlá rozhrania:

- Všetky SQL parametre odovzdávať cez ovládač, nikdy skladať SQL z používateľského vstupu.
- Pri meraniach vyžadovať `from < to`, používať interval `[from, to)` a na začiatok limitovať jeden dotaz na 31 dní. Tak sa využije aj delenie dát podľa času.
- `meter_id` v ceste meraní znamená `measurement_meter_id`. Kontrolovať celú väzbu zákazník → odberné miesto → registrové meradlo → meracie meradlo.
- Presné `numeric` hodnoty vracať ako desatinné reťazce; dohodnúť to s frontendom. Chýbajúce hodnoty ponechať ako `null` alebo prázdny zoznam podľa kontraktu.
- Neexistujúci zákazník: 404; existujúci zákazník bez odberných miest: zoznam `[]`. Správanie SQL `NULL` a JSON `null` zjednotiť v API.
- Neprihlásený prístup: 401; prístup k cudzím dátam zamietnuť podľa dohodnutej politiky. Chybné parametre: 422; nedostupná DB: 503 bez SQL, hesiel a interných detailov v odpovedi.
- CORS povoliť pre konkrétny pôvod frontendu. Pri lokálnom vývoji môže frontend používať port 8000 a API port 8001.

## 5. Poradie realizácie

1. Overiť kompletnú DB štruktúru, dostupnosť dát a otvorené dátové otázky z bodu 2.
2. Založiť Python projekt v `energy-sharing-api`, konfiguráciu a základ aplikácie.
3. Pridať pool pripojení, `/health` a `/ready`; overiť aj správanie pri výpadku DB.
4. Dohodnúť a pripraviť overenie identity a autorizáciu. Pre izolované lokálne demo prípadne použiť explicitnú testovaciu identitu.
5. Obaliť existujúce funkcie pre odberné miesta a meradlá, doplniť dátové modely a jednotné chyby.
6. Pridať čítanie meraní s časovým filtrom a kontrolou vlastníctva. Agregácie doplniť až po rozhodnutí o duplicitách a časovom pásme.
7. Overiť funkčný priechod na testovacej DB: zákazník → odberné miesta → mapované meradlo → merania. Pokryť aj cudzie meradlo, chýbajúce mapovanie, prázdne dáta a neplatný interval.
8. Až potom v samostatnom kroku napojiť frontend a postupne nahrádzať demo dáta.

## 6. Hranice prvej etapy

Prvý výsledok má byť spustiteľné API, ktoré bezpečne načíta existujúce zákaznícke údaje a merania. Zápisy, registrácia, skupiny zdieľania, výpočty úspor, vyúčtovanie a odmeny potrebujú samostatný návrh: dodaný SQL súbor ich dátový model neobsahuje.

Pred odovzdaním overiť lokálne spustenie podľa README, API dokumentáciu, funkčnosť proti testovacej DB, odmietnutie cudzieho zákazníka/meradla a to, že v repozitári nie sú prihlasovacie údaje.
