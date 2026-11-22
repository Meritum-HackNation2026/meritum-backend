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
    Then bot podmienia odpowiedź na jedną wiadomość: z informacją, że odpowiada system AI, i osadzeniem z werdyktem, najważniejszym cytatem ze źródłem i datą oraz siłą podstawy dla każdego twierdzenia
    And pod wiadomością jest przycisk-link "Pełna karta" do wyniku, a w treści nie ma surowego adresu

  Scenario: wynik widoczny dla kanału
    Given użytkownik wywołuje /sprawdz z opcją publiczne: True
    When bot dostaje wynik sprawdzenia z kanałem "discord"
    Then odpowiedź jest widoczna dla wszystkich na kanale
    And bez tej opcji odpowiedź zostaje efemeryczna

  Scenario: długi wynik
    Given wynik nie mieści się w limitach Discorda
    When bot buduje odpowiedź
    Then osadzenie ma razem najwyżej 6000 znaków, a bot skraca cytaty, nie twierdzenia

  Scenario: odpowiedź po 3 sekundach
    Given sprawdzenie trwa dłużej niż 3 s
    When Discord czeka na odpowiedź na interakcję
    Then bot odpowiada odroczoną odpowiedzią, a wynik wstawia w jej miejsce

  Scenario: wiadomość z RCS/MMS z tekstem jest sprawdzana jak SMS
    Given bramka wysyła zdarzenie mms:downloaded z częścią tekstową
    When webhook je odbiera i podpis się zgadza
    Then backend sprawdza tekst tak jak przy sms:received
    And odpowiada SMS-em z werdyktem

  Scenario: MMS bez tekstu
    Given mms:downloaded bez części tekstowej (same załączniki)
    When webhook je odbiera i podpis się zgadza
    Then backend potwierdza odbiór (2xx) i nic nie sprawdza

  Scenario: wynik z pamięci niesie znacznik AI modelu, który napisał uzasadnienie
    Given sprawdzenie tekstu "Czy we Włoszech ostatnio odbywał się strajk generalny?" z formularza zakończyło się 10 minut temu
    When ten sam tekst z innymi spacjami i cudzysłowami przychodzi z wtyczki
    Then oba wyniki mają ten sam znacznik AI z dostawcą i modelem, który napisał uzasadnienie

  Scenario: wiadomość prywatna
    Given użytkownik pisze do bota wiadomość prywatną z tekstem do sprawdzenia
    When proces Gateway ją odbiera
    Then woła to samo sprawdzenie co POST /api/v1/checks z channel "discord" i odpowiada w tej rozmowie wiadomościami z backend/007

  Scenario: wzmianka bez intencji MESSAGE_CONTENT
    Given bot jest na serwerze bez uprzywilejowanej intencji MESSAGE_CONTENT
    When ktoś wspomina bota z linkiem do artykułu
    Then bot odpowiada w wątku wynikiem sprawdzenia linku

  Scenario: zerwane połączenie
    Given Gateway zrywa połączenie
    When proces wznawia sesję
    Then nie wysyła drugi raz odpowiedzi na wiadomość, na którą już odpowiedział

  Scenario: wiadomość głosowa w wiadomości prywatnej
    Given użytkownik wysyła botowi wiadomość głosową OGG trwającą 40 s
    When bot ją odbiera
    Then pobiera załącznik od razu i zleca sprawdzenie z audio_id
    And odpowiedź zawiera transkrypcję z informacją, że powstała automatycznie i może mieć błędy

  Scenario: nieobsługiwany format
    Given załącznik audio w formacie, którego transkrypcja nie obsługuje
    When bot go odbiera
    Then odpowiada stanem "out_of_scope" z informacją, co można wysłać zamiast tego

  Scenario: narzędzie sprawdzania w serwerze MCP
    Given klient MCP połączony przez Streamable HTTP z /mcp
    When woła narzędzie sprawdzania z tekstem "Czy od wczoraj w Pcimiu bilety autobusowe można kupić tylko przez aplikację?"
    Then dostaje CheckResult z werdyktem, cytatami z linkami, siłą i informacją o AI
    And CheckRecord ma session_id równy skrótowi z solą identyfikatora klienta MCP

  Scenario: MCP zwraca stan niebędący werdyktem
    Given klient MCP połączony przez Streamable HTTP z /mcp
    And sprawdzenie kończy się stanem "technical_failure"
    When woła narzędzie sprawdzania z tekstem "Czy od wczoraj w Pcimiu bilety autobusowe można kupić tylko przez aplikację?"
    Then wynik ma stan "technical_failure" i kod awarii, bez werdyktu
