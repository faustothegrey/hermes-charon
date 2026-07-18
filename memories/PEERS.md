# Peer Network — Conosciuti da peer70 (orchestratore)
#
# Tutta la comunicazione tra peer avviene via API Hermes (:8642), NON via SSH.

## Peer conosciuti

| Nome    | IP / Host                          | OS                            | Ruolo           | API Key                                |
|---------|------------------------------------|-------------------------------|-----------------|----------------------------------------|
| peer70  | 192.168.178.70                     | Debian 11 bullseye (aarch64)  | **orchestratore** 🏆 | ~/.hermes/.env (API_SERVER_KEY)       |
| peer84  | 192.168.178.84                     | Ubuntu 22.04 (x86_64)         | peer            | ~/.hermes/.env (PEER84_API_KEY)        |
| peer128 | Faustos-MacBook-Pro-Home-3.fritz.box | macOS 26.5.1                | peer (Mac)      | ~/.hermes/.env (PEER128_API_KEY)       |
| peer60  | 192.168.178.60                     | Raspbian 9 stretch (armv7l)   | peer            | Offline                                 |

## Comunicazione
- **Protocollo:** API Hermes OpenAI-compatible su `:8642`
- **Endpoint chat:** `POST /v1/chat/completions` con `Authorization: Bearer <key>`
- **Modello:** `hermes-agent`
- **Niente SSH** per comunicazione tra peer

## Altri dispositivi sulla LAN

| IP               | Hostname                     | Note            |
|------------------|------------------------------|-----------------|
| 192.168.178.124  | Chromecast.fritz.box         | Chromecast      |
| 192.168.178.54   | *.fritz.box                  | Sconosciuto     |
| 192.168.178.64   | *.fritz.box                  | Sconosciuto     |

## Accesso SSH (solo per manutenzione)
- Tutti sulla subnet 192.168.178.0/24
- Stessa chiave `id_rsa` condivisa tra tutti i peer
- peer70: fausto@192.168.178.70
- peer84: root@192.168.178.84
- peer128: fausto@Faustos-MacBook-Pro-Home-3.fritz.box

## Monitoraggio
- peer70 esegue ping via API a tutti i peer ogni ora (cronjob Hermes)
- Stato salvato in ~/.hermes/peer-network/STATUS.md
