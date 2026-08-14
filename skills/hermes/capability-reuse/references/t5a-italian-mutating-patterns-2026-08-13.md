# T5a — Mutating-effect classification must cover the operator language

**Data:** 2026-08-13 · **Skill:** capability-reuse v2.4.17 · **File:** `plugin/retriever.py`

## Il problema

`_extract_request_effect()` classificava solo pattern inglesi. Sulla rete di
peer di Fausto (operatore italofono), prompt compositi mutating come:

- `controlla health e se giu riavvialo`
- `se non healthy riavvia peer58`
- `controlla la salute di peer58 e se non funziona riavvialo`

venivano classificati `read_only` (o `""`) invece di `mutating`. Conseguenza:
un composito mutating poteva superare il canary read-only e aprire active
decision pericolosa — esattamente la classe di hard-negative che la 2.4.16
richiedeva di coprire.

## Il fix (applicato e validato 10/10)

### 1. `mutating_terms` — aggiungere le forme verbali italiane

```python
"riavvia", "riavvialo", "riavviali", "ferma", "fermalo", "arresta",
"disattiva", "attiva", "aggiorna", "riconfigura", "ricarica", "riavvio",
"spegnilo", "accendilo", "termina", "uccidi", "sospendi", "riprendi",
"cambia", "modifica", "sostituisci", "installa", "rimuovi", "elimina",
"invia", "scrivi", "crea", "cancella",
```

### 2. `composite_mutating_patterns` — condizionali italiani

```python
# "e se giu riavvialo", "se non healthy riavvia"
r"\b(?:e\s+)?se\s+(?:non\s+)?(?:healthy|ok|su|attivo|attiva|funzionante|giu|giù|down|offline)\b[^.?!]{0,60}\b(?:riavvia|riavvialo|ferma|fermalo|arresta|disattiva|spegni|accendi|termina|uccidi|sospendi|riprendi|aggiorna|riconfigura)\b",
# "controlla ... e poi riavvialo"
r"\b(?:controlla|check|verifica|ping)\b[^.?!]{0,80}\b(?:e|then|poi)\b[^.?!]{0,80}\b(?:riavvia|riavvialo|ferma|fermalo|arresta|disattiva|spegni|accendi|termina|sospendi|riprendi|aggiorna|riconfigura)\b",
```

### 3. `read_terms` — termini read-only italiani

```python
"mostra", "stato", "verifica", "controlla", "salute", "elenco", "lista",
```

### 4. `non_operational_patterns` — intenti informativi italiani

```python
r"\bspiega\b", r"\bdescrivi\b", r"\bcos'[èe]\b", r"\bche\s+cos'[èe]\b",
r"\bcome\s+funziona\b", r"\bdimmi\s+come\b", r"\bcosa\s+[èe]\b",
```

## Come testare

Importare dal root della skill (non da dentro `plugin/`) per soddisfare gli
import relativi:

```bash
cd ~/.hermes/skills/hermes/capability-reuse
python3 -c "
import sys; sys.path.insert(0, '.')
from plugin.retriever import _extract_request_effect
print(_extract_request_effect('se non healthy riavvia peer58'))  # → mutating
"
```

## Verdetto validazione T5a

10/10 casi PASS dopo il fix:
- mutating: `check health and restart if unhealthy`, `controlla health e se giu riavvialo`,
  `se non healthy riavvia peer58`, `controlla la salute ... riavvialo`, `deploy the new version`
- read_only: `mostra lo stato di peer58`, `verifica lo stato del gateway`, `ping peer58`,
  `get hmp health for peer58`
- non_operational: `spiega come funziona il healthcheck`

## Lezione duratura

Quando si scrive/aggiorna un classificatore di intenti per una rete di
operatori, i termini mutating/read/non-operational vanno allineati alla
**lingua degli operatori**, non solo a quella del codice. Un hard-negative
mancante per lingua = buco di sicurezza silenzioso.
