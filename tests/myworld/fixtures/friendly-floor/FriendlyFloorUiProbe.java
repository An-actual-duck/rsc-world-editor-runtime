package com.openrsc.interfaces.misc;
import java.lang.reflect.*;
import java.nio.file.*;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.data.DataOperations;
import orsc.*;
import orsc.graphics.two.*;
import orsc.net.Network_Socket;
import orsc.buffers.RSBuffer_Bits;
public class FriendlyFloorUiProbe {
 static Path screenshots;
 static Field f(Class<?> c,String n)throws Exception{while(c!=null){try{Field f=c.getDeclaredField(n);f.setAccessible(true);return f;}catch(NoSuchFieldException e){c=c.getSuperclass();}}throw new NoSuchFieldException(n);}
 static Object call(Object x,String n,Class<?>[] ts,Object... a)throws Exception{Method m=x.getClass().getDeclaredMethod(n,ts);m.setAccessible(true);return m.invoke(x,a);}
 static void check(boolean yes,String message){if(!yes)throw new AssertionError(message);}
 static void shot(MudClientGraphics g,String name)throws Exception{BufferedImage image=new BufferedImage(760,420,BufferedImage.TYPE_INT_RGB);image.setRGB(0,0,760,420,g.pixelData,0,760);ImageIO.write(image,"png",screenshots.resolve(name+".png").toFile());}
 public static void main(String[] args)throws Exception{
  screenshots=Paths.get(args[2]);
  EntityHandler.load(true);
  Method load=EntityHandler.class.getDeclaredMethod("loadProjectTiles",Path.class);load.setAccessible(true);load.invoke(null,Paths.get(args[0]));
  byte[] archive=Files.readAllBytes(Paths.get(args[1]));for(String name:new String[]{"h11p.jf","h12b.jf","h12p.jf","h13b.jf","h14b.jf","h16b.jf","h20b.jf","h24b.jf"})Fonts.addFont(DataOperations.loadData(name,0,archive));
  sun.misc.Unsafe unsafe=(sun.misc.Unsafe)f(sun.misc.Unsafe.class,"theUnsafe").get(null);mudclient mc=(mudclient)unsafe.allocateInstance(mudclient.class);
  MudClientGraphics g=new MudClientGraphics(760,420,6000);f(mudclient.class,"surface").set(mc,g);f(mudclient.class,"midRegionBaseZ").set(mc,944);
  PacketHandler packets=(PacketHandler)unsafe.allocateInstance(PacketHandler.class);Network_Socket socket=(Network_Socket)unsafe.allocateInstance(Network_Socket.class);RSBuffer_Bits buffer=new RSBuffer_Bits(8192);f(Network_Socket.class,"bufferBits").set(socket,buffer);f(PacketHandler.class,"clientStream").set(packets,socket);f(mudclient.class,"packetHandler").set(mc,packets);
  WorldEditorInterface editor=new WorldEditorInterface(mc);
  call(editor,"handleFloorMouse",new Class[]{int.class,int.class},20,95);check(f(editor.getClass(),"floorColorPalette").getBoolean(editor),"color picker closed");
  call(editor,"renderFloorControls",new Class[]{int.class,int.class},10,0);shot(g,"friendly-floor-colors");
  call(editor,"handleFloorMouse",new Class[]{int.class,int.class},23,73);check(f(editor.getClass(),"terrainFloorColor").getInt(editor)==17,"swatch input missed");
  java.util.Arrays.fill(g.pixelData,0x202020);call(editor,"renderFloorControls",new Class[]{int.class,int.class},10,0);call(editor,"renderTerrain",new Class[]{int.class,int.class},260,0);shot(g,"friendly-floor-controls");
  int mask=(Integer)call(editor,"terrainPaintMask",new Class[]{});check(mask==6,"floor paint must update both bytes");call(editor,"snapshotTerrainPaint",new Class[]{int.class},mask);
  int resolved=f(editor.getClass(),"terrainStrokeTexture").getInt(editor);check(EntityHandler.getTileDef(resolved-1).usesExplicitBaseColor(),"upstairs snapshot resolved invisible base");
  f(editor.getClass(),"terrainStrokeTiles").set(editor,new int[][]{{10,955}});call(editor,"sendTerrainStroke",new Class[]{});
  check((buffer.dataBuffer[17]&255)==6,"wire field mask");check((buffer.dataBuffer[19]&255)==17,"wire color");check((buffer.dataBuffer[20]&255)==resolved,"wire resolved overlay");
  f(editor.getClass(),"lastClickedLevel").set(editor,1);call(editor,"seedTerrain",new Class[]{int[].class},new int[]{0,17,0,0,0,0,0});check(f(editor.getClass(),"terrainFloorTexture").getInt(editor)==-1,"copy upper invisible lost");
  int invisible=(Integer)call(editor,"resolvedFloorOverlay",new Class[]{});check(EntityHandler.getTileDef(invisible-1).getColour()==12345678,"copy invisible became color");
  call(editor,"seedTerrain",new Class[]{int[].class},new int[]{0,17,200,0,0,0,0});
  call(editor,"setTerrainFloorTexture",new Class[]{int.class},3);call(editor,"setTerrainFloorTexture",new Class[]{int.class},0);check(f(editor.getClass(),"terrainFloorColor").getInt(editor)==17,"texture cleared remembered color");
  load.invoke(null,Paths.get(args[3]));call(editor,"setTerrainFloorTexture",new Class[]{int.class},3);f(editor.getClass(),"floorWalkable").set(editor,true);
  check(!(Boolean)call(editor,"canToggleFloorWalkable",new Class[]{}),"missing inverse incorrectly enabled");
  call(editor,"handleFloorMouse",new Class[]{int.class,int.class},20,65);check(f(editor.getClass(),"floorWalkable").getBoolean(editor),"unavailable toggle changed intent");
  System.out.println("PASS actual Floor input, swatch rendering, atomic wire payload and upper invisible copy");
 }
}
