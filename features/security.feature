Feature: Bezpieczeństwo danych wejściowych

  Scenario: dane osobowe przed startem workflowu
    Given tekst "Zadzwoń pod 600 700 800, mój PESEL to 44051401359"
    When klient wysyła POST /api/v1/checks
    Then wejście workflowu w JobQueue nie zawiera "600 700 800" ani "44051401359", a logi też ich nie mają

  Scenario: usunięcie sprawdzeń sesji przeglądarki
    Given sesja ma 3 sprawdzenia, z których jedno jest w sprawie moderatora
    When obywatel klika „Usuń moje sprawdzenia”, a klient wysyła DELETE /api/v1/sessions/{session_id}/checks
    Then wszystkie 3 zapisy, ich dane workflowów DBOS i powiadomienia sesji znikają
    And sprawa moderatora traci powiązanie z tymi sprawdzeniami, ale zostaje dla innych pytających

  Scenario: sesja nie usuwa cudzych sprawdzeń
    Given sesja ma 3 sprawdzenia, z których jedno jest w sprawie moderatora
    When inna sesja wysyła DELETE /api/v1/sessions/{session_id}/checks z własnym nagłówkiem sesji
    Then odpowiedź ma status 403, a zapisy sesji zostają

  Scenario: przekroczony limit na adres IP
    Given limit 10 sprawdzeń na minutę dla jednego adresu IP
    When z tego adresu przychodzi 11. sprawdzenie w tej samej minucie
    Then odpowiedź ma kod 429, nagłówek Retry-After i komunikat po polsku
    And odpowiedź nie zawiera werdyktu

  Scenario: dwie instancje API
    Given dwie instancje API korzystające z jednego wspólnego licznika
    When 6 zapytań trafia do pierwszej i 5 do drugiej przy limicie 10
    Then 11. zapytanie dostaje 429

  Scenario: za dużo oczekujących sprawdzeń
    Given liczba oczekujących sprawdzeń osiągnęła próg z konfiguracji
    When przychodzi nowe sprawdzenie
    Then odpowiedź ma kod 429 z komunikatem, a workflow nie jest zlecany

  Scenario: polecenie na Discordzie
    Given użytkownik Discorda ma 2 sprawdzenia
    When wysyła polecenie /usun-moje-dane
    Then zapisy z jego skrótem z solą są usunięte, a bot potwierdza to wiadomością widoczną tylko dla niego

  Scenario: identyfikator sesji nie trafia do logów
    Given żądanie DELETE /api/v1/sessions/<session_id>/checks
    When serwer zapisuje log dostępu
    Then w logu ścieżka ma zamaskowany identyfikator sesji

  Scenario: licznik nie przechowuje odwracalnego skrótu IP
    Given żądanie z adresu IP
    When licznik limitu zapisuje klucz
    Then klucz to HMAC-SHA256 adresu z tajnym kluczem z sekretów, a wiersze znikają po zakończeniu okna limitu

  Scenario: sprawdzenie z makiety Discorda
    Given POST /api/v1/checks z channel "discord" i identyfikatorem użytkownika "1234567890"
    When API zleca workflow
    Then wejście workflowu ma channel_user_hash równy session_id, a "1234567890" nie ma w kolejce, bazie ani logach

  Scenario: ten sam użytkownik, dwa wejścia
    Given dwa żądania z tym samym identyfikatorem użytkownika Discorda
    When API liczy skrót
    Then oba mają ten sam channel_user_hash
