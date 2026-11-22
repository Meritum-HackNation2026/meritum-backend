# meritum-backend

API Meritum w FastAPI. Zleca długie operacje workerom ([meritum-worker](https://github.com/Meritum-HackNation2026/meritum-worker)) przez DBOS, a kontrakty bierze z [meritum-core](https://github.com/Meritum-HackNation2026/meritum-core). Frontend to osobne repo ([meritum-frontend](https://github.com/Meritum-HackNation2026/meritum-frontend)): jego nginx przekazuje `/api` do tego API, więc oba działają pod jednym adresem.

| Środowisko | Gałąź | Adres | Kontener | Schemat w bazie |
| --- | --- | --- | --- | --- |
| dev | `develop` | https://meritum-dev.gburek.app/api/v1/health | `meritum-api-dev` | `api_dev` (rola `meritum_api_dev`) |
| prd | `main` | https://meritum.gburek.app/api/v1/health | `meritum-api-prd` | `api_prd` (rola `meritum_api_prd`) |

## Endpointy

| Metoda i ścieżka | Opis |
| --- | --- |
| `GET /api/v1/health` | gotowość (patrz „Test gotowości”): `200 ok` albo `200 degraded` przy awarii tylko opcjonalnych dostawców. Brak wymaganej zależności daje `503 degraded`. Raport zawiera same nazwy zmiennych i dostawców |
| `GET /api/v1/health/live` | żywotność procesu, bez bazy (healthcheck Dockera) |
| `POST /api/v1/jobs/ping` | zleca workflow `ping` (test dymny po deployu), zwraca `workflow_id` |
| `GET /api/v1/jobs/{workflow_id}` | stan zadania: `status`, `output`, `error` |
| `POST /api/v1/checks` | sprawdzenie z każdego kanału: `CheckRequest` (tekst do 4000 znaków, adres http(s) albo `audio_id`), nagłówek `X-Meritum-Session` z losowym identyfikatorem sesji (`session_id` w treści, jeśli jest, musi być taki sam, inaczej 400); maskuje dane osobowe w tekście i w parametrach query linku przed `JobQueue` (bramka PII z `MERITUM_PII_*`, domyślnie pusta, potem wzorce telefonów, e-maili i PESEL) (ścieżka linku zostaje, żeby worker pobrał tę samą stronę; fragment jest usuwany, a link z użytkownikiem lub hasłem dostaje 422), zleca workflow `check`, zwraca 202 i `check_id`; zły wpis daje 422 z kluczem z `copy/pl.json` (`errors.empty`, `errors.too_long`, `errors.invalid_url`); kanały `discord`, `sms` i `mcp` bez `channel_user_id` dostają 400 (SMS przychodzi przez `POST /api/v1/sms/webhook`, Discord przez `POST /api/v1/discord/interactions`); ponad limit dostaje 429 z `Retry-After` (patrz „Limity zapytań”); przy niegotowej usłudze (niedostępna baza API, brak zmiennych API albo braki zgłoszone przez workera) 503 `{"status": "technical_failure", "code": "not_ready", "message_key": "status_hint.technical_failure"}` |
| `POST /api/v1/audio` | nagranie z formularza jako treść żądania (OGG Opus, MP3, M4A albo WAV; format odczytany z bajtów, nie z `Content-Type`); zapisuje plik w `BlobStore` z retencją zapisu sprawdzenia (30 dni) i zwraca 201 z `audio_id` do `POST /api/v1/checks`; odmowa ma `status: out_of_scope`, klucz z `copy/pl.json` oraz `formats`, `max_mb` i `max_minutes` do wstawienia w tekst: 413 `errors.audio_too_large` (ponad 20 MiB), 422 `errors.audio_too_long` (ponad 10 min), 415 `out_of_scope_code.audio`; 10 wysyłek na minutę i 30 na dobę z jednego adresu |
| `GET /api/v1/checks/{check_id}` | `AnalysisStatus`: kroki i, po zakończeniu, `result` (`CheckResult` z `ai_disclosure: true` i nagłówkiem `AI-Disclosure: mode=ai-originated`; gdy wynik ma `ai_marker`, nagłówek dostaje też `model`, `provider` i `date` z tego znacznika) |
| `GET /api/v1/checks/{check_id}/events` | postęp sprawdzenia jako Server-Sent Events: każda wartość strumienia `progress` workflowu (`JobQueue.stream`) to jedno zdarzenie `AnalysisStatus`; `result` pojawia się dopiero po kroku `verify_citations` (`done` albo `skipped`), więc wersja wstępna nie niesie werdyktu; po zakończeniu ostatnie zdarzenie ma pełny `CheckResult` i strumień się zamyka; rozłączenie nie przerywa workflowu, a ponowne połączenie odtwarza kroki od początku (404 dla nieznanego id) |
| `DELETE /api/v1/sessions/{session_id}/checks` | „Usuń moje sprawdzenia” sesji przeglądarki: od razu usuwa zapisy sprawdzeń, powiadomienia i powiązania ze sprawami moderatora, zleca workflow `delete_subject` (dane DBOS i pliki usuwa worker), zwraca 202 i `deleted`; nagłówek `X-Meritum-Session`, jeśli jest, musi wskazywać tę samą sesję (inaczej 403); identyfikator w postaci skrótu kanału albo za krótki daje 400; limit 10 żądań na minutę z jednego adresu (429) |
| `POST /api/v1/checks/{check_id}/claims/{n}/escalate` | „Przekaż moderatorom”: zleca workflow `escalate_claim` (powód `recommended_clicked`) i czeka na zapis sprawy; 200 z `Escalation` `created` albo `updated` z numerem i kluczem `escalation.created`/`escalation.updated`; gdy sprawy nie zapisano, 503 z `Escalation` `recommended` bez numeru i kluczem `escalation.not_saved`; 404 dla nieukończonego sprawdzenia albo nieznanego twierdzenia |
| `POST /api/v1/checks/{check_id}/claims/{n}/dispute` | „Zgłoś błąd”: opcjonalnie `{"justification": "..."}` (maskowane jak pytanie; do 4000 znaków, dłuższe daje 422 `errors.too_long`; po zamaskowaniu przycinane do 1000 przed znacznikiem), powód `user_dispute`, odpowiedzi jak wyżej z kluczem `result.report_error_done`; uzasadnienie jest opcjonalne (brak treści albo same spacje wysyła spór bez niego); wynik sprawdzenia się nie zmienia |
| `POST /api/v1/archives` | „Zarchiwizuj stronę”: `{"url": "https://..."}` (tylko http(s); prywatne adresy, robots.txt, TDM i paywall odrzuca worker), nagłówek `X-Meritum-Session` albo zalogowane konto (bez nich 400); zleca workflow `archive_page` i zwraca 202 z `archive_id` do odpytywania; 5 próśb na godzinę z jednego adresu (429), worker liczy też 5 na godzinę na osobę |
| `GET /api/v1/archives/{archive_id}` | stan kopii: `pending`, `done` (z `url`, `sha256`, `archived_at`, `expires_at`), `refused` (z `refusal` i `message`) albo `failed`; gotową kopię widzi tylko zlecający (ta sama sesja albo konto) i moderatorzy, inni dostają 404 |
| `GET /api/v1/archives/{archive_id}/content` | pobranie zarchiwizowanego tekstu jako `archiwum-<id>.txt` (zlecający albo moderator) |
| `DELETE /api/v1/archives/{archive_id}` | usuwa kopię i jej tekst z `BlobStore` (zlecający albo moderator, 204) |
| `POST /api/v1/discord/interactions` | kanał Discord: interakcje HTTP podpisane kluczem Ed25519 aplikacji (401 przy złym podpisie, 404 gdy środowisko nie ma aplikacji Discord) |
| `POST /api/v1/sms/webhook` | kanał SMS: zdarzenia `sms:received` i `mms:downloaded` bramki sms-gate.app podpisane HMAC (401 przy złym podpisie albo znaczniku czasu spoza ±5 min, 404 gdy środowisko nie ma bramki); zawsze szybkie 202, sprawdzenie idzie do kolejki jobów (patrz „Kanał SMS”) |
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

Ten sam raport trafia do logu startu (`not ready: ...` jako ostrzeżenie), gdy worker odpowie albo po 60 s. `POST /api/v1/checks` przy niegotowej usłudze odpowiada 503 ze stanem `technical_failure` i kodem `not_ready`, bez nazw kluczy; raport dla sprawdzeń jest odświeżany co 30 s. Sam brak (albo wygaśnięcie) raportu workera nie blokuje sprawdzeń: `/health` pokazuje `"worker": "not_reported"`, a API loguje ostrzeżenie. Przełącznik to stała `BLOCK_CHECKS_WITHOUT_WORKER_REPORT` w `src/meritum_backend/health/constants.py` (dziś `False`); po wejściu worker#28 ustaw ją na `True`, żeby sprawdzenia bez raportu workera dostawały `not_ready`. Deploy czeka na `/api/v1/health/live`, potem sprawdza `/api/v1/health`. Przy `200 degraded` zapisuje ostrzeżenie i kontynuuje. Gdy sprawdzenie health nie powiedzie się mimo ponowień, przerywa wdrożenie. Raport workera starszy niż 60 s API odświeża nowym workflowem `readiness`, więc po restarcie workera z poprawionymi kluczami `/health` i sprawdzenia wracają bez restartu API. Jeśli worker nie odpowie na zlecony workflow przez 60 s, API zleca go ponownie, a ostatni raport przestaje się liczyć (`"worker": "not_reported"`); przy wyłączonym workerze i odpytywanym `/health` w kolejce przybywa więc jeden workflow `readiness` na minutę. Gdy start przerywa źle skonfigurowany magazyn plików, log przed wyjściem wymienia brakujące zmienne API (`not ready, cannot start: ...`). Klient DBOS w API nie ponawia połączeń (`retry_connection_errors=False`): przy chwilowej awarii bazy każde zlecenie (`check`, `ping`) od razu dostaje 503, zamiast czekać.

## Kanał Discord

Discord to kanał wejściowy jak formularz i wtyczka: interakcje HTTP (bez bota z trwałym połączeniem) trafiają do `POST /api/v1/discord/interactions`. Komendy:

- `/sprawdz tekst:<tekst albo link> [publiczne:True]`,
- „Sprawdź w Meritum” w menu Aplikacje przy dowolnej wiadomości.

Aplikację da się dodać do serwera albo do własnego konta, a odpowiedź domyślnie widzi tylko pytający; z opcją `publiczne:True` widzi ją cały kanał (menu wiadomości nie ma opcji, więc zawsze odpowiada prywatnie). Każdy doda ją do własnego serwera (albo konta) linkiem zaproszenia:

- dev: <https://discord.com/oauth2/authorize?client_id=1573690220782559332&scope=applications.commands>
- prd: <https://discord.com/oauth2/authorize?client_id=1573692006398693396&scope=applications.commands>

Komenda woła to samo sprawdzenie co `POST /api/v1/checks` (funkcja `start_check`, z kanałem `discord` i skrótem identyfikatora użytkownika), więc wynik nie zależy od kanału. Discord czeka na odpowiedź 3 s, dlatego endpoint od razu odpowiada odroczoną odpowiedzią („Meritum myśli…”), a po zakończeniu sprawdzenia zastępuje ją wynikiem (przycisk „Pełna karta” prowadzi do `/sprawdzenie/<check_id>`), przy pierwszym użyciu poprzedzone informacją, że odpowiada system AI, a numer sprawy tylko wtedy, gdy sprawa u moderatorów została utworzona albo zaktualizowana. Wynik to jedna wiadomość: osadzenie z polem na każde twierdzenie (werdykt, twierdzenie, najważniejszy cytat ze źródłem i datą albo ocena fact-checkera z linkiem, siła podstawy), kolor osadzenia z najpoważniejszego werdyktu i przycisk-link „Pełna karta” pod spodem. Za długi wynik (6000 znaków, 25 pól) skraca cytaty, nie twierdzenia. Format (`meritum_backend.discord.reply_message`) wykorzystuje też proces Gateway (backend#39). Odpowiedzi idą przez webhook interakcji (token ważny 15 minut), bez tokenu bota i bez wzmianek (`allowed_mentions` puste).

Każde środowisko ma własną aplikację Discord. Jej klucz publiczny jest w zmiennych repo `DISCORD_PUBLIC_KEY_DEV` i `DISCORD_PUBLIC_KEY_PRD` (deploy przekazuje go jako `MERITUM_DISCORD_PUBLIC_KEY`, patrz „Sekrety w kontenerze”), a w ustawieniach aplikacji jako Interactions Endpoint URL wpisany jest `https://meritum-dev.gburek.app/api/v1/discord/interactions` albo `https://meritum.gburek.app/...`. Komendy rejestruje sam deploy (`deploy/deploy.sh`, zmienna `DISCORD_APPLICATION_ID_{DEV,PRD}` i sekret `DISCORD_BOT_TOKEN_{DEV,PRD}`), więc nowa opcja trafia do Discorda razem z wdrożeniem. Ręcznie (nowa aplikacja, test lokalny):

```bash
DISCORD_APPLICATION_ID=... DISCORD_BOT_TOKEN=... uv run python scripts/register_discord_commands.py
```

### Gateway: wzmianki i wiadomości prywatne

Interakcje HTTP nie dostarczają zwykłych wiadomości, więc wzmianki na kanale serwera i wiadomości prywatne obsługuje osobny proces połączony z Gateway Discorda: `python -m meritum_backend.discord.gateway` (`src/meritum_backend/discord/gateway/`), z tego samego obrazu co API. Klient to [discord.py](https://discordpy.readthedocs.io/) 2.x. Proces składa te same porty co API (kolejka, limity, maskowanie danych osobowych, pamięć wyników, zapisy sprawdzeń) i woła `start_check` z kanałem `discord` oraz `reply_when_done` z formatem i podziałem odpowiedzi z `meritum_backend.discord`, więc nie ma w nim własnej weryfikacji.

- Intencje: tylko `guilds`, `guild_messages` i `dm_messages`, bez uprzywilejowanej `MESSAGE_CONTENT`. Discord i tak przekazuje treść wiadomości, która wspomina bota, i wiadomości prywatnych. Wiadomość na serwerze bez wzmianki bota jest ignorowana, tak samo wiadomości innych botów.
- Odpowiedź: na serwerze jako odpowiedź na wiadomość z wzmianką (bez pingowania autora), w wiadomości prywatnej jako zwykłe wiadomości w tej rozmowie. Wzmianka bez tekstu dostaje podpowiedź `errors.empty`.
- Wznowienie sesji: Discord po wznowieniu odtwarza zdarzenia, dlatego proces pamięta identyfikatory ostatnich 1000 wiadomości i drugi raz na tę samą nie odpowiada. Pamięć jest w procesie, więc po jego restarcie (nowa sesja, nie wznowienie) wiadomość sprzed restartu nie wraca.
- Token: `MERITUM_DISCORD_BOT_TOKEN`. Bez niego proces loguje błąd i kończy się kodem 1; test gotowości API zgłasza brak tokenu, gdy kanał Discord jest włączony kluczem publicznym.
- Deploy: `deploy/deploy.sh` uruchamia kontener `meritum-discord-<env>` (ten sam obraz, polecenie Gateway, bez healthchecku HTTP), gdy sekret `DISCORD_BOT_TOKEN_{DEV,PRD}` jest ustawiony; bez niego kontenera nie startuje i usuwa stary.
- Na serwerze bot potrzebuje uprawnień do czytania i pisania w kanale. Próbę na żywym bocie i serwerze testowym wykonuje się ręcznie, poza CI.

Endpoint nie ma limitu po IP (wszystkie żądania przychodzą z serwerów Discorda); wspólne limity sprawdzeń liczą skrót użytkownika Discorda.

## Kanał SMS

Bramką jest telefon z Androidem (polska karta prepaid) z aplikacją SMS Gateway for Android w trybie Cloud ([sms-gate.app](https://docs.sms-gate.app/)). W tym trybie treść SMS-ów przechodzi przez serwery sms-gate.app. Usługa jest bezpłatna; operator nadawcy może pobrać standardową opłatę za SMS według jego taryfy.

- Odbiór: bramka wysyła `POST /api/v1/sms/webhook` z nagłówkami `X-Signature` (hex `HMAC_SHA256(klucz, surowe body + X-Timestamp)`) i `X-Timestamp`. Zły podpis albo znacznik czasu starszy lub nowszy niż 5 minut daje 401. Bramka ponawia zdarzenie do ok. 2 dni, dopóki nie dostanie 2xx, więc identyfikator workflowu to `sms-` i 32 znaki hex SHA-256 z `<deviceId>-<id>` (prawdziwe identyfikatory bramki przekraczają 40 znaków `check_id`): powtórzone zdarzenie nie startuje drugiego sprawdzenia.
- Numer nadawcy najpierw trafia do formatu E.164 (`600 700 800`, `0048600700800` i `+48 600 700 800` to ten sam `+48600700800`), a potem od razu zamienia się w skrót z solą (`MERITUM_CHANNEL_HASH_SALT`, ta sama funkcja co w backend#24), który jest `session_id` i `channel_user_hash`. Surowy numer zostaje tylko w pamięci zadania, które po zakończeniu sprawdzenia wysyła odpowiedź; restart procesu gubi odpowiedź, ale numer nigdzie nie trafia.
- Odpowiedź to werdykt głównego twierdzenia, bez linku (operatorzy filtrują linki), najwyżej 70 znaków UCS-2 na SMS. Pierwszy SMS do numeru bez wcześniejszych sprawdzeń poprzedza informacja, że odpowiada system AI. `MERITUM_SMS_GSM7=true` zamienia polskie litery na litery bez ogonków i pozwala na 160 znaków. Sprawdzenie, które nie skończy się w 10 minut, dostaje tekst o niepowodzeniu.
- SMS o treści `USUN` (także `USUŃ`, wielkość liter bez znaczenia) usuwa zapisy sprawdzeń dla skrótu tego numeru (`delete_subject`, backend#20).
- Sprawdzenie z SMS-a przechodzi przez te same limity co formularz (kanał `sms` i próg oczekujących sprawdzeń); skrót numeru zastępuje w nich adres IP, bo wszystkie webhooki przychodzą z serwerów sms-gate.app. Odmowa daje 202 `refused` bez odpowiedzi SMS, więc nie kosztuje SMS-a z karty bramki.
- SMS bramki do samej siebie (numer `MERITUM_SMS_GATEWAY_NUMBER`) dostaje 202 bez sprawdzenia i bez odpowiedzi, żeby nie zapętlić odpowiedzi.
- Wiadomość z telefonu z włączonym RCS („czat” w Wiadomościach Google) bramka widzi jako MMS i wysyła [`mms:downloaded`](https://docs.sms-gate.app/features/mms/#mms-webhook-events) zamiast `sms:received`. Jej pole `body` idzie tą samą ścieżką co tekst SMS-a (podpis, deduplikacja, skrót numeru, `USUN`); załączniki są pomijane i nigdzie nie trafiają. MMS bez tekstu dostaje 202 `ignored`.

Webhooki `sms:received` i `mms:downloaded` są rejestrowane tylko dla dev; dev i prd korzystają z tego samego telefonu, więc prd dostanie własny webhook dopiero po decyzji zespołu (każdy SMS trafiłby wtedy do obu środowisk i oba by odpowiedziały). Rejestracja (stały `id` nadpisuje webhook zamiast tworzyć drugi; webhooków `web-dashboard-*` nie usuwaj):

```bash
curl -X POST -u "$SMS_GATEWAY_USERNAME:$SMS_GATEWAY_PASSWORD" -H "Content-Type: application/json" \
  -d '{"id":"meritum-dev-sms-received","url":"https://meritum-dev.gburek.app/api/v1/sms/webhook","event":"sms:received"}' \
  https://api.sms-gate.app/3rdparty/v1/webhooks
```

Drugi webhook, dla wiadomości RCS/MMS, na ten sam adres:

```bash
curl -X POST -u "$SMS_GATEWAY_USERNAME:$SMS_GATEWAY_PASSWORD" -H "Content-Type: application/json" \
  -d '{"id":"meritum-dev-mms-downloaded","url":"https://meritum-dev.gburek.app/api/v1/sms/webhook","event":"mms:downloaded"}' \
  https://api.sms-gate.app/3rdparty/v1/webhooks
```

Próba na żywo (ręcznie, poza CI): wyślij przez bramkę SMS na jej własny numer i sprawdź w logach `meritum-api-dev` wpis `POST /api/v1/sms/webhook ... 202`.

## Konektor MCP

Serwer MCP pozwala sprawdzić twierdzenie z aplikacji czatu (US-WDR-06, US-WTY-09, F-37, F-42, ADR-17). Działa w tym samym procesie co API, więc sprawdzenie przechodzi przez to samo maskowanie danych osobowych, te same limity i pamięć wyników co formularz, a odpowiedź niesie werdykt, cytaty z linkami, siłę podstawy i informację, że wynik tworzy system AI.

| | |
|---|---|
| Adres | dev: `https://meritum-dev.gburek.app/mcp`, prd: `https://meritum.gburek.app/mcp` (bez ukośnika na końcu, bo aplikacje czatu nie podążają za przekierowaniami) |
| Transport | Streamable HTTP |
| Narzędzia | `check_claim` (jedno twierdzenie albo pytanie o fakt, do 4000 znaków; czeka do 90 s na wynik) i `search_sources` (krótkie fragmenty z katalogu źródeł: tytuł, wydawca, data, link, wersja korpusu; to nie jest werdykt) |
| Uwierzytelnianie | klucz API w nagłówku `Authorization: Bearer <klucz>` albo `X-API-Key: <klucz>`, token dostępu z wbudowanego serwera OAuth (niżej) albo token zewnętrznego serwera OAuth sprawdzany introspekcją (RFC 7662); bez nich 401 z `WWW-Authenticate: Bearer realm="meritum-mcp", resource_metadata="<adres>/.well-known/oauth-protected-resource/mcp"` |
| Limity | `check_claim` i `search_sources` mają wspólny limit 30 wywołań na minutę na klienta (według etykiety klucza API lub tożsamości OAuth). `check_claim` podlega też limitom z sekcji „Limity zapytań”, a `search_sources` ma dodatkowo limit 30 wyszukiwań na minutę z jednego adresu. Po przekroczeniu limitu narzędzie prosi o ponowną próbę za minutę. |
| Retencja | jak w każdym kanale: zapis sprawdzenia 30 dni; „Usuń moje sprawdzenia” działa po skrócie identyfikatora klienta |
| Identyfikator klienta | etykieta klucza (część przed `=`) albo `client_id`/`sub` tokenu OAuth; API zapisuje tylko skrót HMAC-SHA-256 z `<kanał>:<identyfikator>` i solą `MERITUM_CHANNEL_HASH_SALT`, surowy identyfikator nie trafia do kolejki, bazy ani logów |

### Konfiguracja

| Zmienna | Opis |
|---|---|
| `MERITUM_MCP_API_KEYS` | pary `etykieta=klucz` rozdzielone przecinkami; jedna etykieta na konektor, żeby dało się odebrać dostęp jednemu klientowi. Deploy bierze je z sekretu repozytorium `MERITUM_MCP_API_KEYS_{DEV,PRD}` (patrz „Sekrety w kontenerze”) |
| `MERITUM_MCP_OAUTH_INTROSPECTION_URL`, `MERITUM_MCP_OAUTH_CLIENT_ID`, `MERITUM_MCP_OAUTH_CLIENT_SECRET` | serwer OAuth, który wydaje tokeny aplikacjom czatu; muszą być ustawione wszystkie trzy |

Bez żadnej z tych zmiennych `/mcp` odpowiada 401 każdemu. Klucze generuj losowo (`openssl rand -base64 32`), nie wklejaj ich do zgłoszeń, logów ani zrzutów ekranu.

### Jak podłączyć klienta

Stan na 2026-11-22 według oficjalnych instrukcji: [Claude](https://support.claude.com/en/articles/11175166), [ChatGPT](https://help.openai.com/en/articles/12584461) i [tryb deweloperski ChatGPT](https://developers.openai.com/api/docs/guides/developer-mode). Przy rozbieżności obowiązuje strona producenta.

**Claude Code i inspektor MCP: przetestowana droga z kluczem API.**

```bash
# $MERITUM_MCP_KEY: klucz z listy MERITUM_MCP_API_KEYS
claude mcp add --transport http meritum https://meritum-dev.gburek.app/mcp \
  --header "Authorization: Bearer $MERITUM_MCP_KEY"
npx @modelcontextprotocol/inspector   # Streamable HTTP, adres jak wyżej, nagłówek X-API-Key
```

**claude.ai: zalecane logowanie OAuth („Sign in now”).** Własne konektory są na planach Free (jeden), Pro, Max, Team i Enterprise. claude.ai dostaje z `/mcp` odpowiedź 401 ze wskazaniem metadanych OAuth, więc przy „No sign in” ostrzega: „This server offers OAuth sign-in: choose 'Sign in now' instead”. To ten sam serwer OAuth co dla ChatGPT (niżej). Każda osoba loguje się swoim kontem, limity liczą się na nią (`oauth:<user_id>`), a klucz API nie trafia do formularza.

1. Pro i Max: Customize → Connectors → „+ Add” → „Add custom connector”. W Team i Enterprise konektor dodaje właściciel organizacji (Organization settings → Connectors), a członkowie klikają „Connect”.
2. Nazwa `Meritum`, adres `https://meritum-dev.gburek.app/mcp` (bez ukośnika na końcu), „Continue”.
3. Authentication: „Sign in now”. Pól OAuth Client ID i Client Secret nie wypełniaj: claude.ai rejestruje się sam przez `POST /api/v1/oauth/register` (klient publiczny, PKCE `S256`).
4. Przeglądarka przechodzi na logowanie Meritum. Zaloguj się kontem Google (Microsoft tylko wtedy, gdy na serwerze nie ma Google; wybór dostawcy w #146). Kto jest już zalogowany w Meritum, wraca do claude.ai od razu, bo nie ma ekranu zgody.
5. W rozmowie „+” → „Connectors”, włącz Meritum i napisz: „Sprawdź w Meritum: <twierdzenie>”. Odpowiedź ma mieć werdykt, cytaty z linkami, siłę podstawy i informację o AI.

Token dostępu żyje godzinę, a claude.ai odnawia go tokenem odświeżania przez 7 dni. Po tym czasie albo po zmianie `MERITUM_SESSION_SECRET` trzeba kliknąć „Connect” przy konektorze i zalogować się jeszcze raz.

**claude.ai: klucz API w nagłówku (zapasowo).** Działa na dev z nagłówkiem `X-API-Key`, mimo ostrzeżenia o OAuth. Wszyscy, którzy używają tego samego klucza, dzielą jego limit i identyfikator klienta, więc to droga dla zespołu i na wypadek awarii logowania, nie dla jury.

1. Kroki 1 i 2 jak wyżej.
2. Authentication: „No sign in”; w „Request headers” nagłówek `X-API-Key` z kluczem z `MERITUM_MCP_API_KEYS`. Ostrzeżenie o OAuth nie blokuje dodania.
3. „Add”, w rozmowie „+” → „Connectors”, włącz Meritum.

Etykiety przycisków są według formularza claude.ai z 22.11.2026; przy rozbieżności obowiązuje strona producenta.

Serwer musi być osiągalny z internetu na porcie 443 (adresy Meritum to spełniają).

**ChatGPT: OAuth.** ChatGPT nie wyśle klucza API, więc API ma własny, minimalny serwer OAuth 2.1 (ten sam obsługuje claude.ai) według specyfikacji autoryzacji MCP (#117). Logowanie to zwykłe logowanie Google albo Microsoft z sekcji „Logowanie (OIDC)”, bez nowych sekretów. Własne serwery MCP są w ChatGPT Business i Enterprise/Edu w przeglądarce, a w Pro z uprawnieniami odczytu; Developer mode nie jest wymagany.

1. <https://chatgpt.com/plugins> → „+” → „Add custom MCP server” (starsza ścieżka: Workspace settings → Apps → Create).
2. Nazwa `Meritum`, w „Connection” adres `https://meritum-dev.gburek.app/mcp` (Streamable HTTP).
3. Authentication: „OAuth”. Pola klienta zostaw puste: ChatGPT sam znajdzie serwer i zarejestruje się (dynamiczna rejestracja).
4. „I understand and want to continue” → „Create as a plugin”, zainstaluj, zaloguj się kontem Google (albo Microsoft, gdy Google nie jest skonfigurowany) i wpisz `@Meritum` w rozmowie.

Jak to działa:

| Endpoint | Rola |
|---|---|
| `GET /.well-known/oauth-protected-resource[/mcp]` | RFC 9728: zasób `<adres>/mcp` i jego serwer autoryzacji; odpowiedź 401 z `/mcp` wskazuje go w `WWW-Authenticate: Bearer resource_metadata="…"` |
| `GET /.well-known/oauth-authorization-server` | RFC 8414: wystawcą jest sam adres publiczny, PKCE tylko `S256`, klient publiczny (`none`), parametr `iss` w odpowiedzi (RFC 9207) |
| `POST /api/v1/oauth/register` | RFC 7591: adresy przekierowania tylko `https` albo `http` na localhost, bez fragmentu, najwyżej 5 |
| `GET /api/v1/oauth/authorize` | kod autoryzacji z PKCE; niezalogowany idzie przez logowanie OIDC i wraca na `/api/v1/oauth/authorize/resume` |
| `POST /api/v1/oauth/token` | kod (60 s, jednorazowy, zgodny klient, `redirect_uri` i weryfikator PKCE) albo token odświeżania; token dostępu żyje 1 h, odświeżania 7 dni |

Jedyny zakres to `mcp`, a tokeny mają odbiorcę `<adres>/mcp`. Klient MCP w limitach to `oauth:<user_id>`, więc limity liczą się na osobę.

Ograniczenia tej wersji: nic nie jest zapisywane w bazie, więc identyfikator klienta, kody i tokeny są podpisane kluczem `MERITUM_SESSION_SECRET` (zmiana klucza unieważnia wszystkie). Nie ma ekranu zgody (#146) ani odwoływania pojedynczego tokenu: token daje tylko narzędzia, które i tak są publiczne. Stary token odświeżania działa do wygaśnięcia, mimo że każde odświeżenie wydaje nowy. Jednorazowość kodu pilnuje pamięć procesu, więc API musi działać w jednej replice. Dokumenty klienta (CIMD) nie są obsługiwane; ChatGPT używa wtedy dynamicznej rejestracji.

Ścieżki `/.well-known/oauth-*` muszą trafiać do API: nginx aplikacji webowej przekazuje dziś do API tylko `/api/` i `/mcp`.

Ręczne próby w ChatGPT i claude.ai (data, wersja, zrzuty) trafiają do opisu PR i do zgłoszeń o znalezionych problemach. Żaden krok CI nie łączy się z tymi usługami.

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

`GET /api/v1/export` zwraca sprawdzenia z ostatnich `days` dni we wszystkich kanałach, również bez sprawy moderatora. Gdy zapisów jest więcej niż 10 000, API zwraca 422. Zmniejsz `days`, aby pobrać krótszy okres.

| Endpoint | Role |
| --- | --- |
| `GET /api/v1/staff/me` | każda rola; 403 znaczy „brak dostępu do panelu” |
| `GET`, `POST /api/v1/staff`, `DELETE /api/v1/staff/{email}` | `admin` |
| `GET`, `PUT`, `DELETE /api/v1/staff/notifications` | `admin`: cel powiadomień moderatorów |
| `GET /api/v1/moderation/cases` | `moderator`, `admin` |
| `GET /api/v1/moderation/topics` | każda rola (lista jest jawna dla personelu) |
| `POST /api/v1/moderation/topics`, `DELETE /api/v1/moderation/topics/{name}` | `admin` |

Powiadomienia o nowej lub zaktualizowanej sprawie (`notifications/`): po zapisaniu sprawy przez „Przekaż moderatorom” albo „Zgłoś błąd” moderatorzy i administratorzy dostają w skrzynce `case_assigned` (adres skrzynki to `staff:` i skrót adresu e-mail, czytany po zalogowaniu zweryfikowanym adresem), a administrator wybiera dodatkowo jeden cel: `webhook` (JSON `{event, case_id, reasons, panel_url}` podpisany HMAC-SHA256 sekretem z konfiguracji, nagłówki `X-Meritum-Timestamp` i `X-Meritum-Signature: sha256=<hex z "<timestamp>.<body>">`), `google_chat` (adres przestrzeni) albo `email` (Worker Cloudflare z infra/009 pod `MERITUM_EMAIL_WORKER_URL`, na adresy moderatorów). Wysyłka idzie po odpowiedzi, ma 4 próby (1 s, 2 s, 4 s przerwy) i po ostatniej tylko zapisuje błąd w logu; nie blokuje sprawy. Treść nie ma danych osobowych ani identyfikatorów kanałów. Konfiguracja leży w tabeli `notifier_config` (poza lokalnym środowiskiem, gdzie jest w pamięci); sekret nigdy nie wraca w API. Sprawy, które powstają poza tą ścieżką (np. samoczynnie w workerze), backend nie ogłasza.

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
- `deploy` rusza tylko na `develop` (dev) i `main` (prd), po zielonym `lint` i `tests`, na runnerze `dellpromaxgb10`. `deploy/deploy.sh` buduje obraz na hoście (ARM64), podmienia kontener, czeka na `/api/v1/health/live`, sprawdza `/api/v1/health` (ostrzeżenie przy `200 degraded`, przerwanie po wyczerpaniu ponowień) i, jeśli worker tego środowiska działa, puszcza `ping` przez kolejkę DBOS.

### Sekrety w kontenerze

Job `deploy` podaje skryptowi wszystkie sekrety i zmienne repozytorium (`toJSON(secrets)`, `toJSON(vars)`). Jedyna lista tych, które trafiają do kontenera API, jest w `deploy/container_env.sh`: dla gałęzi `develop` skrypt bierze wariant `_DEV`, dla `main` wariant `_PRD`, i podaje go do `docker run` jako `-e NAZWA`, bez wartości w linii poleceń i bez zapisu na dysk. Brak wymaganego sekretu zatrzymuje deploy na kontroli gotowości (#19). Jeśli plik env środowiska ma `MERITUM_FILES_VOLUME` i `MERITUM_FILES_DIR` (wpisuje je platforma, ADR-31), `docker run` montuje ten wolumen plików pod tym katalogiem (`-v "$MERITUM_FILES_VOLUME:$MERITUM_FILES_DIR"`). Każdy wpis z `MERITUM_GCP_MOUNTS` (lista rozdzielona spacjami, wpisy `host:kontener:ro`, infra#28) trafia do `docker run` jako `-v "<wpis>"`, dzięki czemu `GOOGLE_APPLICATION_CREDENTIALS` wskazuje w kontenerze na istniejący plik poświadczeń Workload Identity Federation. Bez tej zmiennej deploy działa dalej i zgłasza ostrzeżenie.

| Zmienna w kontenerze | Sekret lub zmienna repo | Zgłoszenie |
|---|---|---|
| `MERITUM_DISCORD_PUBLIC_KEY` | `DISCORD_PUBLIC_KEY_{DEV,PRD}` (zmienna) | kanał Discord |
| `MERITUM_CHANNEL_HASH_SALT` | `MERITUM_CHANNEL_HASH_SALT_{DEV,PRD}` (sekret) | #24, #66 (klucze licznika limitów) |
| `MERITUM_DISCORD_BOT_TOKEN` | `DISCORD_BOT_TOKEN_{DEV,PRD}` (sekret) | #19 (test gotowości), #39 (proces Gateway) |
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
| `MERITUM_EMAIL_WORKER_URL` | `EMAIL_WORKER_URL_{DEV,PRD}` (zmienna) | #34 |
| `MERITUM_EMAIL_WORKER_SIGNING_SECRET` | `MERITUM_EMAIL_WORKER_SIGNING_SECRET_{DEV,PRD}` (sekret) | #34 |
| `MERITUM_MCP_API_KEYS` | `MERITUM_MCP_API_KEYS_{DEV,PRD}` (sekret) | #43, #44 (klucze klientów MCP, `etykieta=klucz,etykieta2=klucz2`) |

Nowy sekret: dopisz wiersz do listy w `deploy/container_env.sh` i do tej tabeli, potem dodaj sekret w ustawieniach repozytorium.

Baza, rola, schemat i plik `~/meritum/envs/api-<env>.env` na hoście pochodzą z platformy w [meritum-infra](https://github.com/Meritum-HackNation2026/meritum-infra) (`onprem/dellpromaxgb10/platform/`). Dostęp do core daje klucz tylko do odczytu w sekrecie repozytorium `MERITUM_CORE_SSH_KEY`.

Gałęzie: zmiany przez PR do `develop`, wydanie przez PR `develop` → `main`. Nie pushuj bezpośrednio do `develop` ani `main`. Na planie Free GitHub nie wymusza tego w repozytoriach prywatnych, więc to zasada zespołu. Gałąź funkcji usuń po merge'u (`gh pr merge --delete-branch` albo przycisk w PR). Automatyczne usuwanie jest wyłączone, bo bez ochrony gałęzi skasowałoby też `develop` po PR `develop` → `main`.

## Lista linków demo (#126)

Administrator zalogowany przez OIDC pobiera `GET /api/v1/staff/demo-links`
na dev i lokalnie. Lista zawiera identyfikator, konto, datę wydania i termin
ważności każdego aktywnego linku. Pełny adres jest dostępny w odpowiedzi na
wydanie. `POST /api/v1/staff/demo-links/revoke` przyjmuje `{"id":"…"}`
z nagłówkiem `X-CSRF-Token`.

Metadane zapisuje tabela `demo_link_metadata` z migracji 0009 z meritum-core.
Linki sprzed tej zmiany działają do swojego terminu ważności. Lista obejmuje
linki wydane po wdrożeniu zapisu metadanych.

## Dane demo dla jury (dev)

`scripts/seed_demo.py` zasila konta demo (backend#53) przykładowymi danymi, żeby jury nie widziało pustych ekranów: 6 sprawdzeń (prawda, fałsz, częściowo poparte, opinia, link, twierdzenie zdrowotne), sprawa moderatora z odpowiedzią, jedno uruchomienie ewaluacji i powiadomienie `moderator_answer` dla obywatela. Skrypt używa tylko publicznego API z uwierzytelnieniem (nic nie zapisuje w bazie), działa wyłącznie na dev i lokalnie (inny adres kończy się odmową) i jest idempotentny: krok, którego wynik już istnieje, jest pomijany. Prawdziwych danych osobowych nie ma.

Potrzebne dane (nie wpisuj ich do repozytorium ani zgłoszeń):

| Zmienna | Skąd |
|---|---|
| `MERITUM_DEMO_CITIZEN_LINK`, `MERITUM_DEMO_ADMIN_LINK` | linki demo „obywatel” i „admin” z `POST /api/v1/staff/demo-links` (wydaje je administrator zalogowany OIDC, dev, do 7 dni) |
| `MERITUM_MODERATOR_SESSION` (opcjonalna) | wartość ciasteczka `meritum_session` moderatora zalogowanego w przeglądarce; odpowiedź na sprawę wymaga roli moderatora, której konto demo admina nie ma. Bez niej krok odpowiedzi jest pomijany |

```bash
uv run python scripts/seed_demo.py --dry-run      # co by powstało, bez zapisów
uv run python scripts/seed_demo.py                # właściwe uruchomienie
uv run python scripts/seed_demo.py --audio nagranie.ogg --image zrzut.png   # opcjonalnie audio i obraz
```

Ponowne uruchomienie niczego nie dubluje: sprawdzenia rozpoznaje po historii konta obywatela, sprawę po `check_id` w jej twierdzeniach, ewaluację po istniejącej liście uruchomień. Wyjątek: `--audio` i `--image` dodają za każdym razem nowe sprawdzenie. Adres zmienia `--url` albo `MERITUM_SEED_URL` (domyślnie dev). Test: `tests/scripts/test_seed_demo.py`.
