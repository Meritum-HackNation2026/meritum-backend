Feature: Bezpieczeństwo danych wejściowych

  Scenario: dane osobowe przed startem workflowu
    Given tekst "Zadzwoń pod 600 700 800, mój PESEL to 44051401359"
    When klient wysyła POST /api/v1/checks
    Then wejście workflowu w JobQueue nie zawiera "600 700 800" ani "44051401359", a logi też ich nie mają
