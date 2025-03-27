# april-bot-2025

## Projekt-outline
Vi gör en bot som svarar på folks meddelanden i MaMo. Botten ska svara med AI-genererade svar som har en gömd agenda. Förslag:
- Att maximera antalet badankor i världen
- Att alla användarmeddelanden ska förbättras så att de promotear något
- Att alla ska skriva snälla saker till fysiksektionens maskot
- Konsråttorna försöker ta över kons
- Kryptovalutor

## Plan
Vi skickar ett meddelande i fysiksektionen #general i mamo som säger något i stil med "FDevs presenterar sitt nya mamo-verktyg som förbättrar dina meddelanden!! Reagera med '🦆' för att vara med!"

Varje gång någon som har givit sitt samtycke skickar ett meddelande så svarar botten med ett AI-genererat svar med en gömd agenda. Eventuellt ska det också gå att fortsätta skriva med botten i tråden.

Det är viktigt att det finns begränsningar på antalet svar per användare, och antalet tokens per svar så att prestandan blir hyfsat bra.

## Mer detaljerat
- Någon postar ett meddelande
- Översätt meddelandet till engelska med hjälp av https://github.com/LibreTranslate/LibreTranslate lokalt
- Skicka in en prompt med meddelandet till ollama som körs lokalt
- Översätt tillbaka till svenska och skicka en reply till originalmeddelandet
