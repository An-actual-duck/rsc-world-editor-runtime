#!/usr/bin/env python3
"""Reject malformed semantic definitions in the actual client and server XML loaders."""
from pathlib import Path
import subprocess
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[2]
original='<TileDef><colour>3</colour><unknown>2</unknown><objectType>0</objectType></TileDef>'
base='<TileDef><colour>0</colour><unknown>0</unknown><objectType>0</objectType><worldBuilderMaterial>base-color-v1</worldBuilderMaterial></TileDef>'
partner='<TileDef><colour>3</colour><unknown>2</unknown><objectType>1</objectType><worldBuilderSourceOverlay>1</worldBuilderSourceOverlay></TileDef>'
bad=[base.replace('base-color-v1','unknown-v1'),base.replace('base-color-v1',''),base.replace('<unknown>0','<unknown>2'),base.replace('</TileDef>','<worldBuilderSourceOverlay>1</worldBuilderSourceOverlay></TileDef>'),partner.replace('>1</worldBuilderSourceOverlay>','>0</worldBuilderSourceOverlay>'),partner.replace('>1</worldBuilderSourceOverlay>','>2</worldBuilderSourceOverlay>'),partner.replace('<colour>3','<colour>4'),partner.replace('</TileDef>','<worldBuilderSourceOverlay>1</worldBuilderSourceOverlay></TileDef>'),base.replace('</TileDef>','<worldBuilderMaterial>base-color-v1</worldBuilderMaterial></TileDef>')]
java='''import java.lang.reflect.*;import java.nio.file.*;public class FloorMetadataProbe{public static void main(String[]a)throws Exception{Class<?> c=Class.forName(a[0]);Method m=c.getDeclaredMethod("loadProjectTiles",Path.class);m.setAccessible(true);for(int i=1;i<a.length;i++){boolean reject=false;try{m.invoke(null,Paths.get(a[i]));}catch(InvocationTargetException e){reject=true;}if(reject!=(i>1))throw new AssertionError("loader validation mismatch: "+a[i]);}System.out.println("PASS strict floor metadata "+a[0]);}}'''
with tempfile.TemporaryDirectory(prefix='floor-metadata-') as tmp:
    out=Path(tmp);source=out/'FloorMetadataProbe.java';source.write_text(java)
    subprocess.run(['javac','-d',tmp,str(source)],check=True)
    files=[]
    for i,rows in enumerate([original+base+partner]+[original+x for x in bad]+[original+partner+partner.replace('>1</worldBuilderSourceOverlay>','>2</worldBuilderSourceOverlay>'),original*249+base]):
        p=out/f'{i}.xml';p.write_text('<TileDef-array>'+rows+'</TileDef-array>');files.append(str(p))
    for jar,handler in [('Client_Base/Open_RSC_Client.jar','com.openrsc.client.entityhandling.EntityHandler'),('server/core.jar','com.openrsc.server.external.EntityHandler')]:
        with zipfile.ZipFile(ROOT/jar) as archive:
            assert 'World-Builder-Floor-Semantics: standard-floors-v1' in archive.read('META-INF/MANIFEST.MF').decode().splitlines()
        subprocess.run(['java','-cp',tmp+':'+str(ROOT/jar),'FloorMetadataProbe',handler]+files,check=True,cwd=ROOT)
