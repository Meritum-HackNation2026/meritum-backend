# meritum-backend

API Meritum w FastAPI. Zleca długie operacje workerom ([meritum-worker](https://github.com/Meritum-HackNation2026/meritum-worker)) przez DBOS, a kontrakty bierze z [meritum-core](https://github.com/Meritum-HackNation2026/meritum-core). Frontend to osobne repo ([meritum-frontend](https://github.com/Meritum-HackNation2026/meritum-frontend)): jego nginx przekazuje `/api` do tego API, więc oba działają pod jednym adresem.

| Środowisko | Gałąź | Adres | Kontener | Schemat w bazie |
| --- | --- | --- | --- | --- |
| dev | `develop` | https://meritum-dev.gburek.app/api/v1/health | `meritum-api-dev` | `api_dev` (rola `meritum_api_dev`) |
| prd | `main` | https://meritum.gburek.app/api/v1/health | `meritum-api-prd` | `api_prd` (rola `meritum_api_prd`) |

## Endpointy

| Metoda i ścieżka | Opis |
| --- | --- |
| `GET /api/v1/health` | gotowość: 200, gdy rola API wykona zapytanie w bazie, inaczej 503 |
| `GET /api/v1/health/live` | żywotność procesu, bez bazy (healthcheck Dockera) |
| `POST /api/v1/jobs/ping` | zleca workflow `ping` (test dymny po deployu), zwraca `workflow_id` |
| `GET /api/v1/jobs/{workflow_id}` | stan zadania: `status`, `output`, `error` |
| `POST /api/v1/discord/interactions` | kanał Discord: interakcje HTTP podpisane kluczem Ed25519 aplikacji (401 przy złym podpisie, 404 gdy środowisko nie ma aplikacji Discord) |
| `GET /api/docs` | Swagger UI, schemat w `/api/v1/openapi.json` |

## Kanał Discord

Discord to kanał wejściowy jak formularz i wtyczka: interakcje HTTP (bez bota z trwałym połączeniem) trafiają do `POST /api/v1/discord/interactions`. Komendy:

- `/sprawdz tekst:<tekst albo link>`,
- „Sprawdź w Meritum” w menu Aplikacje przy dowolnej wiadomości.

Aplikację da się dodać do serwera albo do własnego konta, a odpowiedź widzi tylko pytający. W bootstrapie odpowiedź mówi, że rdzeń weryfikacji jest w budowie; tekst przechodzi walidację `CheckRequest` z kanałem `discord`.

Każde środowisko ma własną aplikację Discord. Jej klucz publiczny jest w zmiennych repo `DISCORD_PUBLIC_KEY_DEV` i `DISCORD_PUBLIC_KEY_PRD` (deploy przekazuje go jako `MERITUM_DISCORD_PUBLIC_KEY`), a w ustawieniach aplikacji jako Interactions Endpoint URL wpisany jest `https://meritum-dev.gburek.app/api/v1/discord/interactions` albo `https://meritum.gburek.app/...`. Komendy rejestruje:

```bash
DISCORD_APPLICATION_ID=... DISCORD_BOT_TOKEN=... uv run python scripts/register_discord_commands.py
```

Endpoint nie ma limitu po IP (wszystkie żądania przychodzą z serwerów Discorda); limit per użytkownik Discorda dojdzie razem ze sprawdzaniem.

## Praca lokalna

Potrzebujesz `uv`, Dockera i klucza SSH z dostępem do organizacji (core jest prywatną zależnością git).

```bash
uv sync
docker compose up -d --wait db
uv run uvicorn --factory meritum_backend.main:create_app --reload   # http://localhost:8000
```

Ustawienia to zmienne `MERITUM_*` (`src/meritum_backend/settings.py`), domyślne pasują do `docker compose`. Worker lokalnie: w repo workera `uv run meritum-worker` (ta sama baza, schemat `worker_local`), potem `curl -X POST localhost:8000/api/v1/jobs/ping`.

Kontrole przed PR, te same co w CI:

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
uv run python scripts/check_conventions.py && uv run vulture && uv run bandit -c pyproject.toml -r src scripts
uv run pytest            # z testami architektury (tests/architecture/), bez testów integracyjnych
uv run behave            # scenariusze Gherkin z features/
```

Scenariusze ze zgłoszeń trafiają do `features/<domena>.feature`, kroki do `features/steps/` (wołają publiczne API, te same kontrole co `src/`). Testy na prawdziwym PostgreSQL albo u prawdziwego dostawcy oznacz `@pytest.mark.integration`: `uv run pytest` i CI je pomijają, lokalnie uruchamia je `uv run pytest -m integration`.

Zasady architektury i to, co je sprawdza: [docs/architecture.md](docs/architecture.md).

meritum-core jest przypięty do commita (`rev` w `pyproject.toml`). PR-y z podbiciem otwiera automatycznie workflow w meritum-core; ręcznie: zmień `rev` i uruchom `uv lock --upgrade-package meritum-core`.

## CI/CD

`.github/workflows/ci.yml`, jedno uruchomienie na commit:

- `lint` i `tests` idą równolegle na runnerach GCP (`self-hosted, meritum`).
- `deploy` rusza tylko na `develop` (dev) i `main` (prd), po zielonym `lint` i `tests`, na runnerze `dellpromaxgb10`. `deploy/deploy.sh` buduje obraz na hoście (ARM64), podmienia kontener, czeka na `/api/v1/health` i, jeśli worker tego środowiska działa, puszcza `ping` przez kolejkę DBOS.

Baza, rola, schemat i plik `~/meritum/envs/api-<env>.env` na hoście pochodzą z platformy w [meritum-infra](https://github.com/Meritum-HackNation2026/meritum-infra) (`onprem/dellpromaxgb10/platform/`). Dostęp do core daje klucz tylko do odczytu w sekrecie repozytorium `MERITUM_CORE_SSH_KEY`.

Gałęzie: zmiany przez PR do `develop`, wydanie przez PR `develop` → `main`. Nie pushuj bezpośrednio do `develop` ani `main`. Na planie Free GitHub nie wymusza tego w repozytoriach prywatnych, więc to zasada zespołu. Gałąź funkcji usuń po merge'u (`gh pr merge --delete-branch` albo przycisk w PR). Automatyczne usuwanie jest wyłączone, bo bez ochrony gałęzi skasowałoby też `develop` po PR `develop` → `main`.
