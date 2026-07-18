# Flusso distribuzione plugin HMP

## Regola d'Oro

**Niente SSH per interventi sui peer remoti.** Solo spiegare via HMP e lasciare che
il peer esegua da solo. SSH **solo** in casi critici (server down, recovery, emergenza).

I peer sono agenti autonomi, non terminali remoti.

## Il Flusso

```
1. Implementa/modifica su peer70          ← sorgente
2. Testa localmente su peer70
3. Bump versione in plugin.yaml
4. Spiega a UN peer via HMP cosa fare
5. Il peer si aggiorna da solo
6. Test bidirezionale con quel peer
7. Se OK → passa al peer successivo
8. Se KO → fix su peer70, ripeti dal punto 1
```

## Perché

- peer70 è la **source of truth** del plugin HMP
- Ogni peer è indipendente e sa auto-aggiornarsi
- L'errore va fixato **dalla parte che si è rotta**, non spostato sugli altri
- Deploy graduale (1 peer alla volta) → rilevi problemi prima di espandere

## Come preparare il messaggio di upgrade

Il messaggio HMP deve essere:

1. **Breve** (<500 byte). Messaggi lunghi saturano i peer lenti e rimangono in
   `working` senza risposta. Se serve spiegare tanto, dividi in 2-3 messaggi
   separati: primo di annuncio, secondo coi dettagli, terzo con verifica.

2. **Strutturato**:
   - `Ciao peerX, HMP plugin v0.NEW è pronto.`
   - Cosa cambia (1 riga)
   - Cosa fare (lista numerata: backup, modifiche, bump version, restart, test)
   - `Fammi sapere quando hai finito!`

3. **Azioni concrete**: backup, file da modificare, comandi da eseguire, test
   di verifica.

## Quando contattare i peer

- peer84: **solo fuori dalla finestra cooling** (11:00-17:00 e 02:00-03:00).
  Accensione alle 03:00.
- peer105: lento (30-60s per rispondere). Prevedere 2-3 minuti per messaggi
  normali. Messaggi lunghi (>500 byte) possono non arrivare mai.
- peer106: più reattivo, buon candidato per primo test.
- peer128: via .112. Raggiungibile via curl ma non da execute_code.
  Usare curl diretto + poll manuale.

## Cosa fare se il peer non risponde

Se il peer lascia il messaggio in `working` per >2 minuti:

1. Il peer ha lo stesso bug che stai fixando (messaggi bloccati quando l'agente
   è occupato). È un uovo-gallina: non può ricevere l'upgrade finché non è libero.
2. **Riprova più tardi**, quando l'agente è scarico (notte, weekend).
3. Invia messaggio molto breve (1 riga, <200 byte) — bypassa eventuali blocchi
   da messaggi lunghi.
4. Se il peer è irraggiungibile per giorni, solo allora valuta SSH per emergenza.

## Verifica post-upgrade

Dopo che il peer dice di aver completato:

```bash
# 1. Health check
curl -sf http://PEER_IP:18643/health

# 2. Test send: deve rispondere status=queued (non working)
curl -s -X POST http://PEER_IP:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d '{"hmp_version":"1.0","message_id":"test_$(date +%s%N)","from":"peer70","to":"peerX","type":"request","timeout":30,"payload":{"text":"Test post-upgrade"}}'

# 3. Poll per risposta
curl -s http://PEER_IP:18643/hmp/poll/{message_id}
```
