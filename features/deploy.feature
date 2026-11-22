Feature: Test gotowości przy starcie

  Scenario: brak klucza modelu w workerze
    Given raport gotowości workera wymienia brakującą zmienną "MERITUM_LLM_API_KEY"
    When administrator otwiera GET /api/v1/health
    Then odpowiedź ma kod 503 i wymienia nazwę "MERITUM_LLM_API_KEY"
    And log startu API zawiera tę samą listę

  Scenario: pytanie przy niegotowej usłudze
    Given usługa jest niegotowa
    When obywatel wysyła sprawdzenie
    Then dostaje stan "technical_failure" z kodem "not_ready", bez nazw kluczy w komunikacie

  Scenario: korpus EUvsDisinfo nie blokuje sprawdzeń na dev
    Given worker zgłasza dostawcę "euvsdisinfo" jako niedostępnego
    When obywatel wysyła sprawdzenie
    Then sprawdzenie zostaje przyjęte

  Scenario: worker nie zgłosił gotowości
    Given worker nie opublikował raportu od startu API
    When administrator otwiera GET /api/v1/health
    Then odpowiedź ma kod 503 z informacją, że worker nie zgłosił gotowości
