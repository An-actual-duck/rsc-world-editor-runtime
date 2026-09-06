# Current Base public definition snapshot

These data files are provider-owned public definition inputs from the
reviewed public Git tree in `provenance.json` and `gameplay-provenance.json`. No reference runtime is built or
executed. JSON is byte-identical; XML only normalizes CRLF to LF and supplies a
final newline. The integrity test reconstructs and hashes the original bytes,
so that normalization cannot conceal a definition change.

The historical public registries include 1,593 items (1,290 base plus 303
unconditionally appended stock Custom records), 836 NPCs (794 plus 42), 1,296
scenery definitions, 214 boundaries, and 25 tiles. Here “Custom” is a historical
filename, not permission to enable owner-specific gameplay or Advanced modules.
Items use explicit IDs; NPCs and XML registries use ordered indices.

The packaged-runtime probes compare actual server/client item, NPC, scenery,
boundary, tile, prayer and spell fields, exact spell rune maps, registry bounds,
and all 1,593 item sprite selections against these inputs. Server-only gameplay
fields are not asserted on client classes that do not represent them. The stock
sprite archive has a closed namespace inventory and independent source hash;
its historical Custom filename does not enable Advanced gameplay flags.
All 21 selected crafting/resource/teleport extra-definition collections are
compared recursively against their actual loaded fields, keys and end bounds.
Authored project sprite selections retain priority over the stock fallback.

The gathering probe seeds real loaded inventory objects without a login or
database session. It exercises plugin tool selectors, all eight public axe
curves, mining chance boundaries, and resource respawn timing. It does not claim
an end-to-end live gathering session, full skill parity or candidate readiness.
The magic probe uses a registered in-memory player with real inventory and
bank containers (no socket or database opened). It proves matching staff rune
replacement and other rune consumption, four orb input/output transformations
and XP/timer effects, and three god-cape stone rewards/ownership/progression.
The pure unselected-composition control retains the generic spell and axe
dispatch; it is not a full Advanced launch test.

The original definition-only slice did not establish combat parity. The separate
hash-bound `combat-policy.json` now selects classic equipment-field sums,
Attack/Defense/Strength hit rolls and prayers, bow aim versus ammunition power,
public spell powers/failure, and single-target impacts without owner armor
mitigation, elemental damage procs or lifesteal. Recoil uses its public
40-point default budget; life activates only while living at most 10% Hits,
within the public wilderness limit, and always shatters. The matching prayer
controls use the 14 public definitions, required levels and current points,
not owner reservation costs. Generic and Advanced dispatch remains independent.

Packaged headless probes exercise actual equipment reads, formula dispatch,
projectile and melee impacts through the Base reciprocal combat entrypoint,
prayer/equipment packets and client decoding, prayer drain, state-changing rings,
and stock poisoned-ammunition dispatch with its 32-tick cadence and 2-power
decay. Reciprocal cleanup detaches the exact shared event before resetting
players, avoiding recursive combat cleanup. These are bounded contract proofs,
not a claim of every plugin, NPC attack profile, death/inventory interaction,
or complete gameplay parity.
The original `effective-policy.json` records the older definition-only scope;
the separately bound skill/combat policies and tests define these later slices.
Genuine imported-map acceptance has its own independent verification document.

The separately hash-bound `skill-policy.json` records the public 18-skill
numeric identity and XP/style oracle from exact historical source blobs. Bound
Base keeps Attack, Defense, Strength and Firemaking current/max/XP independent;
the shared `Melee` code alias refers only to Attack, never a migrated combined
stat. Base's full stats payload contains exactly 18 current bytes, 18 maximum
bytes, 18 fixed-point XP integers, then quest points. The matching client keeps
all 18 skills visible in numeric order and sends classic style values 0–3.

Headless packaged probes cover constructor/load/setter paths, real private
SQLite save/reopen/load with boosted and drained current values, equipment
eligibility, actual NPC weakening, NPC partial-damage and PvP death XP dispatch,
public configured XP rates, magic cast versus kill XP, outbound server packets,
and client packet consumers/control dispatch. The PvP victim is deliberately
not logged in, so its existing death-world side-effect guard remains active.
These are not GUI, player death/inventory, complete combat balancing, hiscores,
or full imported-map acceptance claims. Generic/unselected Firemaking hiding,
20-skill packet shape and combined-melee behavior remain covered controls.
