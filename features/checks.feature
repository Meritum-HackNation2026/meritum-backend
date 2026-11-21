Feature: Kontrole działającego API

  Scenario: API odpowiada na sprawdzenie żywotności
    Given aplikacja zbudowana przez create_app
    When klient pyta o /api/v1/health/live
    Then odpowiedź ma status 200 i treść {"status": "ok"}

  Scenario: tekst do sprawdzenia
    Given tekst "Czy we Włoszech ostatnio odbywał się strajk generalny?" z kanału "web" i nagłówkiem X-Meritum-Session
    When klient wysyła POST /api/v1/checks
    Then odpowiedź ma kod 202 i identyfikator sprawdzenia
    And GET /api/v1/checks/{id} zwraca AnalysisStatus z krokami, a po zakończeniu pole result z CheckResult

  Scenario: zbyt długi tekst
    Given tekst o długości 4001 znaków
    When klient wysyła POST /api/v1/checks
    Then odpowiedź ma kod 422 z kluczem komunikatu po polsku i żaden workflow nie startuje

  Scenario: adres bez schematu http(s)
    Given wejście "ftp://example.com/plik"
    When klient wysyła POST /api/v1/checks
    Then odpowiedź ma kod 422 z komunikatem, że przyjmujemy tylko adresy http:// albo https://

  Scenario: postęp kroków w strumieniu
    Given trwa sprawdzenie tekstu bez linku
    When klient otwiera GET /api/v1/checks/{id}/events
    Then dostaje zdarzenia AnalysisStatus, w których kilka kroków badań ma jednocześnie stan "active"
    And krok "fetch_url" ma stan "skipped"

  Scenario: wersja wstępna bez werdyktu
    Given cytaty nie przeszły jeszcze weryfikacji
    When serwer wysyła wersję wstępną odpowiedzi
    Then zdarzenie nie zawiera werdyktu

  Scenario: koniec sprawdzenia
    Given workflow kończy się stanem "done"
    When serwer wysyła ostatnie zdarzenie
    Then zdarzenie zawiera AnalysisStatus z pełnym CheckResult w polu result, a strumień się zamyka

  Scenario: nagranie z formularza
    Given plik M4A o długości 40 s
    When klient wysyła POST /api/v1/audio
    Then odpowiedź ma kod 201 i audio_id
    And POST /api/v1/checks z tym audio_id startuje sprawdzenie z krokiem "transcribe_audio"

  Scenario: odrzucony format audio niesie kod, a nie klucz kopii w message
    Given plik "nagranie.xyz"
    When klient wysyła go do sprawdzenia
    Then odpowiedź niesie kod z kontraktu v4, a message nie zaczyna się od "status_hint."

  Scenario: za duży plik
    Given plik większy niż limit rozmiaru z core/013
    When klient wysyła POST /api/v1/audio
    Then odpowiedź ma kod 413 z komunikatem po polsku, bez werdyktu
