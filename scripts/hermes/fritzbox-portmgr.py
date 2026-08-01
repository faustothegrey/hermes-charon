#!/usr/bin/env python3
"""
fritzbox-portmgr.py — Gestione port forwarding FritzBox via TR-064

Utilizzo:
  python3 fritzbox-portmgr.py list                     # elenca tutte le regole
  python3 fritzbox-portmgr.py add <porta> <IP> [TCP|UDP] [nome]  # aggiunge regola
  python3 fritzbox-portmgr.py del <porta> [TCP|UDP]     # elimina regola
  python3 fritzbox-portmgr.py info                     # info sul router

Default: porta esterna = interna, protocollo = TCP, nome = "Hermes:<porta>"
"""
import sys
import os
from fritzconnection import FritzConnection

FRITZ_IP = os.getenv("FRITZ_IP", "192.168.178.1")
FRITZ_USER = os.getenv("FRITZ_USER", "fausto")
FRITZ_PASSWORD = os.getenv("FRITZ_PASSWORD", "")

def get_fc():
    return FritzConnection(address=FRITZ_IP, user=FRITZ_USER, password=FRITZ_PASSWORD)

def cmd_list():
    fc = get_fc()
    print(f"{'#':<3} {'Descrizione':<35} {'Esterno':<20} {'Interno':<20} {'Stato':<8}")
    print("-" * 90)
    i = 0
    while True:
        try:
            e = fc.call_action("WANIPConn1", "GetGenericPortMappingEntry", NewPortMappingIndex=i)
            desc = e['NewPortMappingDescription'][:33]
            ext = f":{e['NewExternalPort']}/{e['NewProtocol']}"
            int_ = f"{e['NewInternalClient']}:{e['NewInternalPort']}"
            stato = "✅" if e['NewEnabled'] else "⛔"
            print(f"{i:<3} {desc:<35} {ext:<20} {int_:<20} {stato:<8}")
            i += 1
        except Exception:
            break
    print(f"\nTotale: {i} regole")

def cmd_add(port, internal_ip, protocol="TCP", description=None):
    fc = get_fc()
    if description is None:
        description = f"Hermes:{port}"
    try:
        fc.call_action("WANIPConn1", "AddPortMapping",
            NewRemoteHost="",
            NewExternalPort=int(port),
            NewProtocol=protocol.upper(),
            NewInternalPort=int(port),
            NewInternalClient=internal_ip,
            NewEnabled=True,
            NewPortMappingDescription=description,
            NewLeaseDuration=0)
        print(f"✅ Regola aggiunta: {port}/{protocol.upper()} → {internal_ip}:{port} ({description})")
    except Exception as e:
        print(f"❌ Errore: {e}")

def cmd_del(port, protocol="TCP"):
    fc = get_fc()
    try:
        fc.call_action("WANIPConn1", "DeletePortMapping",
            NewRemoteHost="",
            NewExternalPort=int(port),
            NewProtocol=protocol.upper())
        print(f"✅ Regola eliminata: {port}/{protocol.upper()}")
    except Exception as e:
        print(f"❌ Errore: {e}")

def cmd_info():
    fc = get_fc()
    info = fc.call_action("WANIPConn1", "GetExternalIPAddress")
    status = fc.call_action("WANIPConn1", "GetStatusInfo")
    print(f"Modello:     {fc.modelname}")
    print(f"IP Esterno:  {info['NewExternalIPAddress']}")
    print(f"Stato:       {status['NewConnectionStatus']}")
    print(f"Uptime:      {status.get('NewUptime', 'N/A')}s")
    try:
        host = next(iter(getattr(fc, '_hosts', [])))
    except:
        pass
    # Mostra peer conosciuti
    print(f"\nHost LAN noti:")
    print(f"  peer70  (questo)  192.168.178.70")
    print(f"  peer84            192.168.178.84")
    print(f"  peer128           Faustos-MacBook-Pro-Home-3.fritz.box")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list()
    elif cmd == "add" and len(sys.argv) >= 4:
        cmd_add(sys.argv[2], sys.argv[3],
                sys.argv[4] if len(sys.argv) > 4 else "TCP",
                sys.argv[5] if len(sys.argv) > 5 else None)
    elif cmd == "del" and len(sys.argv) >= 3:
        cmd_del(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "TCP")
    elif cmd == "info":
        cmd_info()
    else:
        print(f"❌ Comando sconosciuto o argomenti mancanti\n")
        print(__doc__)
