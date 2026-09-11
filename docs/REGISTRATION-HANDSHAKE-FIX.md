# Installed account connection handshake correction

September 11, 2026: owner testing of the upgraded Preservation target exposed
registration failing with EOF / unable to connect. Server startup and map import
had succeeded. Registration opened a fresh socket without the current composition
handshake, unlike configuration fetch and normal login. Both password-recovery
socket paths had the same omission.

All three now call the existing handshake before sending account packets.
Server validation and legacy disabled-composition behavior are unchanged.

Focused evidence:

- Current Base compilation succeeded.
- Real installed client New User registration created a fresh fixture account;
  a restarted client logged into it normally; both roles shut down cleanly.
- All ten socket branches (five paths with explicit/default endpoint selection)
  are checked for handshake-before-packet ordering.
- Existing executable six-field handshake acceptance/refusal test passed.

The GUI test was corrected to use the established Preservation button color
selector; failed selector attempts were rerun against the same compiled inputs.
No full suite was run. Password recovery has ordering coverage, not an end-to-end
password-reset acceptance claim. Fresh characters may legitimately enter the
appearance-confirmation screen after login.
