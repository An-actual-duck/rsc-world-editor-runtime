import com.openrsc.server.*;
import com.openrsc.server.constants.*;
import com.openrsc.server.event.rsc.impl.combat.CombatFormula;
import com.openrsc.server.external.SpellDef;
import com.openrsc.server.model.Point;
import com.openrsc.server.model.container.*;
import com.openrsc.server.model.entity.Mob;
import com.openrsc.server.model.entity.EntityType;
import com.openrsc.server.model.entity.player.*;
import com.openrsc.server.model.entity.npc.Npc;
import com.openrsc.server.net.rsc.handlers.SpellHandler;
import com.openrsc.server.util.rsc.DataConversions;
import org.json.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;

/** Actual packaged equipment and combat formulas against source-bound public vectors. */
public final class PublicCombatProbe {
  static Server server;
  static Player player;
  static void check(boolean yes,String why) { if(!yes)throw new AssertionError(why); }
  static Field field(Class<?> type,String name) throws Exception { Field f=type.getDeclaredField(name);f.setAccessible(true);return f; }
  static Object invoke(Class<?> type,Object receiver,String name,Class<?>[] types,Object...args)throws Exception {
    Method method=type.getDeclaredMethod(name,types);method.setAccessible(true);return method.invoke(receiver,args);
  }
  static double formula(String name,Mob mob)throws Exception { return ((Number)invoke(CombatFormula.class,null,name,new Class<?>[]{Mob.class},mob)).doubleValue(); }
  static void clear()throws Exception {
    player.getCarriedItems().getInventory().getItems().clear();
    Arrays.fill((Item[])field(Equipment.class,"list").get(player.getCarriedItems().getEquipment()),null);
  }
  static void wear(int id)throws Exception {
    Item item=new Item(id);
    if(server.getConfig().WANT_EQUIPMENT_TAB) {
      ((Item[])field(Equipment.class,"list").get(player.getCarriedItems().getEquipment()))[item.getDef(server.getWorld()).getWieldPosition()]=item;
      item.getItemStatus().setWielded(true);
    } else {
      check(player.getCarriedItems().getInventory().add(item,false),"fixture worn item "+id);
      for(Item added:player.getCarriedItems().getInventory().getItems())if(added.getCatalogId()==id)added.getItemStatus().setWielded(true);
    }
  }
  static void prayerAndEffects(Npc npc)throws Exception {
    clear();player.getPrayers().resetPrayers();
    check(player.getPrayers().getActivePrayers().length==14,"actual public prayer packet extent");
    com.openrsc.server.net.rsc.handlers.PrayerHandler handler=new com.openrsc.server.net.rsc.handlers.PrayerHandler();
    com.openrsc.server.net.rsc.struct.incoming.PrayerStruct payload=new com.openrsc.server.net.rsc.struct.incoming.PrayerStruct();
    payload.setOpcode(com.openrsc.server.net.rsc.enums.OpcodeIn.PRAYER_ACTIVATED);
    player.getSkills().setTemporaryLevelAndMaxStat(5,1,99,false);
    for(int id:new int[]{0,3,9,1,4,10,2,5,11,12,13}) {payload.prayerID=id;handler.process(payload,player);check(player.getPrayers().isPrayerActivated(id),"actual public prayer activation "+id);}
    for(int id:new int[]{0,3,1,4,2,5})check(!player.getPrayers().isPrayerActivated(id),"exclusive prayer family "+id);
    for(int id:new int[]{9,10,11,12,13})check(player.getPrayers().isPrayerActivated(id),"independent classic prayers "+id);
    check(player.getPrayers().getAllocatedPoints()==0,"no reservation");
    player.getPrayers().resetPrayers();player.getSkills().setTemporaryLevelAndMaxStat(5,99,1,false);
    payload.prayerID=13;handler.process(payload,player);check(!player.getPrayers().isPrayerActivated(13),"required max not boosted current");
    player.getSkills().setTemporaryLevelAndMaxStat(5,0,99,false);payload.prayerID=0;handler.process(payload,player);
    check(!player.getPrayers().isPrayerActivated(0),"empty prayer refusal");
    player.getSkills().setTemporaryLevelAndMaxStat(5,10,99,false);payload.prayerID=0;handler.process(payload,player);
    player.setPrayerStatePoints(1200);
    int drain=(int)Math.ceil(server.getEntityHandler().getPrayerDef(0).getDrainRate()*120/300.0);
    new com.openrsc.server.event.rsc.impl.PrayerDrainEvent(server.getWorld(),player).run();
    check(player.getPrayerStatePoints()==1200-drain,"actual classic prayer drain");
    player.setPrayerStatePoints(1);new com.openrsc.server.event.rsc.impl.PrayerDrainEvent(server.getWorld(),player).run();
    check(player.getSkills().getLevel(5)==0&&!player.getPrayers().isPrayerActivated(0),"drain exhaustion deactivates");
    player.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);npc.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);
    // Execute the real impact path with owner elemental proc fields deliberately populated.
    new com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent(server.getWorld(),npc,player,17,1,false,100,100,100,100).action();
    check(player.getSkills().getLevel(3)==82,"actual projectile damage without owner mitigation");
    check(npc.getSkills().getLevel(3)==99,"no projectile life steal");
    com.openrsc.server.event.rsc.impl.combat.CombatEvent event=new com.openrsc.server.event.rsc.impl.combat.CombatEvent(server.getWorld(),npc,player);
    invoke(event.getClass(),event,"inflictDamage",new Class<?>[]{Mob.class,Mob.class,int.class},npc,player,17);
    check(player.getSkills().getLevel(3)==65,"actual melee impact no owner mitigation");
    clear();wear(1314);player.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);
    new com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent(server.getWorld(),npc,player,17,1,false).action();
    check(npc.getSkills().getLevel(3)==97&&player.getCache().getInt("ringofrecoil")==2,"actual projectile deterministic recoil");
    player.getCache().set("ringofrecoil",39);
    new com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent(server.getWorld(),npc,player,17,2,false).action();
    check(npc.getSkills().getLevel(3)==96,"recoil remaining budget clamp");
    check(!player.getCarriedItems().getEquipment().hasEquipped(1314)&&!player.getCache().hasKey("ringofrecoil"),"actual recoil shatter and cache clear");
    clear();wear(1314);check(CurrentBaseCombatContract.consumeRecoil(player,0)==0&&!player.getCache().hasKey("ringofrecoil"),"zero damage no recoil consumption");
    clear();wear(1317);player.getSkills().setTemporaryLevelAndMaxStat(3,11,100,false);
    check(!player.checkRingOfLife(npc),"life above threshold refusal");
    player.getSkills().setTemporaryLevelAndMaxStat(3,0,100,false);check(!player.checkRingOfLife(npc),"life cannot resurrect");
    player.getSkills().setTemporaryLevelAndMaxStat(3,10,100,false);
    player.setLocation(Point.location(120,247),true);
    check(player.getLocation().wildernessLevel()==31&&!player.checkRingOfLife(npc),"life wilderness31 refusal");
    player.setLocation(Point.location(120,253),true);
    check(player.getLocation().wildernessLevel()==30,"life wilderness30 fixture");
    player.getSkills().setTemporaryLevelAndMaxStat(3,11,100,false);
    npc.startCombat(player);check(npc.getCombatEvent()!=null,"life fixture active reciprocal combat");
    com.openrsc.server.event.rsc.impl.combat.CombatEvent lifeCombat=npc.getCombatEvent();
    new com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent(server.getWorld(),npc,player,1,1,false).action();
    check(player.getSkills().getLevel(3)==10,"life follows living ten-percent impact");
    check(player.getCombatEvent()==null&&npc.getCombatEvent()==null&&!lifeCombat.isRunning(),"actual ring-triggered reciprocal cleanup");
    server.getGameEventHandler().remove(lifeCombat);
    check(!player.getCarriedItems().getEquipment().hasEquipped(1317),"life always shatters");
    check(player.getX()==server.getConfig().RESPAWN_LOCATION_X&&player.getY()==server.getConfig().RESPAWN_LOCATION_Y,"actual life destination");
    clear();player.setLocation(Point.location(120,648),true);
    npc.setLocation(player.getLocation(),true);
    player.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);npc.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);
    field(Player.class,"loggedIn").setBoolean(player,true);
    wear(1314);
    npc.getSkills().setTemporaryLevelAndMaxStat(2,90,90,false);
    npc.getSkills().setTemporaryLevelAndMaxStat(0,90,90,false);
    int actual=0;
    for(int seed=0;seed<100;seed++) {
      DataConversions.getRandom().setSeed(seed);int expected=(int)formula("calculateMeleeDamage",npc);
      if(expected>0) {
        DataConversions.getRandom().setSeed(seed);
        npc.startCombat(player);
        com.openrsc.server.event.rsc.impl.combat.CombatEvent actualEvent=npc.getCombatEvent();
        check(actualEvent!=null&&actualEvent==player.getCombatEvent()&&npc.getPvmMeleeEvent()==null,"actual Base entry selects reciprocal event");
        actualEvent.run();
        actual=99-player.getSkills().getLevel(3);
        check(actual==0||actual==expected,"actual melee run classic roll or accuracy miss");
        check(npc.getSkills().getLevel(3)==99-(actual>0?actual/10+1:0),"actual melee run recoil");
        npc.resetCombatEvent();player.resetCombatEvent();server.getGameEventHandler().remove(actualEvent);
        check(npc.getCombatEvent()==null&&player.getCombatEvent()==null&&!actualEvent.isRunning(),"actual reciprocal reset terminates without recursive resetAll");
        if(actual>0)break;
      }
    }
    check(actual>0,"actual melee positive hit");field(Player.class,"loggedIn").setBoolean(player,false);
    clear();player.getCache().remove("ringofrecoil");
    player.applyEarthAttackSpeedDebuff(80);
    check(com.openrsc.server.event.rsc.impl.projectile.RangeUtils.getAdjustedRangeDelayTicks(player,3)==3,"public ranged no owner slow");
    player.clearEarthAttackSpeedDebuff();
    npc.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);
    server.getConfig().WANT_POISON_NPCS=true;
    for(int seed=0;seed<1000 && npc.getCurrentPoisonPower()<10;seed++) {
      DataConversions.getRandom().setSeed(seed);
      new com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent(server.getWorld(),player,npc,0,2,false,ItemId.POISONED_RUNE_THROWING_DART.id()).action();
    }
    check(npc.getCurrentPoisonPower()==60,"actual stock poisoned ammunition dispatch");
    com.openrsc.server.event.rsc.impl.PoisonEvent poison=npc.getAttribute("poisonEvent",null);
    check(poison!=null&&poison.getDelayTicks()==32,"public poison32tick cadence");
    poison.run();check(poison.getPoisonPower()==58&&npc.getSkills().getLevel(3)==93,"public poison6damage and2decay");
    poison.run();check(poison.getPoisonPower()==56&&npc.getSkills().getLevel(3)==88,"public poison floor division");
    poison.setPoisonPower(9);poison.run();check(npc.getCurrentPoisonPower()<10,"public poison exhaustion");
    player.setPoisonDamage(60);player.startPoisonEvent();
    new com.openrsc.server.event.rsc.impl.combat.scripts.all.PlayerPoisonScript().executeScript(player,player);
    check(player.getCurrentPoisonPower()==48,"public PvP poison resets48, no owner stacking");player.curePoison();
  }
  static void hostileMagic(Npc npc)throws Exception {
    clear();player.setCastTimer(0);player.getSkills().setTemporaryLevelAndMaxStat(6,99,99,false);
    player.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);npc.getSkills().setTemporaryLevelAndMaxStat(3,99,99,false);
    npc.setLocation(player.getLocation(),true);
    for(boolean gauntlets:new boolean[]{false,true}) {
      clear();player.setCastTimer(0);
      if(gauntlets) {wear(ItemId.GAUNTLETS_OF_CHAOS.id());player.getCache().set("famcrest_gauntlets",com.openrsc.server.external.Gauntlets.CHAOS.id());}
      SpellDef spell=server.getEntityHandler().getSpellDef(Spells.WIND_BOLT);
      for(Map.Entry<Integer,Integer> rune:spell.getRunesRequired())check(player.getCarriedItems().getInventory().add(new Item(rune.getKey(),rune.getValue()),false),"spell fixture runes");
      java.util.List<com.openrsc.server.event.rsc.GameTickEvent> before=server.getGameEventHandler().getEvents();
      invoke(SpellHandler.class,new SpellHandler(),"handleMobCast",new Class<?>[]{Player.class,Mob.class,Spells.class,int.class},player,npc,Spells.WIND_BOLT,2);
      Object action=player.getWalkToAction();check(action!=null,"actual hostile spell walk action");
      check(player.checkAttack(npc,true),"hostile fixture attackable");
      check((Boolean)invoke(SpellHandler.class,null,"canCast",new Class<?>[]{Player.class},player),"hostile fixture timer");
      DataConversions.getRandom().setSeed(501);
      Method execute=action.getClass().getDeclaredMethod("executeInternal");execute.setAccessible(true);execute.invoke(action);
      com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent projectile=null;
      for(com.openrsc.server.event.rsc.GameTickEvent event:server.getGameEventHandler().getEvents())
        if(before.stream().noneMatch(previous->previous==event)&&event instanceof com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent) {
          check(projectile==null,"one public projectile");projectile=(com.openrsc.server.event.rsc.impl.projectile.ProjectileEvent)event;
        }
      check(projectile!=null,"actual hostile dispatch queues projectile gauntlets="+gauntlets+" before="+before.size()+" after="+server.getGameEventHandler().getEvents().size());
      int damage=field(projectile.getClass(),"damage").getInt(projectile);
      check(damage==new Random(501).nextInt(gauntlets?6:5),"actual bolt public power and gauntlets plus1");
      for(String effect:new String[]{"windAccuracyDebuffPercent","waterMaxHitDebuffPercent","earthAttackSpeedDebuffPercent","fireDefenseDebuffPercent"})check(field(projectile.getClass(),effect).getInt(projectile)==0,"no owner spell debuff "+effect);
      for(Map.Entry<Integer,Integer> rune:spell.getRunesRequired())check(player.getCarriedItems().getInventory().countId(rune.getKey())==0,"actual spell reagent consumption");
      int hits=npc.getSkills().getLevel(3);projectile.action();check(npc.getSkills().getLevel(3)==hits-damage,"actual queued magic impact");
      projectile.stop();server.getGameEventHandler().remove(projectile);
    }
    clear();
    for(Spells spell:new Spells[]{Spells.CLAWS_OF_GUTHIX,Spells.SARADOMIN_STRIKE,Spells.FLAMES_OF_ZAMORAK}) {
      int skill=spell==Spells.CLAWS_OF_GUTHIX?1:spell==Spells.SARADOMIN_STRIKE?5:6;
      npc.getSkills().setTemporaryLevelAndMaxStat(skill,60,60,false);
      invoke(SpellHandler.class,new SpellHandler(),"applyPublicGodSpellDrain",new Class<?>[]{Player.class,Mob.class,Spells.class},player,npc,spell);
      check(npc.getSkills().getLevel(skill)==(skill==5?59:56),"public god spell affected numeric skill");
      invoke(SpellHandler.class,new SpellHandler(),"applyPublicGodSpellDrain",new Class<?>[]{Player.class,Mob.class,Spells.class},player,npc,spell);
      check(npc.getSkills().getLevel(skill)==(skill==5?58:56),"public god spell repeated drain policy");
    }
  }
  static void equipmentPacket()throws Exception {
    player.getSkills().setTemporaryLevelAndMaxStat(0,99,99,false);
    player.getSkills().setTemporaryLevelAndMaxStat(1,59,59,false);
    check(!player.getCarriedItems().getEquipment().ableToEquip(new Item(1430)),"public skirt needs Defense60 despite Attack99");
    player.getSkills().setTemporaryLevelAndMaxStat(1,60,60,false);
    check(player.getCarriedItems().getEquipment().ableToEquip(new Item(1430)),"public skirt accepts Defense60");
    clear();wear(1430);wear(317);
    io.netty.channel.embedded.EmbeddedChannel channel=new io.netty.channel.embedded.EmbeddedChannel();
    field(Player.class,"channel").set(player,channel);field(Player.class,"loggedIn").setBoolean(player,true);
    java.util.List<com.openrsc.server.net.Packet> packets=(java.util.List<com.openrsc.server.net.Packet>)field(Player.class,"outgoingPackets").get(player);
    for(com.openrsc.server.net.Packet packet:packets)packet.getBuffer().release();packets.clear();
    int hits=player.getSkills().getLevel(3),maxHits=player.getSkills().getMaxStat(3);
    com.openrsc.server.net.rsc.ActionSender.sendEquipmentStats(player);
    check(packets.size()==1,"actual public equipment packet");
    io.netty.buffer.ByteBuf bytes=packets.remove(0).getBuffer();
    int[] expected={83,7,7,7,1};
    check(bytes.readableBytes()==37,"stable equipment packet extent");
    for(int value:expected)check(bytes.readUnsignedByte()==value,"public byte equipment field");
    for(int value:expected)check(bytes.readInt()==value,"public full-width equipment field");
    for(int i=0;i<3;i++)check(bytes.readInt()==0,"no owner extended equipment power");
    bytes.release();
    check(player.getSkills().getLevel(3)==hits&&player.getSkills().getMaxStat(3)==maxHits,"packet does not alter Hits");
    field(Player.class,"loggedIn").setBoolean(player,false);field(Player.class,"channel").set(player,null);channel.finishAndReleaseAll();clear();
  }
  public static void main(String[] args) {
    try {run(args);System.exit(0);}catch(Throwable failure){failure.printStackTrace();System.exit(1);}
  }
  static void run(String[] args)throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    server=new Server("current-base.conf");server.getEntityHandler().load();
    check(server.getConfig().RESTRICT_ITEM_ID==1592,"public stock items remain obtainable");
    player=new Player(server.getWorld(),725L);
    player.getSettings().setAppearance(new com.openrsc.server.model.PlayerAppearance(0,0,0,0,1,2));
    player.setBank(new Bank(player));
    player.setClientVersion(server.getConfig().CLIENT_VERSION);
    player.setClientLimitations(com.openrsc.server.net.rsc.ClientLimitations.forVersion(player.getClientVersion()));
    player.getClientLimitations().maxSkillId=17;player.getClientLimitations().maxItemId=1592;
    player.setLocation(Point.location(120,648),true);
    server.getWorld().getPlayers().add(player);
    field(Player.class,"prayers").set(player,new Prayers(player));
    for(int id=0;id<18;id++)player.getSkills().setExperienceAndLevel(id,14000000,99,false);
    JSONObject policy=new JSONObject(new String(Files.readAllBytes(Paths.get(args[1],"combat-policy.json")),java.nio.charset.StandardCharsets.UTF_8));
    for(boolean equipmentTab:new boolean[]{false,true}) {
      server.getConfig().WANT_EQUIPMENT_TAB=equipmentTab;
      for(int id:new int[]{1430,314,316,317,430,0,117}) {
        clear();wear(id);
        com.openrsc.server.external.ItemDefinition def=server.getEntityHandler().getItemDef(id);
        check(player.getArmourPoints()==Math.max(1,1+(int)def.getArmourBonus()),"raw armour "+id);
        check(player.getWeaponAimPoints()==Math.max(1,1+def.getWeaponAimBonus()),"raw aim "+id);
        check(player.getWeaponPowerPoints()==Math.max(1,1+def.getWeaponPowerBonus()),"raw power "+id);
        check(player.getMagicPoints()==Math.max(1,1+def.getMagicBonus()),"raw magic "+id);
        player.getCache().set("devotion_zamorak_offerings",10000);
        player.getCache().store("myworld_prayer_book","ZAMORAK");
        check(player.getPrayerPoints()==Math.max(1,1+def.getPrayerBonus()),"no devotion bonus "+id);
        check(player.getDamageRollHighBiasChance()==0.0&&player.getArmorSpeedMultiplier()==1.0,"no armour bias/speed "+id);
      }
    }
    server.getConfig().WANT_EQUIPMENT_TAB=false;clear();wear(316);
    player.getSkills().setTemporaryLevelAndMaxStat(0,41,60,false);
    player.getSkills().setTemporaryLevelAndMaxStat(1,53,60,false);
    player.getSkills().setTemporaryLevelAndMaxStat(2,67,60,false);
    int[][] bonuses={{1,1,1},{0,0,3},{3,0,0},{0,3,0}};
    for(int style=0;style<4;style++) {
      player.setCombatStyle(style);
      for(int prayerTier=0;prayerTier<4;prayerTier++) {
        Arrays.fill(player.getPrayers().getActivePrayers(),false);
        if(prayerTier>0)for(int prayer:new int[][]{{0,1,2},{3,4,5},{9,10,11}}[prayerTier-1])player.getPrayers().setPrayer(prayer,true,false);
        double multiplier=1.0+0.05*prayerTier;
        check(formula("getMeleeDamage",player)==(Math.floor(67*multiplier)+8+bonuses[style][2])*75,"public max roll style/prayer");
        check(formula("getMeleeAccuracy",player)==(Math.floor(41*multiplier)+8+bonuses[style][0])*65,"public accuracy style/prayer");
        check(formula("getMeleeDefence",player)==(Math.floor(53*multiplier)+8+bonuses[style][1])*65,"public defense style/prayer");
      }
    }
    Arrays.fill(player.getPrayers().getActivePrayers(),false);
    Npc npc=new Npc(server.getWorld(),3,121,648);
    check(npc.getArmourPoints()==0&&npc.getWeaponAimPoints()==0&&npc.getWeaponPowerPoints()==0,"NPC raw equipment0");
    check(formula("getMeleeDamage",npc)==npc.getSkills().getLevel(2)*64,"NPC public max roll");
    JSONObject tables=policy.getJSONObject("projectileTables");
    for(String name:tables.keySet())for(Object value:tables.getJSONArray(name)) {
      JSONObject row=(JSONObject)value;
      int actual=((Number)invoke(CombatFormula.class,null,name,new Class<?>[]{int.class},row.getInt("id"))).intValue();
      check(actual==row.getInt("value"),"public ranged numeric table "+name+"/"+row.getInt("id"));
    }
    player.getSkills().setTemporaryLevelAndMaxStat(4,40,60,false);
    check(((Number)invoke(CombatFormula.class,null,"getRangedDamage",new Class<?>[]{Mob.class,int.class,int.class},player,ItemId.SHORTBOW.id(),ItemId.RUNE_ARROWS.id())).intValue()==48*105,"ammunition determines power");
    check(((Number)invoke(CombatFormula.class,null,"getRangedAccuracy",new Class<?>[]{Mob.class,int.class},player,ItemId.SHORTBOW.id())).intValue()==48*75,"bow determines aim");
    JSONObject spells=policy.getJSONObject("spellPowers");
    for(String name:spells.keySet()) {
      Spells spell=Spells.valueOf(name);double power=spells.getDouble(name);
      for(EntityType target:new EntityType[]{EntityType.PLAYER,EntityType.NPC})check(server.getConstants().getSpellDamages().getSpellDamage(spell,target,SpellDamages.MagicType.MODERNMAGIC)==power,"stock spell power "+name);
      Random expected=new Random(401);DataConversions.getRandom().setSeed(401);
      for(int i=0;i<32;i++)check(CombatFormula.calculateMagicDamage(player,npc,power,0.1)==expected.nextInt((int)Math.floor(power)+1),"actual magic no owner mitigation/cap "+name);
    }
    clear();check(CombatFormula.getGodSpellMax(player,false)==18,"god spell no cape/charge");wear(1213);
    check(CombatFormula.getGodSpellMax(player,false)==18,"cape alone no Charge benefit");
    player.setChargeEvent(new com.openrsc.server.event.DelayedEvent(server.getWorld(),player,1,"test charge") {public void run(){}});
    check(CombatFormula.getGodSpellMax(player,false)==25,"Charge and cape benefit");clear();
    check(CombatFormula.getGodSpellMax(player,false)==18,"Charge alone no benefit");player.setChargeEvent(null);
    SpellDef spell=server.getEntityHandler().getSpellDef(Spells.FIRE_WAVE);
    player.getSkills().setTemporaryLevelAndMaxStat(6,1,99,false);
    check(!(Boolean)invoke(SpellHandler.class,new SpellHandler(),"spellSuccessCheck",new Class<?>[]{Player.class,SpellDef.class},player,spell),"actual public cast failure");
    player.getSkills().setTemporaryLevelAndMaxStat(6,99,99,false);
    check((Boolean)invoke(SpellHandler.class,new SpellHandler(),"spellSuccessCheck",new Class<?>[]{Player.class,SpellDef.class},player,spell),"actual public cast success");
    prayerAndEffects(npc);
    hostileMagic(npc);
    equipmentPacket();
    // Owner selection control is an injected dispatch unit, never an Advanced launch claim.
    Constructor<CurrentCompositionIdentity> constructor=CurrentCompositionIdentity.class.getDeclaredConstructor(boolean.class,Map.class);constructor.setAccessible(true);
    Map<String,String> fields=new HashMap<>();fields.put("variantId","current-advanced-v1");
    field(CurrentCompositionIdentity.class,"current").set(null,constructor.newInstance(true,fields));
    check(!CurrentBaseCombatContract.selected(),"non-Base selection not public combat");
    check(server.getConstants().getSpellDamages().getSpellDamage(Spells.WIND_STRIKE,EntityType.NPC,SpellDamages.MagicType.MODERNMAGIC)==4.0,"owner spell power unchanged");
    player.getSkills().setTemporaryLevelAndMaxStat(6,1,99,false);
    check((Boolean)invoke(SpellHandler.class,new SpellHandler(),"spellSuccessCheck",new Class<?>[]{Player.class,SpellDef.class},player,spell),"owner cast no-failure unchanged");
    Prayers ownerPrayers=new Prayers(player);check(ownerPrayers.getActivePrayers().length==16,"owner prayer registry unchanged");
    com.openrsc.server.event.rsc.impl.PoisonEvent ownerPoison=new com.openrsc.server.event.rsc.impl.PoisonEvent(server.getWorld(),npc,60,null);
    check(ownerPoison.getDelayTicks()==8,"owner poison cadence unchanged");ownerPoison.run();check(ownerPoison.getPoisonPower()==57,"owner poison decay unchanged");
    player.applyEarthAttackSpeedDebuff(80);
    check(com.openrsc.server.event.rsc.impl.projectile.RangeUtils.getAdjustedRangeDelayTicks(player,3)>3,"owner ranged slow unchanged");
    player.resetCombatEvent();npc.resetCombatEvent();
    player.startCombat(npc);check(player.getPvmMeleeEvent()!=null&&player.getCombatEvent()==null,"non-Base actual entry retains owner PvM event");
    System.out.println("PUBLIC_COMBAT_VERIFIED equipmentFormulasImpactsPrayersRingsPoison=true");
  }
}
