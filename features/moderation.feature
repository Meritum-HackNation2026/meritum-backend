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
