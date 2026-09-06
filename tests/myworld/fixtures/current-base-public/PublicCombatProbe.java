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
  public static void main(String[] args) {
    try {run(args);System.exit(0);}catch(Throwable failure){failure.printStackTrace();System.exit(1);}
  }
  static void run(String[] args)throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    server=new Server("current-base.conf");server.getEntityHandler().load();
    check(server.getConfig().RESTRICT_ITEM_ID==1592,"public stock items remain obtainable");
    player=new Player(server.getWorld(),725L);
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
    // Owner selection control is an injected dispatch unit, never an Advanced launch claim.
    Constructor<CurrentCompositionIdentity> constructor=CurrentCompositionIdentity.class.getDeclaredConstructor(boolean.class,Map.class);constructor.setAccessible(true);
    Map<String,String> fields=new HashMap<>();fields.put("variantId","current-advanced-v1");
    field(CurrentCompositionIdentity.class,"current").set(null,constructor.newInstance(true,fields));
    check(!CurrentBaseCombatContract.selected(),"non-Base selection not public combat");
    check(server.getConstants().getSpellDamages().getSpellDamage(Spells.WIND_STRIKE,EntityType.NPC,SpellDamages.MagicType.MODERNMAGIC)==4.0,"owner spell power unchanged");
    player.getSkills().setTemporaryLevelAndMaxStat(6,1,99,false);
    check((Boolean)invoke(SpellHandler.class,new SpellHandler(),"spellSuccessCheck",new Class<?>[]{Player.class,SpellDef.class},player,spell),"owner cast no-failure unchanged");
    System.out.println("PUBLIC_COMBAT_VERIFIED initialEquipmentAndFormulaSlice=true");
  }
}
