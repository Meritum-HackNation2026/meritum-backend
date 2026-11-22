Feature: Ewaluacja jakości z poziomu aplikacji

  Scenario: nowy przebieg na golden secie
    Given zalogowany analityk
    When wysyła POST /api/v1/eval/runs z zestawem "golden"
    Then odpowiedź ma kod 202 z identyfikatorem przebiegu, a przebieg startuje w workerze

  Scenario: własny zestaw
    Given zalogowany analityk
    And plik CSV z 30 przypadkami w formacie przypadków
    When analityk wysyła go na POST /api/v1/eval/datasets
    Then zestaw jest zapisany i można na nim uruchomić przebieg

  Scenario: porównanie
    Given zalogowany analityk
    And dwa zakończone przebiegi
    When analityk otwiera GET /api/v1/eval/runs/compare z identyfikatorami obu przebiegów
    Then dostaje różnice mierników i listę przypadków, które zmieniły wynik
