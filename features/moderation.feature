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
