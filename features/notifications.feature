Feature: Powiadomienia w skrzynce i na żywo

  Scenario: koniec sprawdzenia, gdy użytkownik jest gdzie indziej
    Given sesja ma otwarty strumień GET /api/v1/notifications/stream
    When workflow sprawdzania tej sesji się kończy
    Then sesja dostaje Notification z kind "check_done", check_id i linkiem do wyniku, bez treści pytania

  Scenario: skrzynka nieprzeczytanych
    Given sesja dostała 2 powiadomienia i nie zareagowała
    When klient otwiera GET /api/v1/notifications
    Then lista ma 2 powiadomienia ze stanem "unread", a POST /api/v1/notifications/{id}/read zmienia stan na "read"

  Scenario: zalogowany użytkownik na drugim urządzeniu
    Given powiadomienie ma user_id zalogowanego obywatela
    When obywatel otwiera skrzynkę na innym urządzeniu
    Then widzi to powiadomienie
