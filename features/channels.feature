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

  Scenario: to samo wejście z dwóch kanałów (scenariusz G)
    Given sprawdzenie tekstu "Czy Wrocław był jedynym miastem w Polsce, w którym 65-latkowie jeździli komunikacją miejską za darmo?" z formularza zakończyło się 10 minut temu
    When ten sam tekst z innymi spacjami i cudzysłowami przychodzi z wtyczki
    Then część merytoryczna CheckResult jest identyczna jako JSON, z tym samym werdyktem i tą samą publikacją
    And workflow sprawdzania nie startuje drugi raz, a CheckRecord.cache_hit jest true

  Scenario: problem techniczny nie trafia do pamięci
    Given sprawdzenie zakończyło się stanem "technical_failure"
    When to samo wejście przychodzi ponownie
    Then startuje nowy workflow

  Scenario: wynik z pamięci nie zdradza cudzej sprawy
    Given wynik w pamięci pochodzi ze sprawdzenia, które utworzyło sprawę "#S-7"
    When inna sesja dostaje ten wynik z pamięci
    Then CheckResult.escalation jest policzone dla tej sesji i nie zawiera cudzego stanu ani numeru "#S-7"
    And powtórzone pytanie bez odpowiedzi zwiększa licznik powtórzeń tak samo jak bez pamięci

  Scenario: pierwsze użycie komendy (scenariusz G)
    Given użytkownik pierwszy raz wywołuje /sprawdz z tekstem "Czy Wrocław był jedynym miastem w Polsce, w którym 65-latkowie jeździli komunikacją miejską za darmo?"
    When bot dostaje wynik sprawdzenia z kanałem "discord"
    Then pierwsza wiadomość mówi, że odpowiada system AI, i podsumowuje werdykt każdego twierdzenia z linkiem do pełnej karty wyniku
    And potem bot wysyła po jednej wiadomości na twierdzenie: werdykt, jeden najważniejszy cytat albo ocenę fact-checkera ze źródłem i siłę

  Scenario: długi cytat
    Given odpowiedź dla twierdzenia przekracza 2000 znaków
    When bot dzieli odpowiedź na wiadomości
    Then żadna wiadomość nie ma więcej niż 2000 znaków treści, osadzenia mają razem najwyżej 6000 znaków, a podział nie przecina cytatu

  Scenario: odpowiedź po 3 sekundach
    Given sprawdzenie trwa dłużej niż 3 s
    When Discord czeka na odpowiedź na interakcję
    Then bot odpowiada odroczoną odpowiedzią, a wynik wysyła jako wiadomość uzupełniającą

  Scenario: wiadomość z RCS/MMS z tekstem jest sprawdzana jak SMS
    Given bramka wysyła zdarzenie mms:downloaded z częścią tekstową
    When webhook je odbiera i podpis się zgadza
    Then backend sprawdza tekst tak jak przy sms:received
    And odpowiada SMS-em z werdyktem

  Scenario: MMS bez tekstu
    Given mms:downloaded bez części tekstowej (same załączniki)
    When webhook je odbiera i podpis się zgadza
    Then backend potwierdza odbiór (2xx) i nic nie sprawdza
