# Session-Specific FritzBox Discoveries (Jul 2026)

## Connection Details
- **Model**: FRITZ!Box 7490 (Fritz!OS 07.62)
- **IP**: 192.168.178.1
- **Provider**: WIND Tre
- **IPv4**: 176.206.11.86
- **DNS**: 151.5.216.150, 151.5.216.15
- **DynDNS**: settembre2.homepc.it
- **DSL**: 14836/10798 kbps (down/up), stato: connessa
- **Energia**: ~55 W

## Known Working API Pages
- `page=overview` — full status (DSL, Internet, WLAN, devices, comfort)
- `page=chan` — 5 GHz channel scan + airtime data

## AirTime Data Format
Compressed format from `data.5ghz.airtimedata`:
```
<timestamp>,<slotCount>,<slotDurationMs>,<ch>:<val>,<ch>:<val>,...
```
Where `val` = how many scan slots detected that channel as busy.

## TR-064 Status
SOAP `/upnp/control/` endpoints on port 443 → 404