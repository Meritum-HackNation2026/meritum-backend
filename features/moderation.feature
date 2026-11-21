Feature: Logowanie personelu i obywateli kontem Google albo Microsoft

  Scenario: logowanie kontem Google
    Given dostawca OIDC Google skonfigurowany z identyfikatorem klienta i sekretem
    When użytkownik przechodzi przez GET /api/v1/auth/login/google i wraca z poprawnym kodem
    Then dostaje ciasteczko sesji z flagami HttpOnly, Secure i SameSite=Lax
    And GET /api/v1/auth/me zwraca identyfikator konta od dostawcy i adres e-mail

  Scenario: sfałszowany stan
    Given powrót od dostawcy z parametrem state, który nie pasuje do sesji
    When backend obsługuje powrót
    Then odmawia logowania i nie tworzy sesji

  Scenario: wylogowanie
    Given zalogowany użytkownik
    When wysyła POST /api/v1/auth/logout
    Then ciasteczko jest unieważnione, a GET /api/v1/auth/me zwraca 401

  Scenario: administrator nadaje konto moderatora
    Given zalogowany administrator
    When wysyła POST /api/v1/staff z adresem e-mail i rolą "moderator"
    Then osoba może się zalogować do panelu i widzi sprawy, ale nie listę kont

  Scenario: osoba bez konta
    Given ktoś bez konta nadanego przez administratora
    When próbuje się zalogować do panelu
    Then dostaje odmowę i nie widzi żadnej sprawy

  Scenario: zmiana listy tematów
    Given administrator dodaje temat "wybory" ze słowami kluczowymi
    When kolejne twierdzenie bez odpowiedzi dotyczy wyborów
    Then rozpoznawanie tematów używa nowej listy bez restartu usługi

  Scenario: zalecenie zamienione w przekazanie
    Given wynik ma twierdzenie z werdyktem "brak wystarczających dowodów" i Escalation ze stanem "recommended" bez numeru
    When obywatel wysyła POST /api/v1/checks/{id}/claims/{n}/escalate
    Then odpowiedź ma Escalation ze stanem "created" i numerem "#S-12" albo, przy dołączeniu do podobnej sprawy, ze stanem "updated" i jej numerem

  Scenario: zgłoszenie błędu z uzasadnieniem
    Given wynik z werdyktem "fałszywe"
    When obywatel wysyła POST /api/v1/checks/{id}/claims/{n}/dispute z uzasadnieniem zawierającym numer telefonu
    Then sprawa ma powód "user_dispute", uzasadnienie jest zamaskowane, a obywatel dostaje numer sprawy
    And wynik dla innych pytających się nie zmienia

  Scenario: nieudany zapis sprawy zwraca osobny komunikat
    Given repozytorium spraw moderatora nie przyjmuje zapisu
    When obywatel przekazuje sprawdzenie moderatorom albo zgłasza błąd
    Then API odpowiada 503 z kluczem "escalation.not_saved"
    And odpowiedź nie zawiera numeru sprawy

  Scenario: dołączenie nie zdradza innych pytających
    Given podobne twierdzenie jest już w otwartej sprawie od innej sesji
    When obywatel przekazuje swoje twierdzenie
    Then komunikat nie mówi, że ktoś inny pytał o to samo

  @integration
  Scenario: rola nadana przez administratora przeżywa deploy
    Given backend z MERITUM_DATABASE_PROVIDER=postgres
    When administrator nadaje rolę i backend się restartuje
    Then konto personelu ma nadal tę rolę

  Scenario: wejście z linku jury
    Given administrator utworzył ważny link jury
    When członek jury realizuje link
    Then dostaje sesję analityka tylko do odczytu i trafia na stronę ewaluacji

  Scenario: link jury użyty drugi raz
    Given administrator utworzył ważny link jury
    When członek jury realizuje link
    And kolejna osoba realizuje ten sam link
    Then kolejna osoba dostaje odmowę i pozostaje bez sesji

  Scenario: link jury po terminie
    Given administrator utworzył ważny link jury
    When członek jury realizuje link po okresie oceny
    Then dostaje informację o wygaśnięciu i pozostaje bez sesji

  Scenario: po zalogowaniu moderator wraca tam, skąd zaczął
    Given moderator otwiera /panel i nie jest zalogowany
    When loguje się przez dostawcę OIDC
    Then po powrocie z logowania trafia na /panel

  Scenario: obcy adres powrotu jest odrzucany
    Given żądanie logowania z adresem powrotu https://zly.example/
    When logowanie się kończy
    Then backend przekierowuje na /
