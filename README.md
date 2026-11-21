# meritum-backend

API Meritum w FastAPI. Zleca długie operacje workerom ([meritum-worker](https://github.com/Meritum-HackNation2026/meritum-worker)) przez DBOS, a kontrakty bierze z [meritum-core](https://github.com/Meritum-HackNation2026/meritum-core). Frontend to osobne repo ([meritum-frontend](https://github.com/Meritum-HackNation2026/meritum-frontend)): jego nginx przekazuje `/api` do tego API, więc oba działają pod jednym adresem.

| Środowisko | Gałąź | Adres | Kontener | Schemat w bazie |
| --- | --- | --- | --- | --- |
| dev | `develop` | https://meritum-dev.gburek.app/api/v1/health | `meritum-api-dev` | `api_dev` (rola `meritum_api_dev`) |
| prd | `main` | https://meritum.gburek.app/api/v1/health | `meritum-api-prd` | `api_prd` (rola `meritum_api_prd`) |

## Endpointy

| Metoda i ścieżka | Opis |
| --- | --- |
| `GET /api/v1/health` | gotowość (patrz „Test gotowości”): 200, gdy niczego nie brakuje, inaczej 503 z nazwami brakujących zmiennych i niedostępnych dostawców (bez wartości) |
| `GET /api/v1/health/live` | żywotność procesu, bez bazy (healthcheck Dockera) |
| `POST /api/v1/jobs/ping` | zleca workflow `ping` (test dymny po deployu), zwraca `workflow_id` |
| `GET /api/v1/jobs/{workflow_id}` | stan zadania: `status`, `output`, `error` |
| `POST /api/v1/checks` | sprawdzenie z każdego kanału: `CheckRequest` (tekst do 4000 znaków, adres http(s) albo `audio_id`), nagłówek `X-Meritum-Session` z losowym identyfikatorem sesji; maskuje dane osobowe w tekście i w parametrach query linku przed `JobQueue` (bramka PII z `MERITUM_PII_*`, domyślnie pusta, potem wzorce telefonów, e-maili i PESEL) (ścieżka linku zostaje, żeby worker pobrał tę samą stronę; fragment jest usuwany, a link z użytkownikiem lub hasłem dostaje 422), zleca workflow `check`, zwraca 202 i `check_id`; zły wpis daje 422 z kluczem z `copy/pl.json` (`errors.empty`, `errors.too_long`, `errors.invalid_url`); kanały `discord`, `sms` i `mcp` dostają 400 do czasu backend#27 (SMS przychodzi przez `POST /api/v1/sms/webhook`); ponad limit dostaje 429 z `Retry-After` (patrz „Limity zapytań”); przy niegotowej usłudze (niedostępna baza API, brak zmiennych API albo braki zgłoszone przez workera) 503 `{"status": "technical_failure", "code": "not_ready", "message_key": "status_hint.technical_failure"}` |
| `POST /api/v1/audio` | nagranie z formularza jako treść żądania (OGG Opus, MP3, M4A albo WAV; format odczytany z bajtów, nie z `Content-Type`); zapisuje plik w `BlobStore` z retencją zapisu sprawdzenia (30 dni) i zwraca 201 z `audio_id` do `POST /api/v1/checks`; odmowa ma `status: out_of_scope`, klucz z `copy/pl.json` oraz `formats`, `max_mb` i `max_minutes` do wstawienia w tekst: 413 `errors.audio_too_large` (ponad 20 MiB), 422 `errors.audio_too_long` (ponad 10 min), 415 `status_hint.out_of_scope_audio_format`; 10 wysyłek na minutę i 30 na dobę z jednego adresu |
| `GET /api/v1/checks/{check_id}` | `AnalysisStatus`: kroki i, po zakończeniu, `result` (`CheckResult` z `ai_disclosure: true` i nagłówkiem `AI-Disclosure: mode=ai-originated`) |
| `GET /api/v1/checks/{check_id}/events` | postęp sprawdzenia jako Server-Sent Events: każda wartość strumienia `progress` workflowu (`JobQueue.stream`) to jedno zdarzenie `AnalysisStatus`; `result` pojawia się dopiero po kroku `verify_citations` (`done` albo `skipped`), więc wersja wstępna nie niesie werdyktu; po zakończeniu ostatnie zdarzenie ma pełny `CheckResult` i strumień się zamyka; rozłączenie nie przerywa workflowu, a ponowne połączenie odtwarza kroki od początku (404 dla nieznanego id) |
| `DELETE /api/v1/sessions/{session_id}/checks` | „Usuń moje sprawdzenia” sesji przeglądarki: od razu usuwa zapisy sprawdzeń, powiadomienia i powiązania ze sprawami moderatora, zleca workflow `delete_subject` (dane DBOS i pliki usuwa worker), zwraca 202 i `deleted`; nagłówek `X-Meritum-Session`, jeśli jest, musi wskazywać tę samą sesję (inaczej 403); identyfikator w postaci skrótu kanału albo za krótki daje 400; limit 10 żądań na minutę z jednego adresu (429) |
| `POST /api/v1/checks/{check_id}/claims/{n}/escalate` | „Przekaż moderatorom”: zleca workflow `escalate_claim` (powód `recommended_clicked`) i czeka na zapis sprawy; 200 z `Escalation` `created` albo `updated` z numerem i kluczem `escalation.created`/`escalation.updated`; gdy sprawy nie zapisano, 503 z `Escalation` `recommended` bez numeru i kluczem `escalation.recommended`; 404 dla nieukończonego sprawdzenia albo nieznanego twierdzenia |
| `POST /api/v1/checks/{check_id}/claims/{n}/dispute` | „Zgłoś błąd”: opcjonalnie `{"justification": "..."}` (maskowane jak pytanie; do 4000 znaków, dłuższe daje 422 `errors.too_long`; po zamaskowaniu przycinane do 1000 przed znacznikiem), powód `user_dispute`, odpowiedzi jak wyżej z kluczem `result.report_error_done`; uzasadnienie jest opcjonalne (brak treści albo same spacje wysyła spór bez niego); wynik sprawdzenia się nie zmienia |
| `POST /api/v1/discord/interactions` | kanał Discord: interakcje HTTP podpisane kluczem Ed25519 aplikacji (401 przy złym podpisie, 404 gdy środowisko nie ma aplikacji Discord) |
| `POST /api/v1/sms/webhook` | kanał SMS: zdarzenie `sms:received` bramki sms-gate.app podpisane HMAC (401 przy złym podpisie albo znaczniku czasu spoza ±5 min, 404 gdy środowisko nie ma bramki); zawsze szybkie 202, sprawdzenie idzie do kolejki jobów (patrz „Kanał SMS”) |
| `GET /api/v1/auth/login/{google,microsoft}` | logowanie OIDC: przekierowanie do dostawcy (404, gdy dostawca nie jest skonfigurowany) |
| `GET /api/v1/auth/callback/{google,microsoft}` | powrót od dostawcy: sprawdza `state` i token ID, zakłada sesję, przekierowuje na `/` (400 przy złym `state` albo tokenie) |
| `GET /api/v1/auth/me` | zalogowane konto: dostawca, identyfikator konta, e-mail i `csrf_token` (401 bez sesji) |
| `POST /api/v1/auth/logout` | wylogowanie z nagłówkiem `X-CSRF-Token`; ciasteczko sesji zostaje unieważnione (204) |
| `GET /api/docs` | Swagger UI, schemat w `/api/v1/openapi.json` |

## Nagrania (magazyn plików)

`POST /api/v1/audio` zapisuje nagrania przez `BlobStore` z meritum-core (ADR-31), a worker czyta je stamtąd do transkrypcji. Adapter wybiera `build_blobs` w `src/meritum_backend/checks/factory.py`:

| Zmienna | Adapter |
| --- | --- |
| `MERITUM_FILES_DIR` | system plików w tym katalogu; to wolumen plików wspólny z workerem, który platforma wpisuje do pliku env i deploy montuje (patrz „Sekrety w kontenerze”) |
| `MERITUM_BLOB_PROVIDER` (`gcs` z `MERITUM_BLOB_BUCKET`) | prywatny bucket Cloud Storage, gdy nie ma wolumenu |
| żadna | przy `MERITUM_ENV=local` pamięć procesu (wystarcza testom i samemu API, worker nie zobaczy pliku); w innym środowisku API nie startuje |

Plik ma `expires_at` 30 dni od wysłania. Bucket GCS usuwa go regułą cyklu życia (infra#8). Na wolumenie adapter systemu plików niczego sam nie usuwa: plik sprawdzenia kasuje workflow retencji razem z zapisem sprawdzenia i przy „Usuń moje sprawdzenia” (backend/009, worker/013, worker#24). Nagranie, które nie trafiło do żadnego sprawdzenia, zostaje na wolumenie, dopóki worker#24 nie zacznie czyścić plików po `expires_at`.

## Test gotowości

`GET /api/v1/health` łączy dwa raporty i wymienia tylko nazwy, nigdy wartości sekretów:

- własny raport API: baza (`SELECT 1` rolą API), `MERITUM_CHANNEL_HASH_SALT`, magazyn plików (ta sama fabryka `build_blobs` co przy starcie: wolumen `MERITUM_FILES_DIR` albo `MERITUM_BLOB_PROVIDER` z `MERITUM_BLOB_DIRECTORY` lub `MERITUM_BLOB_BUCKET`) i `MERITUM_DISCORD_BOT_TOKEN`, gdy kanał Discord jest włączony (`MERITUM_DISCORD_PUBLIC_KEY`);
- raport workera: przy pierwszym sprawdzeniu API zleca workflow `readiness` i czyta jego zdarzenie `readiness` (`ReadinessReport` z core: brakujące zmienne i niedostępni dostawcy workera). Dopóki worker go nie opublikuje, odpowiedź ma `"worker": "not_reported"` i kod 503.

Ten sam raport trafia do logu startu (`not ready: ...` jako ostrzeżenie), gdy worker odpowie albo po 60 s. `POST /api/v1/checks` przy niegotowej usłudze odpowiada 503 ze stanem `technical_failure` i kodem `not_ready`, bez nazw kluczy; raport dla sprawdzeń jest odświeżany co 30 s. Sam brak (albo wygaśnięcie) raportu workera nie blokuje sprawdzeń: `/health` pokazuje `"worker": "not_reported"`, a API loguje ostrzeżenie. Przełącznik to stała `BLOCK_CHECKS_WITHOUT_WORKER_REPORT` w `src/meritum_backend/health/constants.py` (dziś `False`); po wejściu worker#28 ustaw ją na `True`, żeby sprawdzenia bez raportu workera dostawały `not_ready`. Deploy czeka na `/api/v1/health/live`, a niegotową usługę zgłasza ostrzeżeniem z treścią raportu, bez przerywania; przerywa go tylko niedostępna baza API. Raport workera starszy niż 60 s API odświeża nowym workflowem `readiness`, więc po restarcie workera z poprawionymi kluczami `/health` i sprawdzenia wracają bez restartu API. Jeśli worker nie odpowie na zlecony workflow przez 60 s, API zleca go ponownie, a ostatni raport przestaje się liczyć (`"worker": "not_reported"`); przy wyłączonym workerze i odpytywanym `/health` w kolejce przybywa więc jeden workflow `readiness` na minutę. Gdy start przerywa źle skonfigurowany magazyn plików, log przed wyjściem wymienia brakujące zmienne API (`not ready, cannot start: ...`). Klient DBOS w API nie ponawia połączeń (`retry_connection_errors=False`): przy chwilowej awarii bazy każde zlecenie (`check`, `ping`) od razu dostaje 503, zamiast czekać.

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

## Kanał SMS

Bramką jest telefon z Androidem (polska karta prepaid) z aplikacją SMS Gateway for Android w trybie Cloud ([sms-gate.app](https://docs.sms-gate.app/)). W tym trybie treść SMS-ów przechodzi przez serwery sms-gate.app. Usługa jest bezpłatna; operator nadawcy może pobrać standardową opłatę za SMS według jego taryfy.

- Odbiór: bramka wysyła `POST /api/v1/sms/webhook` z nagłówkami `X-Signature` (hex `HMAC_SHA256(klucz, surowe body + X-Timestamp)`) i `X-Timestamp`. Zły podpis albo znacznik czasu starszy lub nowszy niż 5 minut daje 401. Bramka ponawia zdarzenie do ok. 2 dni, dopóki nie dostanie 2xx, więc identyfikator workflowu to `sms-<deviceId>-<id>`: powtórzone zdarzenie nie startuje drugiego sprawdzenia.
- Numer nadawcy od razu zamienia się w skrót z solą (`MERITUM_CHANNEL_HASH_SALT`, ta sama funkcja co w backend#24), który jest `session_id` i `channel_user_hash`. Surowy numer zostaje tylko w pamięci zadania, które po zakończeniu sprawdzenia wysyła odpowiedź; restart procesu gubi odpowiedź, ale numer nigdzie nie trafia.
- Odpowiedź to werdykt głównego twierdzenia, bez linku (operatorzy filtrują linki), najwyżej 70 znaków UCS-2 na SMS. Pierwszy SMS do numeru bez wcześniejszych sprawdzeń poprzedza informacja, że odpowiada system AI. `MERITUM_SMS_GSM7=true` zamienia polskie litery na litery bez ogonków i pozwala na 160 znaków. Sprawdzenie, które nie skończy się w 10 minut, dostaje tekst o niepowodzeniu.
- SMS o treści `USUN` usuwa zapisy sprawdzeń dla skrótu tego numeru (`delete_subject`, backend#20).
- SMS bramki do samej siebie (numer `MERITUM_SMS_GATEWAY_NUMBER`) dostaje 202 bez sprawdzenia i bez odpowiedzi, żeby nie zapętlić odpowiedzi.

Webhook `sms:received` jest zarejestrowany tylko dla dev; dev i prd korzystają z tego samego telefonu, więc prd dostanie własny webhook dopiero po decyzji zespołu (każdy SMS trafiłby wtedy do obu środowisk i oba by odpowiedziały). Rejestracja (stały `id` nadpisuje webhook zamiast tworzyć drugi; webhooków `web-dashboard-*` nie usuwaj):

```bash
curl -X POST -u "$SMS_GATEWAY_USERNAME:$SMS_GATEWAY_PASSWORD" -H "Content-Type: application/json" \
  -d '{"id":"meritum-dev-sms-received","url":"https://meritum-dev.gburek.app/api/v1/sms/webhook","event":"sms:received"}' \
  https://api.sms-gate.app/3rdparty/v1/webhooks
```

Próba na żywo (ręcznie, poza CI): wyślij przez bramkę SMS na jej własny numer i sprawdź w logach `meritum-api-dev` wpis `POST /api/v1/sms/webhook ... 202`.

## Usuwanie danych

Obywatel usuwa swoje sprawdzenia w każdym kanale (US-BEZ-05, F-20). Przeglądarka i wtyczka wołają `DELETE /api/v1/sessions/{session_id}/checks`; losowy identyfikator sesji zna tylko jej właściciel, więc nie jest potrzebne logowanie. Nagłówek `X-Meritum-Session` jest opcjonalny: gdy wskazuje inną sesję, odpowiedź to 403, ale to chroni przed pomyłką klienta, a nie przed kimś, kto zna cudzy identyfikator. Każde żądanie zleca workflow, więc endpoint ma limit 10 na minutę z jednego adresu. Discord, SMS i MCP nie mają sesji przeglądarki i wołają `delete_subject(kind, value, eraser, jobs)` z pakietu `meritum_backend.privacy` ze skrótem z solą (`channel_user_hash`), a zalogowane konto z `user_id`. Surowego identyfikatora kanału funkcja nie przyjmie.

Funkcja najpierw zleca workflow `delete_subject` (worker usuwa dane workflowów w tabelach DBOS i pliki w `BlobStore`, a tabele aplikacji czyści drugi raz), potem w jednej transakcji usuwa zapisy, powiadomienia i powiązania ze sprawami moderatora (`SubjectEraser` z core). Sprawa moderatora zostaje dla innych pytających.

Identyfikator sesji w tej ścieżce działa jak klucz, więc log dostępu uvicorn pokazuje zamiast niego `{session_id}` (`DELETE /api/v1/sessions/{session_id}/checks`); filtr instaluje `create_app`.

Repozytoria aplikacji buduje core (`build_app_repositories`) ze zmiennych `MERITUM_DATABASE_PROVIDER` (`memory` domyślnie, `postgres`) i `MERITUM_DATABASE_URL`. Przy `postgres` adres musi mieć `search_path` schematu aplikacji (`app_dev`, `app_prd`).

Test na prawdziwej bazie, lokalnie:

```bash
docker run -d --rm --name app-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=meritum -p 55433:5432 postgres:18
export MERITUM_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55433/meritum
uv run dbos migrate -s "$MERITUM_TEST_DATABASE_URL" --schema worker_local   # tabele DBOS bez workera
uv run pytest -m integration tests/privacy
```

Drugi test zleca workflow `check` dla świeżej sesji i sprawdza, że trafił do tabel DBOS. To, że po usunięciu żaden wiersz DBOS nie zawiera sesji, sprawdza tylko z działającym workerem (worker#24) na tej samej bazie i z `MERITUM_TEST_WORKER=1`; bez tego kończy się pominięciem.

## Limity zapytań

`POST /api/v1/checks` liczy każde poprawne sprawdzenie (po walidacji i maskowaniu, także te, które potem dostaną 429) na adres IP klienta, kraj (nagłówek `CF-IPCountry` od Cloudflare, bez niego `XX`) i kanał, w oknach jednominutowych. Liczniki są wspólne dla wszystkich instancji API (ADR-18): tabela `rate_limit_hits` w schemacie API, zakładana przy pierwszym użyciu. Klucze to HMAC-SHA-256 z sekretem `MERITUM_CHANNEL_HASH_SALT` (ten sam co skrót identyfikatora kanału, #24), więc bez sekretu nie da się ich odwrócić, sprawdzając wszystkie adresy IPv4. Bez sekretu (lokalnie, w testach) proces losuje własny klucz i zapisuje ostrzeżenie; instancje liczą wtedy osobno. Co 15 sekund, a także przy każdym sprawdzeniu, API usuwa wiersze zakończonych okien, więc klucz adresu znika najpóźniej 15 sekund po końcu swojego okna. Kod limitów nie zapisuje adresów IP w logach; logi dostępu uvicorna i bramy to osobna sprawa polityki prywatności.

Przed zleceniem workflowu API sprawdza też, ile sprawdzeń czeka w kolejce DBOS tego środowiska. Gdy osiągną próg, nowe dostają 429. Limit współbieżności kolejki zostaje w workerze.

Odpowiedź 429 nie zawiera werdyktu, tylko klucz komunikatu z `copy/pl.json`: `errors.rate_limited` z `Retry-After: 60` albo `errors.busy` z `Retry-After: 300`. Limity slowapi (`/jobs/ping`, `POST /api/v1/audio`) liczą nadal w pamięci procesu; ich 429 ma `message_key` `errors.rate_limited`, a po wyczerpaniu limitu dobowego (30 nagrań na dobę) `errors.rate_limited_daily`. Gdy baza liczników albo DBOS nie odpowiada, limit przepuszcza żądanie (fail-open, decyzja zespołu w #66; ostrzeżenie w logu bez adresu IP), a przed API zostają reguły Cloudflare.

| Zmienna | Domyślnie | Opis |
| --- | --- | --- |
| `MERITUM_CHECKS_PER_IP_PER_MINUTE` | 10 | sprawdzenia z jednego adresu IP na minutę |
| `MERITUM_CHECKS_PER_REGION_PER_MINUTE` | 3000 | sprawdzenia z jednego kraju na minutę; bezpiecznik na rozproszony zalew, bo prawie cały ruch idzie z `PL` |
| `MERITUM_CHECKS_PER_CHANNEL_PER_MINUTE` | 6000 | sprawdzenia z jednego kanału na minutę; bezpiecznik jak limit kraju |
| `MERITUM_EVENT_STREAMS_PER_IP_PER_MINUTE` | 60 | strumienie postępu (`GET /api/v1/checks/{id}/events`) otwarte z jednego adresu IP na minutę, z ponownymi połączeniami i z zapytaniami o nieznane id (to też ogranicza zgadywanie id); osobna pula, więc śledzenie sprawdzenia nie zużywa limitu nowych |
| `MERITUM_MAX_PENDING_CHECKS` | 100 | oczekujące sprawdzenia, od których API odpowiada 429 |

Domyślne wartości są w `src/meritum_backend/limits/constants.py`. Test licznika na prawdziwym PostgreSQL: `docker compose up -d --wait db`, potem `uv run pytest -m integration tests/limits`.

Discord, SMS i MCP nie mają sesji przeglądarki. Ich adapter wysyła `POST /api/v1/checks` z `channel_user_id` (identyfikator Discorda, numer telefonu albo identyfikator klienta MCP), a API od razu liczy HMAC-SHA-256 z `<kanał>:<identyfikator>` z solą `MERITUM_CHANNEL_HASH_SALT`, więc ten sam identyfikator w dwóch kanałach to dwie osoby (`meritum_backend.channels.channel_user_hash`). Skrót jest jednocześnie `session_id` i `channel_user_hash` wejścia workflowu; surowy identyfikator nie trafia do kolejki, bazy ani logów. Bez soli takie sprawdzenie dostaje 503, a bez `channel_user_id` 400. Kanały `web` i `extension` z `channel_user_id` dostają 422. Pusta sól liczy się jak brak soli. Ta sama sól jest kluczem liczników limitów, więc jej zmiana daje każdej osobie z Discorda, SMS i MCP nowy `session_id`, a starych zapisów nie da się już połączyć z jej skrótem.

## Logowanie (OIDC)

Personel panelu i obywatel logują się kontem Google albo Microsoft. Backend prowadzi przepływ authorization code z PKCE przez Authlib (`starlette_client`) i sprawdza token ID: podpis kluczem z JWKS dostawcy, wystawcę, odbiorcę (nasz identyfikator klienta), czas ważności i `nonce`. Samo logowanie nie nadaje roli; rolę personelu nadaje administrator według listy adresów (#22). Microsoft nie weryfikuje adresu w claimie `email` (przy dzierżawie `common` użytkownik może go ustawić sam), dlatego rolę dostaje tylko adres z `email_verified: true`.

Sesja to podpisane ciasteczko `meritum_session` z flagami `HttpOnly`, `Secure` i `SameSite=Lax`. Żyje 8 godzin od zalogowania, bez przedłużania przy kolejnych żądaniach (`SESSION_MAX_AGE` w `src/meritum_backend/auth/constants.py`). Ciasteczko przechowuje tylko dostawcę, identyfikator konta i e-mail; wylogowanie usuwa je z przeglądarki, ale skopiowana wartość działa do końca swojego czasu życia (sesja nie ma rejestru po stronie serwera). Żądanie zmieniające stan przy takiej sesji musi powtórzyć `csrf_token` z `GET /api/v1/auth/me` w nagłówku `X-CSRF-Token` (zależność `CsrfUser` w `auth/api.py`), inaczej dostaje 403.

| Zmienna | Opis |
| --- | --- |
| `MERITUM_SESSION_SECRET` | klucz podpisujący ciasteczko; bez niego proces losuje własny, więc restart kończy sesje |
| `MERITUM_GOOGLE_CLIENT_ID`, `MERITUM_GOOGLE_CLIENT_SECRET` | klient OAuth w Google Cloud; bez obu Google jest wyłączony |
| `MERITUM_MICROSOFT_CLIENT_ID`, `MERITUM_MICROSOFT_CLIENT_SECRET` | aplikacja w Microsoft Entra; bez obu Microsoft jest wyłączony |
| `MERITUM_MICROSOFT_TENANT` | dzierżawa Entra, domyślnie `common` (konta firmowe i prywatne) |
| `MERITUM_PUBLIC_URL` | publiczny adres API, podstawa adresów powrotu; domyślnie według `MERITUM_ENV` |
| `MERITUM_ADMIN_EMAILS` | adresy pierwszych administratorów panelu, rozdzielone przecinkami albo spacjami |

Adresy powrotu do wpisania u dostawców:

| Środowisko | Google | Microsoft |
| --- | --- | --- |
| local | `http://localhost:8000/api/v1/auth/callback/google` | `http://localhost:8000/api/v1/auth/callback/microsoft` |
| dev | `https://meritum-dev.gburek.app/api/v1/auth/callback/google` | `https://meritum-dev.gburek.app/api/v1/auth/callback/microsoft` |
| prd | `https://meritum.gburek.app/api/v1/auth/callback/google` | `https://meritum.gburek.app/api/v1/auth/callback/microsoft` |

Testy i scenariusze behave (`features/moderation.feature`) używają fałszywego dostawcy (`FakeLogin`) i tokenów podpisanych lokalnym kluczem, bez sieci. Logowanie prawdziwym kontem Google i Microsoft sprawdza się ręcznie na dev, poza CI.

Rejestr podmiotów przetwarzających (ADR-14, design-system#9): Google LLC i Microsoft Corporation przetwarzają dane logowania (identyfikator konta, adres e-mail, imię i nazwisko z profilu) jako dostawcy tożsamości, także poza UE. Meritum zapisuje z nich tylko identyfikator konta i e-mail, w ciasteczku sesji.

## Panel personelu (#22)

Role (`StaffRole` z core): `moderator` widzi sprawy, `analyst` mierniki i eksport, `admin` zarządza kontami i listą tematów wysokiego ryzyka. Adresy z `MERITUM_ADMIN_EMAILS` są administratorami od startu; pozostałe role nadaje administrator. Każdy endpoint panelu sprawdza rolę zależnością `StaffGate` (`staff/api.py`), a zmiany stanu wymagają też `CsrfUser`.

| Endpoint | Role |
| --- | --- |
| `GET /api/v1/staff/me` | każda rola; 403 znaczy „brak dostępu do panelu” |
| `GET`, `POST /api/v1/staff`, `DELETE /api/v1/staff/{email}` | `admin` |
| `GET /api/v1/moderation/cases` | `moderator`, `admin` |
| `GET /api/v1/moderation/topics` | każda rola (lista jest jawna dla personelu) |
| `POST /api/v1/moderation/topics`, `DELETE /api/v1/moderation/topics/{name}` | `admin` |

Konta personelu zapisuje repozytorium z core. Przy `MERITUM_DATABASE_PROVIDER=postgres` nadane role zostają po restarcie API. Schemat aplikacji musi mieć migrację `0003_staff_accounts.sql`, którą wykonuje deploy workera z odpowiednią wersją core. Lokalnie i w CI domyślny provider `memory` używa repozytorium w pamięci z core. Sprawy i tematy panelu są na razie w pamięci procesu.

Przed pierwszym wdrożeniem z PostgreSQL zapisz aktualne przydziały ról z panelu. Po wdrożeniu administrator może nadać je ponownie. Konta administratorów z konfiguracji nadal działają.

Scenariusz restartu uruchom lokalnie po ustawieniu `MERITUM_TEST_DATABASE_URL` na adres PostgreSQL, na którym możesz tworzyć schematy.

```bash
uv run behave --tags=@integration features/moderation.feature
```

## Jednorazowy link jury (#32)

1. Administrator wysyła `POST /api/v1/staff/jury-links` z sesją i nagłówkiem
   `X-CSRF-Token`. Odpowiedź 201 zawiera `url` i `expires_at`. Opcjonalny parametr
   `expires_at` to koniec okresu oceny: data ze strefą czasową najwyżej 7 dni naprzód.
   Bez niego link wygasa po 24 godzinach.
2. Strona `/panel/jury` pobiera token z fragmentu adresu, usuwa fragment z paska
   adresu i wysyła `POST /api/v1/auth/jury-links/redeem` z JSON `{"token": "..."}`.
   Fragment nie trafia do logów dostępu. API zwraca 303 do `/panel/eval`, 404 dla
   nieznanego lub zużytego linku, 410 dla wygasłego, 429 po 10 próbach na minutę z IP.
3. Sesja jury ma rolę `analyst` i `read_only: true` w `GET /api/v1/staff/me`
   (pole pojawia się tylko dla sesji jury; brak pola znaczy `false`).
   `csrf_user` (każda zmiana stanu z sesją) odrzuca ją z 403 `read-only session`;
   wylogowanie (też z CSRF) ją przyjmuje. Publiczne trasy bez sesji
   (np. sprawdzenie obywatela) działają dla jurora jak dla każdego. Odczyt w panelu wymaga jawnego
   `StaffGate(..., allow_jury=True)`. API przebiegów i mierników powstaje w #35.

Na dev i prd skróty SHA-256 oraz terminy ważności są w tabeli `jury_links` w
schemacie API. Realizacja usuwa wiersz w transakcji. Lokalnie adapter trzyma go
w pamięci. Sesja wygasa najpóźniej w chwili wygaśnięcia linku.

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
- `deploy` rusza tylko na `develop` (dev) i `main` (prd), po zielonym `lint` i `tests`, na runnerze `dellpromaxgb10`. `deploy/deploy.sh` buduje obraz na hoście (ARM64), podmienia kontener, czeka na `/api/v1/health/live`, zgłasza wynik `/api/v1/health` (ostrzeżenie przy 503) i, jeśli worker tego środowiska działa, puszcza `ping` przez kolejkę DBOS.

### Sekrety w kontenerze

Job `deploy` podaje skryptowi wszystkie sekrety i zmienne repozytorium (`toJSON(secrets)`, `toJSON(vars)`). Jedyna lista tych, które trafiają do kontenera API, jest w `deploy/container_env.sh`: dla gałęzi `develop` skrypt bierze wariant `_DEV`, dla `main` wariant `_PRD`, i podaje go do `docker run` jako `-e NAZWA`, bez wartości w linii poleceń i bez zapisu na dysk. Brak sekretu nie zatrzymuje deployu; wykrywa go test gotowości (#19). Jeśli plik env środowiska ma `MERITUM_FILES_VOLUME` i `MERITUM_FILES_DIR` (wpisuje je platforma, ADR-31), `docker run` montuje ten wolumen plików pod tym katalogiem (`-v "$MERITUM_FILES_VOLUME:$MERITUM_FILES_DIR"`). Każdy wpis z `MERITUM_GCP_MOUNTS` (lista rozdzielona spacjami, wpisy `host:kontener:ro`, infra#28) trafia do `docker run` jako `-v "<wpis>"`, dzięki czemu `GOOGLE_APPLICATION_CREDENTIALS` wskazuje w kontenerze na istniejący plik poświadczeń Workload Identity Federation. Bez tej zmiennej deploy działa dalej i zgłasza ostrzeżenie.

| Zmienna w kontenerze | Sekret lub zmienna repo | Zgłoszenie |
|---|---|---|
| `MERITUM_DISCORD_PUBLIC_KEY` | `DISCORD_PUBLIC_KEY_{DEV,PRD}` (zmienna) | kanał Discord |
| `MERITUM_CHANNEL_HASH_SALT` | `MERITUM_CHANNEL_HASH_SALT_{DEV,PRD}` (sekret) | #24, #66 (klucze licznika limitów) |
| `MERITUM_DISCORD_BOT_TOKEN` | `DISCORD_BOT_TOKEN_{DEV,PRD}` (sekret) | #19 (test gotowości) |
| `MERITUM_SESSION_SECRET` | `MERITUM_SESSION_SECRET_{DEV,PRD}` (sekret) | #15 |
| `MERITUM_GOOGLE_CLIENT_ID` | `GOOGLE_CLIENT_ID_{DEV,PRD}` (zmienna) | #15 |
| `MERITUM_GOOGLE_CLIENT_SECRET` | `GOOGLE_CLIENT_SECRET_{DEV,PRD}` (sekret) | #15 |
| `MERITUM_MICROSOFT_CLIENT_ID` | `MICROSOFT_CLIENT_ID_{DEV,PRD}` (zmienna) | #15 |
| `MERITUM_MICROSOFT_CLIENT_SECRET` | `MICROSOFT_CLIENT_SECRET_{DEV,PRD}` (sekret) | #15 |
| `MERITUM_ADMIN_EMAILS` | `MERITUM_ADMIN_EMAILS_{DEV,PRD}` (sekret) | #22 |
| `MERITUM_SMS_GATEWAY_USERNAME` | `SMS_GATEWAY_USERNAME_{DEV,PRD}` (sekret) | #29 |
| `MERITUM_SMS_GATEWAY_PASSWORD` | `SMS_GATEWAY_PASSWORD_{DEV,PRD}` (sekret) | #29 |
| `MERITUM_SMS_GATEWAY_WEBHOOK_SIGNING_KEY` | `SMS_GATEWAY_WEBHOOK_SIGNING_KEY_{DEV,PRD}` (sekret) | #29 |
| `MERITUM_SMS_GATEWAY_NUMBER` | `SMS_GATEWAY_NUMBER_{DEV,PRD}` (sekret) | #29 |

Nowy sekret: dopisz wiersz do listy w `deploy/container_env.sh` i do tej tabeli, potem dodaj sekret w ustawieniach repozytorium.

Baza, rola, schemat i plik `~/meritum/envs/api-<env>.env` na hoście pochodzą z platformy w [meritum-infra](https://github.com/Meritum-HackNation2026/meritum-infra) (`onprem/dellpromaxgb10/platform/`). Dostęp do core daje klucz tylko do odczytu w sekrecie repozytorium `MERITUM_CORE_SSH_KEY`.

Gałęzie: zmiany przez PR do `develop`, wydanie przez PR `develop` → `main`. Nie pushuj bezpośrednio do `develop` ani `main`. Na planie Free GitHub nie wymusza tego w repozytoriach prywatnych, więc to zasada zespołu. Gałąź funkcji usuń po merge'u (`gh pr merge --delete-branch` albo przycisk w PR). Automatyczne usuwanie jest wyłączone, bo bez ochrony gałęzi skasowałoby też `develop` po PR `develop` → `main`.
