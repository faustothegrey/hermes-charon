#!/usr/bin/env python3
"""
dsi_reset.py — Reset del connettore DSI via DRM ioctl.

Cicla DPMS Off → On per forzare la reinizializzazione del bridge DSI.
Non richiede reboot. Eseguire con sudo.
"""
import ctypes
import ctypes.util
import os
import sys
import fcntl
import time

# Costanti DRM
DRM_IOCTL_BASE = ord('d')
DRM_IOWR = lambda n, size: (2 << 30) | (ctypes.sizeof(size) << 16) | (DRM_IOCTL_BASE << 8) | n
DRM_IOW  = lambda n, size: (1 << 30) | (ctypes.sizeof(size) << 16) | (DRM_IOCTL_BASE << 8) | n
DRM_IOR  = lambda n, size: (2 << 30) | (ctypes.sizeof(size) << 16) | (DRM_IOCTL_BASE << 8) | n
DRM_IO   = lambda n: (0) | (DRM_IOCTL_BASE << 8) | n

# DRM IOCTL numeri
DRM_IOCTL_VERSION       = DRM_IOWR(0x00, 8)  # placeholder
DRM_IOCTL_MODE_GETRESOURCES = DRM_IOWR(0xA0, 8)
DRM_IOCTL_MODE_GETCONNECTOR  = DRM_IOWR(0xA7, 8)
DRM_IOCTL_MODE_OBJ_SETPROPERTY = DRM_IOWR(0xB1, 8)

DRM_MODE_OBJECT_CONNECTOR = 0xc4c0c0c0

class drm_mode_get_connector(ctypes.Structure):
    _fields_ = [
        ('connector_id', ctypes.c_uint32),
        ('encoderm_id', ctypes.c_uint32),
        ('encoderm_id_ptr', ctypes.c_uint64),
        ('connection', ctypes.c_uint32),
        ('mm_width', ctypes.c_uint32),
        ('mm_height', ctypes.c_uint32),
        ('subpixel', ctypes.c_uint32),
        ('count_modes', ctypes.c_uint32),
        ('modes_ptr', ctypes.c_uint64),
        ('count_props', ctypes.c_uint32),
        ('props_ptr', ctypes.c_uint64),
        ('prop_values_ptr', ctypes.c_uint64),
        ('count_encoders', ctypes.c_uint32),
        ('encoders_ptr', ctypes.c_uint64),
    ]

class drm_mode_obj_set_property(ctypes.Structure):
    _fields_ = [
        ('value', ctypes.c_uint64),
        ('obj_id', ctypes.c_uint32),
        ('obj_type', ctypes.c_uint32),
        ('prop_id', ctypes.c_uint32),
        ('count_props', ctypes.c_uint32),  # padding
        ('reserved', ctypes.c_uint64),
    ]


def get_connector_props(fd, connector_id):
    """Get connector properties using a two-call approach."""
    # First call: get counts
    conn = drm_mode_get_connector(
        connector_id=connector_id,
        count_props=0,
        props_ptr=0,
        prop_values_ptr=0,
    )
    buf = ctypes.create_string_buffer(ctypes.sizeof(conn))
    ctypes.memmove(buf, ctypes.byref(conn), ctypes.sizeof(conn))
    
    try:
        fcntl.ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, buf, True)
    except Exception as e:
        print(f"  errore ioctl: {e}", file=sys.stderr)
        return None, None
    
    ctypes.memmove(ctypes.byref(conn), buf, ctypes.sizeof(conn))
    count_props = conn.count_props
    
    if count_props == 0:
        return [], []
    
    # Second call: get actual properties
    prop_ids = (ctypes.c_uint32 * count_props)()
    prop_values = (ctypes.c_uint64 * count_props)()
    
    conn2 = drm_mode_get_connector(
        connector_id=connector_id,
        count_props=count_props,
        props_ptr=ctypes.addressof(prop_ids),
        prop_values_ptr=ctypes.addressof(prop_values),
    )
    buf2 = ctypes.create_string_buffer(ctypes.sizeof(conn2))
    ctypes.memmove(buf2, ctypes.byref(conn2), ctypes.sizeof(conn2))
    
    try:
        fcntl.ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, buf2, True)
    except Exception as e:
        print(f"  errore ioctl (2): {e}", file=sys.stderr)
        return None, None
    
    return list(prop_ids), list(prop_values)


def get_property_name(fd, prop_id):
    """Get property name from ID."""
    # Try to read via sysfs: /sys/class/drm/card*/connector*/properties/
    for card_dir in os.listdir('/sys/class/drm/'):
        if not card_dir.startswith('card'):
            continue
        props_dir = f'/sys/class/drm/{card_dir}/properties/'
        if not os.path.isdir(props_dir):
            continue
        for pname in os.listdir(props_dir):
            pfile = f'{props_dir}{pname}/id'
            if os.path.exists(pfile):
                try:
                    with open(pfile) as f:
                        if int(f.read().strip()) == prop_id:
                            return pname
                except (ValueError, OSError):
                    pass
    return f"prop_{prop_id}"


def reset_dsi():
    """Main: cycle DPMS off/on on the DSI-1 connector."""
    # Find the DSI-1 connector on any card
    dsi_connector_id = None
    card_path = None
    
    for card_dir in sorted(os.listdir('/sys/class/drm/')):
        if not card_dir.startswith('card') or '-DSI-' not in card_dir:
            continue
        conn_path = f'/sys/class/drm/{card_dir}'
        connector_path = os.path.realpath(f'{conn_path}/device')
        card_base = os.path.basename(connector_path)  # e.g. "card1"
        card_path = f'/dev/dri/{card_base}'
        try:
            with open(f'{conn_path}/connector_id') as f:
                dsi_connector_id = int(f.read().strip())
                print(f"Trovato connettore DSI: {card_dir} -> ID {dsi_connector_id} su {card_path}")
                break
        except (OSError, ValueError):
            continue
    
    if dsi_connector_id is None or card_path is None:
        print("❌ Nessun connettore DSI trovato", file=sys.stderr)
        return False
    
    if not os.path.exists(card_path):
        print(f"❌ {card_path} non trovato", file=sys.stderr)
        return False
    
    # Open DRM device
    try:
        fd = os.open(card_path, os.O_RDWR | os.O_CLOEXEC)
    except OSError as e:
        print(f"❌ Impossibile aprire {card_path}: {e}", file=sys.stderr)
        return False
    
    try:
        # Get properties
        prop_ids, prop_values = get_connector_props(fd, dsi_connector_id)
        if prop_ids is None:
            print("❌ Impossibile leggere proprietà connettore", file=sys.stderr)
            return False
        
        print(f"  Proprietà trovate: {len(prop_ids)}")
        
        # Find DPMS property (typically ID 5, "DPMS")
        dpms_prop_id = None
        for pid in prop_ids:
            pname = get_property_name(fd, pid)
            if pname == "DPMS":
                dpms_prop_id = pid
                print(f"  ✅ Trovata proprietà DPMS: ID {pid}")
                break
        
        if dpms_prop_id is None:
            print("❌ Proprietà DPMS non trovata", file=sys.stderr)
            return False
        
        # Set DPMS to Off (3)
        print("  ⏹  DPMS → Off (3)")
        setprop = drm_mode_obj_set_property(
            value=3,
            obj_id=dsi_connector_id,
            obj_type=DRM_MODE_OBJECT_CONNECTOR,
            prop_id=dpms_prop_id,
        )
        buf = ctypes.create_string_buffer(ctypes.sizeof(setprop))
        ctypes.memmove(buf, ctypes.byref(setprop), ctypes.sizeof(setprop))
        try:
            fcntl.ioctl(fd, DRM_IOCTL_MODE_OBJ_SETPROPERTY, buf, True)
            print("  ✅ DPMS Off impostato")
        except Exception as e:
            print(f"  ⚠️  DPMS Off fallito: {e}", file=sys.stderr)
            # Continua comunque
        
        time.sleep(2)
        
        # Set DPMS back to On (0)
        print("  ▶️  DPMS → On (0)")
        setprop.value = 0
        buf = ctypes.create_string_buffer(ctypes.sizeof(setprop))
        ctypes.memmove(buf, ctypes.byref(setprop), ctypes.sizeof(setprop))
        try:
            fcntl.ioctl(fd, DRM_IOCTL_MODE_OBJ_SETPROPERTY, buf, True)
            print("  ✅ DPMS On impostato")
        except Exception as e:
            print(f"  ⚠️  DPMS On fallito: {e}", file=sys.stderr)
        
        # FBIOBLANK UNBLANK
        try:
            fb = os.open('/dev/fb0', os.O_RDWR)
            fcntl.ioctl(fb, 0x4611, 0)  # FB_BLANK_UNBLANK
            os.close(fb)
            print("  ✅ UNBLANK effettuato")
        except Exception as e:
            print(f"  ⚠️  UNBLANK fallito: {e}", file=sys.stderr)
        
        # Backlight on
        try:
            for d in os.listdir('/sys/class/backlight'):
                with open(f'/sys/class/backlight/{d}/bl_power', 'w') as f:
                    f.write('0')
                print(f"  ✅ Backlight {d} acceso")
        except Exception as e:
            print(f"  ⚠️  Backlight: {e}", file=sys.stderr)
        
        print("\n✅ Reset DSI completato. Il display dovrebbe funzionare.")
        return True
    
    finally:
        os.close(fd)


if __name__ == "__main__":
    success = reset_dsi()
    sys.exit(0 if success else 1)
