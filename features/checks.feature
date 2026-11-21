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
