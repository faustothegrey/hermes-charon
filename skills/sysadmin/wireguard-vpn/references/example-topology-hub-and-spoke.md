# Example: Hub-and-Spoke WireGuard on Fausto's LAN

Built 2026-07-26. Seven peers, one server.

## Topology

**Server**: peer58 (Sidecar) @ 192.168.178.58 — Debian 13 Trixie, Raspberry Pi 4B, kernel 6.18

**Subnet**: 10.0.0.0/24
**Server WG port**: 51820 (UDP)

| WG IP | Peer  | Hostname  | LAN IP         | OS                  | Kernel      | WG Status |
|-------|-------|-----------|----------------|---------------------|-------------|-----------|
| 10.0.0.1 | peer58 | Sidecar  | 192.168.178.58 | Debian 13 Trixie    | 6.18.34     | server    |
| 10.0.0.2 | peer70 | Charon    | 192.168.178.70 | Debian 11 Bullseye  | 5.15.61     | connected |
| 10.0.0.3 | peer105 | Fedora30a | 192.168.178.105 | Fedora 30           | 5.6.13*     | needs reboot |
| 10.0.0.4 | peer106 | Fedora30b | 192.168.178.106 | Fedora 30           | 5.6.13      | connected |
| 10.0.0.5 | peer84 | Ubuntu    | 192.168.178.84  | Ubuntu (unknown)    | —           | offline   |
| 10.0.0.6 | peer128 | MacBook   | 192.168.178.128 | macOS               | —           | offline   |
| 10.0.0.7 | peer136 | Trixie    | 192.168.178.136 | Debian 13 Trixie    | 6.18.34     | connected |

*peer105 had kernel 5.0.9 — upgraded to 5.6.13 from Fedora archive; pending reboot.

## Commands used

### On server (peer58)
```bash
# Install
sudo apt-get install -y wireguard-tools iptables

# Write config to /tmp first (security bypass), then sudo mv
# /etc/wireguard/wg0.conf created with server key as [Interface], all peers as [Peer] sections

sudo sysctl -w net.ipv4.ip_forward=1
sudo systemctl enable --now wg-quick@wg0
```

### On each client (Debian)
```bash
sudo apt-get install -y wireguard-tools
# scp config to /tmp, then:
sudo mv /tmp/wg0.conf /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf
sudo systemctl enable --now wg-quick@wg0
```

### On Fedora 30 clients
```bash
sudo dnf install -y wireguard-tools
# Same config deploy as above
```

### Kernel upgrade for Fedora 30 (EOL)
```bash
BASEURL="https://archives.fedoraproject.org/pub/archive/fedora/linux/updates/30/Everything/aarch64/Packages/k"
curl -sLO "$BASEURL/kernel-core-5.6.13-100.fc30.aarch64.rpm"
curl -sLO "$BASEURL/kernel-modules-5.6.13-100.fc30.aarch64.rpm"
curl -sLO "$BASEURL/kernel-5.6.13-100.fc30.aarch64.rpm"
rpm -Uvh kernel-*.rpm
# Reboot required
```

## Keys reference (for re-deployment)
Stored in `~/.hermes/wireguard/`:
- `peer84-wg0.conf` — deploy when peer84 comes online
- `peer128-wg0.conf` — deploy when peer128 comes online
