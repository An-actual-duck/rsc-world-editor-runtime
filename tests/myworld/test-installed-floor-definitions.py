#!/usr/bin/env python3
"""Exercise verified installed-floor bootstrap and generated-ID projectile policy."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('floors', ROOT/'scripts/standard-floors.py')
floors = importlib.util.module_from_spec(spec); spec.loader.exec_module(floors)
java = r'''
import java.lang.reflect.*;
import java.nio.file.*;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.server.io.NativeLayeredTerrainTile;
import com.openrsc.server.model.world.region.NativeLayeredTerrainCollisionPlan;
public class InstalledFloorProbe {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args)throws Exception {
  if(args[0].equals("policy")) {
   for(int raw:new int[]{2,11,250})for(boolean marked:new boolean[]{false,true}) {
    com.openrsc.server.external.TileDef tile=new com.openrsc.server.external.TileDef();
    tile.worldBuilderSourceOverlay=marked?1:0;
    boolean expected=!marked&&raw!=250;
    check(tile.blocksLegacyProjectiles(raw)==expected,"server legacy policy");
    check(new com.openrsc.client.entityhandling.defs.TileDef(7,0,0,"",marked?1:0).blocksLegacyProjectiles(raw)==expected,"client legacy warning");
    NativeLayeredTerrainCollisionPlan.Result collision=NativeLayeredTerrainCollisionPlan.derive(new NativeLayeredTerrainTile(0,0,raw,0,0,0,0),null,null,id->false,id->false,id->false,id->tile.blocksLegacyProjectiles(id));
    check(collision.isOverlayProjectileBlocked()==expected,"native overlay policy");
   }
   System.out.println("PASS legacy and semantic raw2/11 projectile policy");return;
  }
  try {
   Method load=EntityHandler.class.getDeclaredMethod("loadInstalledFloorDefinitions");load.setAccessible(true);load.invoke(null);
   byte[] bytes=orsc.WorldBuilderInstalledFloorDefinitions.loadConfigured();
   check((bytes==null)==args[0].equals("absent"),"descriptor availability");
   if(bytes!=null) {check(EntityHandler.tileCount()==4,"installed catalog ignored");check(EntityHandler.getTileDef(0).getColour()==91,"custom original replaced");check(EntityHandler.getTileDef(1).getWorldBuilderSourceOverlay()==1,"generated raw2 lost");}
   check(!args[0].equals("reject"),"invalid installation accepted");
  } catch(Exception error) {if(!args[0].equals("reject"))throw error;}
 }
}
'''
with tempfile.TemporaryDirectory(prefix='installed-floors-') as tmp:
    root=Path(tmp); source=root/'InstalledFloorProbe.java';source.write_text(java)
    cp=':'.join([str(root), str(ROOT/'Client_Base/Open_RSC_Client.jar'), str(ROOT/'server/core.jar')])
    subprocess.run(['javac','-cp',cp,'-d',tmp,str(source)],check=True)
    subprocess.run(['java','-cp',cp,'InstalledFloorProbe','policy'],check=True)
    source=b'<TileDef-array><TileDef><colour>91</colour><unknown>4</unknown><objectType>1</objectType></TileDef></TileDef-array>'
    payload=floors.extend(source)
    base={'schemaVersion':1,'manifestType':'world-builder-installed-floor-definitions','tileDefinitionsRelativePath':'world-builder-configs/TileDef.xml','tileDefinitionsSha256':hashlib.sha256(payload).hexdigest()}
    cases=[('valid',base,payload),('absent',None,None),('reject',None,payload),('reject',dict(base,tileDefinitionsSha256='0'*64),payload),
           ('reject',dict(base,tileDefinitionsRelativePath='../TileDef.xml'),payload),('reject',dict(base,schemaVersion='1'),payload),
           ('reject',dict(base,extra=True),payload),('reject',base,None)]
    malformed=payload.replace(b'<worldBuilderSourceOverlay>1',b'<worldBuilderSourceOverlay>0')
    cases.append(('reject',dict(base,tileDefinitionsSha256=hashlib.sha256(malformed).hexdigest()),malformed))
    for i,(mode,descriptor,xml) in enumerate(cases):
        case=root/str(i);config=case/'world-builder-configs';config.mkdir(parents=True)
        if descriptor is not None:(config/'installed-floors.json').write_text(json.dumps(descriptor))
        if xml is not None:(config/'TileDef.xml').write_bytes(xml)
        subprocess.run(['java','-cp',cp,'InstalledFloorProbe',mode],check=True,cwd=case)
    linked=root/'linked';linked.mkdir();(linked/'world-builder-configs').symlink_to(root/'0/world-builder-configs',target_is_directory=True)
    subprocess.run(['java','-cp',cp,'InstalledFloorProbe','reject'],check=True,cwd=linked)
print('PASS installed client bootstrap, absence, hash/path/schema/XML and symlink refusals')
