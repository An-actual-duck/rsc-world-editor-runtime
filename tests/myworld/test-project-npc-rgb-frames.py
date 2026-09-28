#!/usr/bin/env python3
"""Lossless project NPC frames through client initialization and software drawing."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("npc_registry", ROOT / "tests/myworld/test-project-npc-animation-registry-v1.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

HARNESS = r'''
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.zip.*;
import orsc.*;
import orsc.graphics.two.*;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.client.entityhandling.defs.*;
import com.openrsc.client.entityhandling.defs.extras.AnimationDef;
public final class NpcRgbHarness {
  static Field field(Class<?> c,String n)throws Exception {Field f=c.getDeclaredField(n);f.setAccessible(true);return f;}
  static Object call(Class<?> c,Object o,String n,Class<?>[] types,Object...args)throws Exception {
    Method m=c.getDeclaredMethod(n,types);m.setAccessible(true);return m.invoke(o,args);
  }
  public static void main(String[] args)throws Exception {
    ProjectContentBundle b=ProjectContentBundle.load(Paths.get(args[0]),args[1],"project-local-custom-content-v3",args[2],args[3],args[4],args[5]);
    int npcId=Integer.parseInt(args[6]), animationId=Integer.parseInt(args[7]);
    List<AnimationDef> animations=(List<AnimationDef>)field(EntityHandler.class,"animations").get(null);
    int capacity;
    try(java.util.jar.JarFile jar=new java.util.jar.JarFile(args[8])) {
      capacity=Integer.parseInt(jar.getManifest().getMainAttributes().getValue("World-Builder-Npc-Animation-Count"));
    }
    for(boolean custom:new boolean[]{false,true}) for(boolean bearded:new boolean[]{false,true}) {
      Config.S_WANT_CUSTOM_SPRITES=custom;Config.S_ALLOW_BEARDED_LADIES=bearded;animations.clear();
      call(EntityHandler.class,null,"loadAnimationDefinitions",new Class<?>[]{});
      if(animations.size()>capacity)throw new AssertionError("Manifest animation capacity is stale: "+animations.size());
    }
    call(EntityHandler.class,null,"loadProjectNpcAnimations",new Class<?>[]{ProjectContentBundle.class},b);
    call(EntityHandler.class,null,"loadProjectNpcs",new Class<?>[]{ProjectContentBundle.class},b);
    NPCDef npc=EntityHandler.getNpcDef(npcId);
    if(npc.getSprite(0)!=animationId)throw new AssertionError("NPC animation mapping differs");
    AnimationDef animation=EntityHandler.getAnimationDef(animationId);
    sun.misc.Unsafe unsafe=(sun.misc.Unsafe)field(sun.misc.Unsafe.class,"theUnsafe").get(null);
    mudclient client=(mudclient)unsafe.allocateInstance(mudclient.class);
    orsc.multiclient.ClientPort port=(orsc.multiclient.ClientPort)Proxy.newProxyInstance(NpcRgbHarness.class.getClassLoader(),new Class<?>[]{orsc.multiclient.ClientPort.class},(o,m,a)->null);
    field(mudclient.class,"clientPort").set(client,port);
    Config.S_WANT_CUSTOM_SPRITES=true;
    MudClientGraphics surface=new MudClientGraphics(240,240,70000);
    surface.sprites=new com.openrsc.client.model.Sprite[70000];
    field(GraphicsController.class,"spriteArchive").set(surface,new ZipFile(b.path("asset.sprite.authentic").toFile()));
    client.setSurface(surface);
    // Exercise normal authentic initialization. It must retain the bound frame base.
    int originalBase=animation.getNumber();
    call(mudclient.class,client,"loadEntitiesAuthentic",new Class<?>[]{});
    if(animation.getNumber()!=originalBase)throw new AssertionError("Authentic initialization renumbered imported animation");
    ORSCharacter character=new ORSCharacter();character.npcId=npcId;
    field(mudclient.class,"npcs").set(client,new ORSCharacter[]{character});
    field(mudclient.class,"animFrameToSprite_Walk").set(client,new int[]{0,1,2,1});
    int[][] layers=new int[8][12];for(int[] row:layers)for(int i=0;i<12;i++)row[i]=i;
    field(mudclient.class,"animDirLayer_To_CharLayer").set(client,layers);
    java.awt.image.BufferedImage contact=new java.awt.image.BufferedImage(240*8,240*6,java.awt.image.BufferedImage.TYPE_INT_RGB);
    for(boolean custom:new boolean[]{false,true}) {
      Config.S_WANT_CUSTOM_SPRITES=custom;
      for(int direction=0;direction<8;direction++)for(int beat=0;beat<3;beat++) {
        field(ORSCharacter.class,"direction").set(character,orsc.enumerations.ORSCharacterDirection.lookup(direction));
        field(ORSCharacter.class,"stepFrame").setInt(character,beat*Math.max(1,npc.getWalkModel()));
        int facing=direction>4?8-direction:direction, offset=facing*3+beat;
        com.openrsc.client.model.Sprite actual=surface.spriteSelect(animation,offset);
        com.openrsc.client.model.Sprite expected=b.npcAnimations().get(animationId).rgbFrame(offset);
        if(!Arrays.equals(actual.getPixels(),expected.getPixels()))throw new AssertionError("Frame pixels changed");
        if(actual.getWidth()<16||actual.getHeight()<16)throw new AssertionError("Placeholder sized frame");
        Arrays.fill(surface.pixelData,0);client.drawNPC(0,20,20,180,180,0,0,100);
        int count=0,minY=240,maxY=-1;for(int y=0;y<240;y++)for(int x=0;x<240;x++)if(surface.pixelData[y*240+x]!=0){count++;minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
        if(count<256||maxY-minY<80)throw new AssertionError("NPC body missing: "+count+" bounds="+minY+".."+maxY);
        contact.setRGB(direction*240,(beat+(custom?3:0))*240,240,240,surface.pixelData,0,240);
      }
    }
    if(args.length>9)javax.imageio.ImageIO.write(contact,"png",Paths.get(args[9]).toFile());
    System.out.println("npc-rgb-rendered npc="+npcId+" animation="+animationId+" modes=2 directions=8 beats=3");
  }
}
'''

class NpcRgbFramesTest(unittest.TestCase):
    bundle = helper.ProjectNpcAnimationRegistryV1Test.bundle

    @classmethod
    def setUpClass(cls):
        helper.ProjectNpcAnimationRegistryV1Test.setUpClass()
        cls.classes = helper.ProjectNpcAnimationRegistryV1Test.classes
        source = Path(cls.classes.name) / "NpcRgbHarness.java"
        source.write_text(HARNESS)
        subprocess.run(["javac", "-cp", str(helper.CLIENT), "-d", cls.classes.name, str(source)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def rgb_bundle(self, mutation=None):
        workspace,bundle,manifest,registry_path=self.bundle()
        registry=json.loads(registry_path.read_text())
        row=registry["animations"][0]
        for key in ("customSpriteSubspace","customSpriteEntry","customEntrySha256"):row.pop(key)
        row["frameSource"]="authentic-rgb"
        row["charColour"]=0;row["blueMask"]=0
        row["authenticBaseSpriteId"]=20000
        row["authenticFrameSha256s"]=[]
        archive=bundle/"files/client/Cache/video/Authentic_Sprites.orsc"
        out=io.BytesIO()
        with zipfile.ZipFile(archive) as old,zipfile.ZipFile(out,"w") as new:
            for entry in old.infolist():new.writestr(entry,old.read(entry.filename))
            for offset in range(15):
                pixels=[((i+1)*37+offset*257)&0xffffff or 1 for i in range(32*64)]
                payload=struct.pack(">iiBiiii",32,64,0,0,0,32,64)+struct.pack(">"+"I"*len(pixels),*pixels)
                if mutation=="dimensions" and offset==0:payload=b"\x7f\xff\xff\xff"+payload[4:]
                if mutation=="trailing" and offset==0:payload+=b"x"
                new.writestr(f"sprites/{20000+offset}.dat",payload)
                row["authenticFrameSha256s"].append(hashlib.sha256(payload).hexdigest())
        archive.write_bytes(out.getvalue())
        if mutation=="legacy-id":row["animationId"]=0
        if mutation=="mode":row["frameSource"]="guess"
        if mutation=="extra":row["customSpriteEntry"]="foreign"
        if mutation=="hash":row["authenticFrameSha256s"][0]="f"*64
        registry_path.write_text(json.dumps(registry))
        # A full-body fixture replaces the first NPC layer; no runtime NPC ID special case.
        npcs=bundle/"files/server/conf/server/defs/NpcDefs.json"
        doc=json.loads(npcs.read_text()); npc=next(iter(doc.values()))[0]
        for i in range(1,13):npc["sprites"+str(i)]=2000 if i==1 else -1
        npc["walkModel"]=1
        npcs.write_text(json.dumps(doc))
        for file in manifest["files"]:
            payload=(bundle/file["bundleRelativePath"]).read_bytes()
            file["size"]=len(payload);file["sha256"]=hashlib.sha256(payload).hexdigest()
        manifest["bundleFingerprintSha256"]="0"*64
        manifest["bundleFingerprintSha256"]=hashlib.sha256(b"world-builder-project-content-bundle-v3\n"+helper.canonical(manifest)).hexdigest()
        (bundle/"manifest.json").write_text(json.dumps(manifest))
        return workspace,bundle,manifest

    def consume(self, mutation=None):
        workspace,bundle,m=self.rgb_bundle(mutation)
        args=[str(workspace),str(bundle),m["bundleFingerprintSha256"],m["definitionFingerprintSha256"],m["assetFingerprintSha256"],m["itemVisualFingerprintSha256"]]
        for name,jar,extra in (("NpcRgbHarness",helper.CLIENT,["0","2000",str(helper.CLIENT)]),("NpcAnimationV1ServerHarness",helper.SERVER,[])):
            result=subprocess.run(["java","-cp",f"{self.classes.name}:{jar}",name,*args,*extra],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(mutation is None,result.returncode==0,result.stdout)
            if mutation is None and name=="NpcRgbHarness":self.assertIn("modes=2 directions=8 beats=3",result.stdout)

    def test_lossless_rgb_initialization_and_rendering(self):self.consume()
    def test_malformed_rgb_refused_by_both_roles(self):
        for mutation in ("dimensions","trailing","mode","extra","hash","legacy-id"):
            with self.subTest(mutation=mutation):self.consume(mutation)

if __name__=="__main__":unittest.main()
