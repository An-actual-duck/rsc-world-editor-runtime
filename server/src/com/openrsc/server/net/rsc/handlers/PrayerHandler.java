package com.openrsc.server.net.rsc.handlers;

import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.model.entity.player.PrayerCatalog;
import com.openrsc.server.model.entity.player.Prayers;
import com.openrsc.server.net.rsc.PayloadProcessor;
import com.openrsc.server.net.rsc.enums.OpcodeIn;
import com.openrsc.server.net.rsc.struct.incoming.PrayerStruct;

public class PrayerHandler implements PayloadProcessor<PrayerStruct, OpcodeIn> {

	public void process(final PrayerStruct payload, final Player player) throws Exception {
		if (com.openrsc.server.CurrentBaseCombatContract.selected()) { processPublicPrayer(payload, player); return; }
		final int prayerID = payload.prayerID;

		if (prayerID < 0 || prayerID >= PrayerCatalog.PRAYERS_PER_BOOK) {
			player.setSuspiciousPlayer(true,
				String.format("prayerID < 0 or prayerID >= %d", PrayerCatalog.PRAYERS_PER_BOOK));
			return;
		}

		if (player.getConfig().LACKS_PRAYERS) {
			player.message("World does not feature prayers!");
			return;
		}

		if (player.getDuel().isDuelActive() && player.getDuel().getDuelSetting(2)) {
			player.message("Prayers cannot be used during this duel!");
			return;
		}

		final Prayers prayers = player.getPrayers();
		final OpcodeIn opcode = payload.getOpcode();

		if (opcode == OpcodeIn.PRAYER_ACTIVATED) {
			if (prayers.isPrayerActivated(prayerID)) {
				return;
			}
			if (!prayers.canActivate(prayerID)) {
				final String blockMessage = prayers.getActivationBlockMessage(prayerID);
				if (blockMessage != null) {
					player.message(blockMessage);
				}
				return;
			}
			prayers.setPrayer(prayerID, true);
		} else if (opcode == OpcodeIn.PRAYER_DEACTIVATED) {
			if (prayers.isPrayerActivated(prayerID)) {
				prayers.setPrayer(prayerID, false);
			}
		}
	}

	private void processPublicPrayer(final PrayerStruct payload, final Player player) {
		int id = payload.prayerID;
		if (id < 0 || id > Prayers.PROTECT_FROM_MISSILES) {
			player.setSuspiciousPlayer(true, "public prayer ID outside 0..13"); return;
		}
		if (player.getConfig().LACKS_PRAYERS || (player.getDuel().isDuelActive() && player.getDuel().getDuelSetting(2))) return;
		if (id == Prayers.PROTECT_ITEMS && player.isIronMan(com.openrsc.server.constants.IronmanMode.Ultimate.id())) return;
		Prayers prayers = player.getPrayers();
		if (payload.getOpcode() == OpcodeIn.PRAYER_DEACTIVATED) { prayers.setPrayer(id, false); return; }
		if (payload.getOpcode() != OpcodeIn.PRAYER_ACTIVATED || prayers.isPrayerActivated(id)) return;
		if (!prayers.canActivate(id)) { player.message(prayers.getActivationBlockMessage(id)); return; }
		for (int[] family : new int[][]{{0,3,9},{1,4,10},{2,5,11}}) {
			for (int member : family) if (member == id) {
				for (int other : family) if (other != id) prayers.setPrayer(other, false, false);
				break;
			}
		}
		prayers.setPrayer(id, true);
	}
}
