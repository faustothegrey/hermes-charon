#!/bin/bash
/home/fausto/.local/bin/himalaya send \
  --to "fausto.lelli@gmail.com" \
  --subject "Saluti da Hermes" \
  --body "Ciao Fausto, questo è un saluto di prova inviato da Hermes tramite Virgilio.it." 2>&1
echo "EXIT:$?"
