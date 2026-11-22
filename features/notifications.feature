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

  Scenario: nowa sprawa
    Given administrator ustawił webhook dla moderatorów
    When powstaje nowa sprawa moderatora
    Then webhook dostaje zdarzenie z numerem sprawy, powodami i linkiem do panelu, bez identyfikatorów kanałów
    And moderatorzy dostają Notification "case_assigned" z case_id w panelu

  Scenario: awaria webhooka
    Given administrator ustawił webhook dla moderatorów
    And webhook odpowiada kodem 500
    When powstaje nowa sprawa moderatora
    Then system ponawia wysyłkę 4 razy i zapisuje błąd
    And sprawa i Notification "case_assigned" istnieją mimo awarii
