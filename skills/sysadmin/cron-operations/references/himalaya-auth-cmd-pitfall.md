# Himalaya `auth.cmd` Pitfall

## Problem

Setting `auth.cmd` to a bare file path (e.g. `auth.cmd = "/home/user/password"`)
causes himalaya to try **executing** that path as a binary/script. A plain text
file without the executable bit fails with:

```
cannot get secret from command
command /path/to/password returned non-zero exit status code 126: Permission denied
```

## Fix

Use a command that reads and outputs the password, not the path alone:

```toml
# WRONG — tries to execute the file as a binary
backend.auth.cmd = "/home/fausto/.config/himalaya/virgilio.pass"

# RIGHT — pipes the file contents
backend.auth.cmd = "cat /home/fausto/.config/himalaya/virgilio.pass"
```

## Alternative

Keep the file path but make it executable and ensure it outputs the password
to stdout:

```bash
chmod +x ~/.config/himalaya/virgilio.pass
# The file must output the password line, e.g.:
echo -n "password" > ~/.config/himalaya/virgilio.pass
```

## Verification

```bash
# This should print the password, not an error
cat ~/.config/himalaya/virgilio.pass

# Test sending a minimal message
echo -e "From: you@example.com\nTo: you@example.com\nSubject: test\n\ntest" | himalaya message send
```
