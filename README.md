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
| `POST /api/v1/checks` | sprawdzenie z każdego kanału: `CheckRequest` (tekst do 4000 znaków, adres http(s) albo `audio_id`), nagłówek `X-Meritum-Session` z losowym identyfikatorem sesji; maskuje telefony, e-maile i PESEL przed `JobQueue`, zleca workflow `check`, zwraca 202 i `check_id`; zły wpis daje 422 z kluczem z `copy/pl.json` (`errors.empty`, `errors.too_long`, `errors.invalid_url`) |
| `GET /api/v1/checks/{check_id}` | `AnalysisStatus`: kroki i, po zakończeniu, `result` (`CheckResult` z `ai_disclosure: true` i nagłówkiem `AI-Disclosure: mode=ai-originated`) |
| `POST /api/v1/discord/interactions` | kanał Discord: interakcje HTTP podpisane kluczem Ed25519 aplikacji (401 przy złym podpisie, 404 gdy środowisko nie ma aplikacji Discord) |
| `GET /api/v1/auth/login/{google,microsoft}` | logowanie OIDC: przekierowanie do dostawcy (404, gdy dostawca nie jest skonfigurowany) |
| `GET /api/v1/auth/callback/{google,microsoft}` | powrót od dostawcy: sprawdza `state` i token ID, zakłada sesję, przekierowuje na `/` (400 przy złym `state` albo tokenie) |
| `GET /api/v1/auth/me` | zalogowane konto: dostawca, identyfikator konta, e-mail i `csrf_token` (401 bez sesji) |
| `POST /api/v1/auth/logout` | wylogowanie z nagłówkiem `X-CSRF-Token`; ciasteczko sesji zostaje unieważnione (204) |
| `GET /api/docs` | Swagger UI, schemat w `/api/v1/openapi.json` |

## Kanał Discord

Discord to kanał wejściowy jak formularz i wtyczka: interakcje HTTP (bez bota z trwałym połączeniem) trafiają do `POST /api/v1/discord/interactions`. Komendy:

- `/sprawdz tekst:<tekst albo link>`,
- „Sprawdź w Meritum” w menu Aplikacje przy dowolnej wiadomości.

Aplikację da się dodać do serwera albo do własnego konta, a odpowiedź widzi tylko pytający. W bootstrapie odpowiedź mówi, że rdzeń weryfikacji jest w budowie; tekst przechodzi walidację `CheckRequest` z kanałem `discord`.

Każde środowisko ma własną aplikację Discord. Jej klucz publiczny jest w zmiennych repo `DISCORD_PUBLIC_KEY_DEV` i `DISCORD_PUBLIC_KEY_PRD` (deploy przekazuje go jako `MERITUM_DISCORD_PUBLIC_KEY`, patrz „Sekrety w kontenerze”), a w ustawieniach aplikacji jako Interactions Endpoint URL wpisany jest `https://meritum-dev.gburek.app/api/v1/discord/interactions` albo `https://meritum.gburek.app/...`. Komendy rejestruje:

```bash
DISCORD_APPLICATION_ID=... DISCORD_BOT_TOKEN=... uv run python scripts/register_discord_commands.py
```

Endpoint nie ma limitu po IP (wszystkie żądania przychodzą z serwerów Discorda); limit per użytkownik Discorda dojdzie razem ze sprawdzaniem.

## Logowanie (OIDC)

Personel panelu i obywatel logują się kontem Google albo Microsoft. Backend prowadzi przepływ authorization code z PKCE przez Authlib (`starlette_client`) i sprawdza token ID: podpis kluczem z JWKS dostawcy, wystawcę, odbiorcę (nasz identyfikator klienta), czas ważności i `nonce`. Samo logowanie nie nadaje roli; rolę personelu nadaje administrator według listy adresów (#12). Microsoft nie weryfikuje adresu w claimie `email` (przy dzierżawie `common` użytkownik może go ustawić sam), dlatego `/me` zwraca `email_verified`, a lista personelu powinna uznawać tylko adresy z `email_verified: true`.

Sesja to podpisane ciasteczko `meritum_session` z flagami `HttpOnly`, `Secure` i `SameSite=Lax`. Żyje 8 godzin od zalogowania, bez przedłużania przy kolejnych żądaniach (`SESSION_MAX_AGE` w `src/meritum_backend/auth/constants.py`). Ciasteczko przechowuje tylko dostawcę, identyfikator konta i e-mail; wylogowanie usuwa je z przeglądarki, ale skopiowana wartość działa do końca swojego czasu życia (sesja nie ma rejestru po stronie serwera). Żądanie zmieniające stan przy takiej sesji musi powtórzyć `csrf_token` z `GET /api/v1/auth/me` w nagłówku `X-CSRF-Token` (zależność `CsrfUser` w `auth/api.py`), inaczej dostaje 403.

| Zmienna | Opis |
| --- | --- |
| `MERITUM_SESSION_SECRET` | klucz podpisujący ciasteczko; bez niego proces losuje własny, więc restart kończy sesje |
| `MERITUM_GOOGLE_CLIENT_ID`, `MERITUM_GOOGLE_CLIENT_SECRET` | klient OAuth w Google Cloud; bez obu Google jest wyłączony |
| `MERITUM_MICROSOFT_CLIENT_ID`, `MERITUM_MICROSOFT_CLIENT_SECRET` | aplikacja w Microsoft Entra; bez obu Microsoft jest wyłączony |
| `MERITUM_MICROSOFT_TENANT` | dzierżawa Entra, domyślnie `common` (konta firmowe i prywatne) |
| `MERITUM_PUBLIC_URL` | publiczny adres API, podstawa adresów powrotu; domyślnie według `MERITUM_ENV` |

Adresy powrotu do wpisania u dostawców:

| Środowisko | Google | Microsoft |
| --- | --- | --- |
| local | `http://localhost:8000/api/v1/auth/callback/google` | `http://localhost:8000/api/v1/auth/callback/microsoft` |
| dev | `https://meritum-dev.gburek.app/api/v1/auth/callback/google` | `https://meritum-dev.gburek.app/api/v1/auth/callback/microsoft` |
| prd | `https://meritum.gburek.app/api/v1/auth/callback/google` | `https://meritum.gburek.app/api/v1/auth/callback/microsoft` |

Testy i scenariusze behave (`features/moderation.feature`) używają fałszywego dostawcy (`FakeLogin`) i tokenów podpisanych lokalnym kluczem, bez sieci. Logowanie prawdziwym kontem Google i Microsoft sprawdza się ręcznie na dev, poza CI.

Rejestr podmiotów przetwarzających (ADR-14, design-system#9): Google LLC i Microsoft Corporation przetwarzają dane logowania (identyfikator konta, adres e-mail, imię i nazwisko z profilu) jako dostawcy tożsamości, także poza UE. Meritum zapisuje z nich tylko identyfikator konta i e-mail, w ciasteczku sesji.

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

Przejście API → worker: `docker compose up -d --wait db`, w repo workera `uv run meritum-worker` (zakłada tabele DBOS w `worker_local`), potem `uv run pytest -m integration tests/checks`.

Zasady architektury i to, co je sprawdza: [docs/architecture.md](docs/architecture.md).

meritum-core jest przypięty do commita (`rev` w `pyproject.toml`). PR-y z podbiciem otwiera automatycznie workflow w meritum-core; ręcznie: zmień `rev` i uruchom `uv lock --upgrade-package meritum-core`.

## CI/CD

`.github/workflows/ci.yml`, jedno uruchomienie na commit:

- `lint` i `tests` idą równolegle na runnerach GCP (`self-hosted, meritum`).
- `deploy` rusza tylko na `develop` (dev) i `main` (prd), po zielonym `lint` i `tests`, na runnerze `dellpromaxgb10`. `deploy/deploy.sh` buduje obraz na hoście (ARM64), podmienia kontener, czeka na `/api/v1/health` i, jeśli worker tego środowiska działa, puszcza `ping` przez kolejkę DBOS.

### Sekrety w kontenerze

Job `deploy` podaje skryptowi wszystkie sekrety i zmienne repozytorium (`toJSON(secrets)`, `toJSON(vars)`). Jedyna lista tych, które trafiają do kontenera API, jest w `deploy/container_env.sh`: dla gałęzi `develop` skrypt bierze wariant `_DEV`, dla `main` wariant `_PRD`, i podaje go do `docker run` jako `-e NAZWA`, bez wartości w linii poleceń i bez zapisu na dysk. Brak sekretu nie zatrzymuje deployu; wykrywa go test gotowości (#19). Jeśli plik env środowiska ma `MERITUM_FILES_VOLUME` i `MERITUM_FILES_DIR` (wpisuje je platforma, ADR-31), `docker run` montuje ten wolumen plików pod tym katalogiem (`-v "$MERITUM_FILES_VOLUME:$MERITUM_FILES_DIR"`). Każdy wpis z `MERITUM_GCP_MOUNTS` (lista rozdzielona spacjami, wpisy `host:kontener:ro`, infra#28) trafia do `docker run` jako `-v "<wpis>"`, dzięki czemu `GOOGLE_APPLICATION_CREDENTIALS` wskazuje w kontenerze na istniejący plik poświadczeń Workload Identity Federation. Bez tej zmiennej deploy działa dalej i zgłasza ostrzeżenie.

| Zmienna w kontenerze | Sekret lub zmienna repo | Zgłoszenie |
|---|---|---|
| `MERITUM_DISCORD_PUBLIC_KEY` | `DISCORD_PUBLIC_KEY_{DEV,PRD}` (zmienna) | kanał Discord |
| `MERITUM_CHANNEL_HASH_SALT` | `MERITUM_CHANNEL_HASH_SALT_{DEV,PRD}` (sekret) | #24 |
| `MERITUM_SESSION_SECRET` | `MERITUM_SESSION_SECRET_{DEV,PRD}` (sekret) | #15 |
| `MERITUM_GOOGLE_CLIENT_ID` | `GOOGLE_CLIENT_ID_{DEV,PRD}` (zmienna) | #15 |
| `MERITUM_GOOGLE_CLIENT_SECRET` | `GOOGLE_CLIENT_SECRET_{DEV,PRD}` (sekret) | #15 |
| `MERITUM_MICROSOFT_CLIENT_ID` | `MICROSOFT_CLIENT_ID_{DEV,PRD}` (zmienna) | #15 |
| `MERITUM_MICROSOFT_CLIENT_SECRET` | `MICROSOFT_CLIENT_SECRET_{DEV,PRD}` (sekret) | #15 |

Nowy sekret: dopisz wiersz do listy w `deploy/container_env.sh` i do tej tabeli, potem dodaj sekret w ustawieniach repozytorium.

Baza, rola, schemat i plik `~/meritum/envs/api-<env>.env` na hoście pochodzą z platformy w [meritum-infra](https://github.com/Meritum-HackNation2026/meritum-infra) (`onprem/dellpromaxgb10/platform/`). Dostęp do core daje klucz tylko do odczytu w sekrecie repozytorium `MERITUM_CORE_SSH_KEY`.

Gałęzie: zmiany przez PR do `develop`, wydanie przez PR `develop` → `main`. Nie pushuj bezpośrednio do `develop` ani `main`. Na planie Free GitHub nie wymusza tego w repozytoriach prywatnych, więc to zasada zespołu. Gałąź funkcji usuń po merge'u (`gh pr merge --delete-branch` albo przycisk w PR). Automatyczne usuwanie jest wyłączone, bo bez ochrony gałęzi skasowałoby też `develop` po PR `develop` → `main`.
