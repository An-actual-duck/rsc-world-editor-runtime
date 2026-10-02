#!/usr/bin/env python3
"""Source-ID-independent NPC masks, paired registry rejection and software pixel parity."""
import importlib.util
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('rgb',ROOT/'tests/myworld/test-project-npc-rgb-frames.py')
rgb=importlib.util.module_from_spec(spec);spec.loader.exec_module(rgb)
HARNESS=r'''
package orsc;
import java.lang.reflect.*;import java.util.*;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.client.entityhandling.defs.NPCDef;
import com.openrsc.client.entityhandling.defs.extras.AnimationDef;
import com.openrsc.client.model.Sprite;
import orsc.graphics.two.*;
public class NpcMaskParity {
 static Field f(Class<?> c,String n)throws Exception{Field f=c.getDeclaredField(n);f.setAccessible(true);return f;}
 public static void main(String[] args)throws Exception{
  sun.misc.Unsafe u=(sun.misc.Unsafe)f(sun.misc.Unsafe.class,"theUnsafe").get(null);
  mudclient c=(mudclient)u.allocateInstance(mudclient.class);
  MudClientGraphics g=new MudClientGraphics(160,160,70000);c.setSurface(g);
  List<AnimationDef> animations=(List<AnimationDef>)f(EntityHandler.class,"animations").get(null);
  animations.clear();for(int i=0;i<2200;i++)animations.add(null);
  List<NPCDef> npcs=(List<NPCDef>)f(EntityHandler.class,"npcs").get(null);npcs.clear();
  NPCDef def=new NPCDef("fixture","","",1,1,1,1,false,new int[12],0x1177aa,0x22bb44,0xaa3344,0xcc9966,100,100,1,2,1,0);npcs.add(def);
  ORSCharacter character=new ORSCharacter();character.npcId=0;
  f(mudclient.class,"npcs").set(c,new ORSCharacter[]{character});
  f(mudclient.class,"animFrameToSprite_Walk").set(c,new int[]{0,1,2,1});
  f(mudclient.class,"animFrameToSprite_CombatA").set(c,new int[]{0,1,2,1,0,1,2,1});
  f(mudclient.class,"animFrameToSprite_CombatB").set(c,new int[]{2,1,0,1,2,1,0,1});
  int[][] layers=new int[8][12];for(int d=0;d<8;d++)for(int i=0;i<12;i++)layers[d][i]=(i+d)%12;
  f(mudclient.class,"animDirLayer_To_CharLayer").set(c,layers);
  IdentityHashMap<AnimationDef,ProjectNpcAnimationRegistry.EntryDef> registry=(IdentityHashMap)f(EntityHandler.class,"PROJECT_NPC_ANIMATIONS").get(null);
  Sprite[] frames=new Sprite[27];int[] colors={0,1,0x010101,0x808080,0xff8080,0x0000ff,0x123456};
  for(int k=0;k<27;k++){int[] p=new int[120];for(int i=0;i<p.length;i++)p[i]=colors[(i+k)%colors.length];Sprite s=new Sprite(p,10,12);s.setRequiresShift(true);s.setShift(-1+k%3,2);s.setSomething(16+k%2,18);frames[k]=s;}
  int compared=0;
  for(int source:new int[]{229,230})for(boolean sourceCustom:new boolean[]{false,true})for(int colour:new int[]{0,1,2,3,0x66aa88})for(int count:new int[]{15,18,27}){
   boolean combat=count>=18,special=count==27;
   String policy=NpcAnimationMaskPolicy.derive(source,sourceCustom,colour);
   int primary=colour,secondary=0;
   if(colour==1){primary=def.getHairColour();secondary=def.getSkinColour();}
   else if(source>=230&&sourceCustom){secondary=def.getSkinColour();}
   else if(colour==2){primary=def.getTopColour();secondary=def.getSkinColour();}
   else if(colour==3){primary=def.getBottomColour();secondary=def.getSkinColour();}
   long masks=NpcAnimationMaskPolicy.resolve(policy,colour,def.getHairColour(),def.getTopColour(),def.getBottomColour(),def.getSkinColour());
   if((int)(masks>>>32)!=primary||(int)masks!=secondary)throw new AssertionError("Legacy mask mismatch");
   ProjectNpcAnimationRegistry.EntryDef old=new ProjectNpcAnimationRegistry.EntryDef(source,"old","npc",colour,0,0,combat,special,0,frames,null);
   ProjectNpcAnimationRegistry.EntryDef captured=new ProjectNpcAnimationRegistry.EntryDef(2000,"private","npc",colour,0,0,combat,special,0,frames,policy);
   AnimationDef a=old.animationDef(),b=captured.animationDef();animations.set(source,a);animations.set(2000,b);registry.put(a,old);registry.put(b,captured);
   for(int direction=0;direction<16;direction++)for(int beat=0;beat<3;beat++)for(boolean privateCustom:new boolean[]{false,true})for(boolean wield:new boolean[]{false,true}){
    character.direction=orsc.enumerations.ORSCharacterDirection.lookup(direction);character.stepFrame=beat;f(mudclient.class,"frameCounter").setInt(c,beat);
    int[][] images=new int[2][];
    for(int pass=0;pass<2;pass++){
     Config.S_WANT_CUSTOM_SPRITES=pass==0?sourceCustom:privateCustom;Config.S_WANT_CUSTOM_LANDSCAPE=false;
     Arrays.fill(def.sprites,-1);def.sprites[0]=pass==0?source:2000;def.sprites[7]=def.sprites[0];
     character.wield=wield?def.sprites[0]:0;character.wield2=character.wield;
     Arrays.fill(g.pixelData,0x203040);c.drawNPC(0,30,30,80,90,3,0,100);images[pass]=g.pixelData.clone();
    }
    if(!Arrays.equals(images[0],images[1]))throw new AssertionError("Pixel mismatch id="+source+" custom="+sourceCustom+" color="+colour+" direction="+direction+" count="+count);
    if(direction<8&&Arrays.stream(images[0]).allMatch(p->p==0x203040))throw new AssertionError("Empty render");
    compared++;
   }
  }
  System.out.println("pixel-parity="+compared);
 }
}
'''
class MaskPolicyTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  rgb.NpcRgbFramesTest.setUpClass();cls.fixture=rgb.NpcRgbFramesTest();cls.classes=rgb.NpcRgbFramesTest.classes
  source=Path(cls.classes.name)/'NpcMaskParity.java';source.write_text(HARNESS)
  subprocess.run(['javac','-cp',str(rgb.helper.CLIENT),'-d',cls.classes.name,str(source)],check=True)
 @classmethod
 def tearDownClass(cls):rgb.NpcRgbFramesTest.tearDownClass()
 def setUp(self):self.addCleanup(self.fixture.doCleanups)
 def test_paired_private_capability(self):
  for jar in [rgb.helper.CLIENT,rgb.helper.SERVER]:
   with zipfile.ZipFile(jar) as z:self.assertIn(b"World-Builder-Npc-Mask-Policy: npc-mask-policy-v1",z.read("META-INF/MANIFEST.MF"))
 def test_actual_renderer_parity(self):
  p=subprocess.run(['java','-cp',f'{self.classes.name}:{rgb.helper.CLIENT}','orsc.NpcMaskParity'],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('pixel-parity=11520',p.stdout)
 def test_registry_policy_validation_both_roles(self):
  for mutation in [None,'unknown','forged','partial','type','range','nonrgb']:
   with self.subTest(mutation=mutation):
    workspace,bundle,m=self.fixture.rgb_bundle()
    if mutation=='nonrgb':workspace,bundle,m,_=self.fixture.bundle()
    path=bundle/'manifest.json'
    rp=next(bundle/x['bundleRelativePath'] for x in m['files'] if 'npc-animation' in x['bundleRelativePath'])
    doc=json.loads(rp.read_text());row=doc['animations'][0];row.update(npcMaskPolicy='literal-and-skin',sourceAnimationId=230,sourceCustomSprites=True)
    if mutation=='unknown':row['npcMaskPolicy']='guess'
    if mutation=='forged':row['npcMaskPolicy']='top-and-skin'
    if mutation=='partial':row.pop('sourceAnimationId')
    if mutation=='type':row['sourceCustomSprites']='true'
    if mutation=='range':row['sourceAnimationId']=65536
    rp.write_text(json.dumps(doc))
    for item in m['files']:
     data=(bundle/item['bundleRelativePath']).read_bytes();item['size']=len(data);item['sha256']=hashlib.sha256(data).hexdigest()
    m['bundleFingerprintSha256']='0'*64;m['bundleFingerprintSha256']=hashlib.sha256(b'world-builder-project-content-bundle-v3\n'+rgb.helper.canonical(m)).hexdigest();path.write_text(json.dumps(m))
    args=[str(workspace),str(bundle),m['bundleFingerprintSha256'],m['definitionFingerprintSha256'],m['assetFingerprintSha256'],m['itemVisualFingerprintSha256']]
    for name,jar,extra in [('NpcRgbHarness',rgb.helper.CLIENT,['0','2000',str(rgb.helper.CLIENT)]),('NpcAnimationV1ServerHarness',rgb.helper.SERVER,[])]:
     p=subprocess.run(['java','-cp',f'{self.classes.name}:{jar}',name,*args,*extra],capture_output=True,text=True)
     self.assertEqual(p.returncode==0,mutation is None,p.stdout+p.stderr)
if __name__=='__main__':unittest.main()
