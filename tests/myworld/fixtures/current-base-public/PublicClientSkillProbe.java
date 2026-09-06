import java.lang.reflect.*;
import java.util.*;
import orsc.*;
import orsc.buffers.RSBuffer_Bits;

/** Actual client registry/menu dispatch and stat packet consumers; no window or network. */
public final class PublicClientSkillProbe {
  static Object unsafe;
  static Class<?> unsafeType;
  static Object allocate(Class<?> type) throws Exception { return unsafeType.getMethod("allocateInstance",Class.class).invoke(unsafe,type); }
  static Field field(Class<?> type,String name) throws Exception {
    while(type!=null) { try { Field f=type.getDeclaredField(name);f.setAccessible(true);return f; } catch(NoSuchFieldException absent) { type=type.getSuperclass(); } }
    throw new NoSuchFieldException(name);
  }
  static void set(Object object,String name,Object value) throws Exception { field(object.getClass(),name).set(object,value); }
  static Object call(Object object,String name,Class<?>[] types,Object... args) throws Exception {
    Method m=object.getClass().getDeclaredMethod(name,types);m.setAccessible(true);return m.invoke(object,args);
  }
  static void check(boolean value,String label) { if(!value)throw new AssertionError(label); }
  public static void main(String[] args) throws Exception {
    boolean control=Boolean.getBoolean("publicSkillSelectionControl");
    if(control) {
      // Deliberately injected selection unit; not a valid Advanced launch/binding claim.
      Constructor<CurrentCompositionIdentity> constructor=CurrentCompositionIdentity.class.getDeclaredConstructor(boolean.class,Map.class);constructor.setAccessible(true);
      Map<String,String> fields=new HashMap<>();fields.put("variantId","current-advanced-v1");
      field(CurrentCompositionIdentity.class,"current").set(null,constructor.newInstance(true,fields));
      Config.S_WANT_RUNECRAFT=false;Config.S_WANT_HARVESTING=false;
    } else CurrentCompositionIdentity.initializeFromSystemProperties();
    unsafeType=Class.forName("sun.misc.Unsafe");Field f=unsafeType.getDeclaredField("theUnsafe");f.setAccessible(true);unsafe=f.get(null);
    mudclient client=(mudclient)allocate(mudclient.class);
    call(client,"loadSkills",new Class<?>[]{});
    List<?> names=(List<?>)field(mudclient.class,"skillNameLongArray").get(null);
    if(control) {
      check(((String[])call(client,"createEquipmentStatNames",new Class<?>[]{}))[0].equals("Rng. Def"),"owner equipment labels unchanged");
      check(names.size()==20 && names.get(0).equals("Melee") && names.get(5).equals("Worship") && names.get(11).equals("Retired"),"non-Base registry unchanged");
      for(int id:new int[]{1,2,9,11})check((Boolean)call(client,"isSkillHiddenFromStatsMenu",new Class<?>[]{int.class},id),"owner hidden skills unchanged");
      check(!(Boolean)call(client,"shouldDrawPublicCombatStyleMenu",new Class<?>[]{}),"no public style menu outside Base");
      System.out.println("PUBLIC_CLIENT_SKILLS_VERIFIED nonBaseSelectionUnit=true");return;
    }
    String[] expected={"Attack","Defense","Strength","Hits","Ranged","Prayer","Magic","Cooking","Woodcutting","Fletching","Fishing","Firemaking","Crafting","Smithing","Mining","Herblaw","Agility","Thieving"};
    check(names.equals(Arrays.asList(expected)),"actual public registry");
    mudclient.skillCount=18;field(mudclient.class,"skillNameLong").set(null,expected);
    int[] visible=(int[])call(client,"getDisplayedSkillIndices",new Class<?>[]{});
    check(visible.length==18,"all classic skills visible");for(int i=0;i<18;i++)check(visible[i]==i,"numeric display ordering");
    set(client,"playerStatCurrent",new int[18]);set(client,"playerStatBase",new int[18]);set(client,"playerExperience",new int[18]);
    PacketHandler handler=new PacketHandler(client);set(client,"packetHandler",handler);
    RSBuffer_Bits input=(RSBuffer_Bits)field(PacketHandler.class,"packetsIncoming").get(handler);
    for(int i=0;i<18;i++)input.putByte(20+i);for(int i=0;i<18;i++)input.putByte(60-i);
    input.packetEnd=0;call(handler,"loadStats",new Class<?>[]{});
    input.packetEnd=0;for(int i=0;i<18;i++)input.putInt(40000+400*i);
    input.packetEnd=0;call(handler,"loadExperience",new Class<?>[]{});
    for(int i=0;i<18;i++) {
      check(((int[])field(mudclient.class,"playerStatCurrent").get(client))[i]==20+i,"decoded current"+i);
      check(client.getPlayerStatBase(i)==60-i,"decoded max"+i);
      check(client.getPlayerExperience(i)==10000+100*i,"decoded fixed-point XP"+i);
    }
    Config.S_EXPERIENCE_COUNTER_TOGGLE=false;Config.S_EXPERIENCE_DROPS_TOGGLE=false;
    for(int id:new int[]{0,1,2,11}) {
      input.packetEnd=0;input.putByte(id);input.putByte(19+id);input.putByte(40+id);input.putInt(120000+4*id);
      input.packetEnd=0;call(handler,"updateExperience",new Class<?>[]{});
      check(client.getPlayerStatBase(id)==40+id && client.getPlayerExperience(id)==30000+id,"single-stat decoder"+id);
    }
    Config.C_HITS_XP_FOCUS_MENU=2;Config.C_GATHERING_FOCUS_MENU=2;Config.C_FIGHT_MENU=2;
    check(!(Boolean)call(client,"shouldDrawHitsXpFocusMenu",new Class<?>[]{}),"owner HitsFocus disabled");
    check(!(Boolean)call(client,"shouldDrawGatheringFocusMenu",new Class<?>[]{}),"owner gathering menu disabled");
    check((Boolean)call(client,"shouldDrawPublicCombatStyleMenu",new Class<?>[]{}),"classic always-show control");
    client.setFightModeSelectorToggle(0);check(!(Boolean)call(client,"shouldDrawPublicCombatStyleMenu",new Class<?>[]{}),"classic hide control");
    orsc.net.Network_Socket stream=(orsc.net.Network_Socket)allocate(orsc.net.Network_Socket.class);
    RSBuffer_Bits output=new RSBuffer_Bits(8192);set(stream,"bufferBits",output);handler.setClientStream(stream);
    for(int style=0;style<4;style++) {
      call(client,"selectCombatStyleMenuRow",new Class<?>[]{int.class},style);
      int at=style*4;
      check(output.dataBuffer[at]==0 && output.dataBuffer[at+1]==2 && output.dataBuffer[at+2]==29 && output.dataBuffer[at+3]==style,"actual menu packet29"+style);
      check(client.getCombatStyle()==style,"selected classic control state");
    }
    Config.F_CACHE_DIR=java.nio.file.Paths.get("Cache").toAbsolutePath().toString();
    com.openrsc.client.entityhandling.EntityHandler.load(true);
    check(com.openrsc.client.entityhandling.EntityHandler.prayerCount()==14,"actual public prayers");
    set(client,"prayerOn",new boolean[14]);
    client.setPlayerStatBase(5,99);client.setPlayerStatCurrent(5,1);
    for(int prayer=0;prayer<14;prayer++) {
      check((Boolean)call(client,"canActivatePrayer",new Class<?>[]{int.class},prayer),"level eligibility, no reservation "+prayer);
      call(client,"togglePrayerMenuPrayer",new Class<?>[]{int.class},prayer);
      int at=16+prayer*4;
      check(output.dataBuffer[at+2]==60 && output.dataBuffer[at+3]==prayer,"actual prayer activation packet "+prayer);
    }
    client.setPlayerStatBase(5,1);client.setPlayerStatCurrent(5,99);
    check(!(Boolean)call(client,"canActivatePrayer",new Class<?>[]{int.class},13),"boosted current cannot bypass required max");
    client.setPlayerStatBase(5,99);client.setPlayerStatCurrent(5,0);
    check(!(Boolean)call(client,"canActivatePrayer",new Class<?>[]{int.class},0),"zero prayer refusal");
    ((boolean[])field(mudclient.class,"prayerOn").get(client))[0]=true;
    call(client,"togglePrayerMenuPrayer",new Class<?>[]{int.class},0);
    check((output.dataBuffer[74]&255)==254 && output.dataBuffer[75]==0,"actual prayer deactivation packet");
    check((Integer)call(client,"getAllocatedPrayerPoints",new Class<?>[]{})==0,"no owner reservation");
    check((Integer)call(client,"getPrayerAllocationPoints",new Class<?>[]{})==99,"public prayer display max");
    String[] equipmentNames=(String[])call(client,"createEquipmentStatNames",new Class<?>[]{});
    check(Arrays.asList(equipmentNames).subList(0,5).equals(Arrays.asList("Armour","Aim","Power","Magic","Prayer")),"classic equipment labels");
    set(client,"playerStatEquipment",new int[8]);input.packetEnd=0;
    int[] equipment={83,7,7,7,1,0,0,0};for(int i=0;i<5;i++)input.putByte(equipment[i]);for(int value:equipment)input.putInt(value);
    input.packetEnd=0;call(handler,"updateEquipmentStats",new Class<?>[]{int.class},37);
    check(Arrays.equals((int[])field(mudclient.class,"playerStatEquipment").get(client),equipment),"actual classic equipment numeric packet decoder");
    System.out.println("PUBLIC_CLIENT_SKILLS_VERIFIED registry=18 stats=18 singleStats=4 styles=4 noWindow=true");
  }
}
