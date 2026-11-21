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
