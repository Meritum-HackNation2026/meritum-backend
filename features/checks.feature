Feature: Kontrole działającego API

  Scenario: API odpowiada na sprawdzenie żywotności
    Given aplikacja zbudowana przez create_app
    When klient pyta o /api/v1/health/live
    Then odpowiedź ma status 200 i treść {"status": "ok"}
