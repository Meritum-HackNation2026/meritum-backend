Feature: Kanały bez sesji przeglądarki

  Scenario: pierwszy SMS z nowego numeru
    Given webhook bramki SMS dostaje tekst z nowego numeru
    When sprawdzenie się kończy
    Then pierwsza odpowiedź mówi, że odpowiada system AI, i podaje werdykt głównego twierdzenia bez linku
    And każdy SMS odpowiedzi ma najwyżej 70 znaków w UCS-2

  Scenario: słowo USUN
    Given numer ma zapisane sprawdzenia
    When przychodzi SMS "USUN"
    Then zapisy dla skrótu z solą tego numeru są usunięte
