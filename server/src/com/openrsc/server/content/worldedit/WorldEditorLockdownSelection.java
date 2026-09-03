package com.openrsc.server.content.worldedit;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Server-authoritative reconstruction of the bounded Lockdown selection contract. */
public final class WorldEditorLockdownSelection {
	private WorldEditorLockdownSelection() {}

	public static int[][] tiles(int mode,int[][] points,int maximumTiles){
		if(points==null||points.length<1||points.length>256)throw new IllegalArgumentException("Lockdown requires 1..256 selections.");
		if(mode==0)return unique(points,maximumTiles);
		if(mode!=1)throw new IllegalArgumentException("Lockdown selection mode is invalid.");
		if(points.length==1)return unique(points,maximumTiles);
		if(points.length==2)return line(points[0],points[1],maximumTiles);
		return polygon(points,maximumTiles);
	}
	private static int[][] unique(int[][] points,int maximumTiles){Map<Long,int[]> result=new LinkedHashMap<Long,int[]>();for(int[] point:points){validate(point);long key=((long)point[0]<<32)^(point[1]&0xffffffffL);if(!result.containsKey(key))result.put(key,new int[]{point[0],point[1]});if(result.size()>maximumTiles)throw new IllegalArgumentException("Lockdown protects too many tiles.");}return result.values().toArray(new int[result.size()][2]);}
	private static int[][] line(int[] first,int[] second,int maximumTiles){validate(first);validate(second);List<int[]> result=new ArrayList<int[]>();int x=first[0],y=first[1],tx=second[0],ty=second[1],dx=Math.abs(tx-x),sx=x<tx?1:-1,dy=-Math.abs(ty-y),sy=y<ty?1:-1,error=dx+dy;while(true){if(result.size()>=maximumTiles)throw new IllegalArgumentException("Lockdown line protects too many tiles.");result.add(new int[]{x,y});if(x==tx&&y==ty)break;int doubled=error*2;if(doubled>=dy){error+=dy;x+=sx;}if(doubled<=dx){error+=dx;y+=sy;}}return result.toArray(new int[result.size()][2]);}
	private static int[][] polygon(int[][] points,int maximumTiles){for(int i=0;i<points.length;i++){validate(points[i]);for(int j=0;j<i;j++)if(points[i][0]==points[j][0]&&points[i][1]==points[j][1])throw new IllegalArgumentException("Lockdown marker coordinate is repeated.");}long area=0L;for(int i=0;i<points.length;i++){int[] a=points[i],b=points[(i+1)%points.length];area+=(long)a[0]*b[1]-(long)b[0]*a[1];}if(area==0L)throw new IllegalArgumentException("Lockdown polygon is degenerate.");for(int first=0;first<points.length;first++){int firstNext=(first+1)%points.length;for(int second=first+1;second<points.length;second++){int secondNext=(second+1)%points.length;if(first==second||firstNext==second||secondNext==first)continue;if(intersects(points[first],points[firstNext],points[second],points[secondNext]))throw new IllegalArgumentException("Lockdown polygon self-intersects.");}}List<int[]> result=new ArrayList<int[]>();int minX=Integer.MAX_VALUE,maxX=Integer.MIN_VALUE,minY=Integer.MAX_VALUE,maxY=Integer.MIN_VALUE;for(int[] point:points){minX=Math.min(minX,point[0]);maxX=Math.max(maxX,point[0]);minY=Math.min(minY,point[1]);maxY=Math.max(maxY,point[1]);}if((long)maxX-minX>4096L||(long)maxY-minY>4096L)throw new IllegalArgumentException("Lockdown exceeds 4,096 tiles per axis.");for(int x=minX;x<=maxX;x++)for(int y=minY;y<=maxY;y++){if(!owns(points,x,y))continue;if(result.size()>=maximumTiles)throw new IllegalArgumentException("Lockdown protects too many tiles.");result.add(new int[]{x,y});}if(result.isEmpty())throw new IllegalArgumentException("Lockdown owns no tile centers.");return result.toArray(new int[result.size()][2]);}
	private static boolean owns(int[][] points,int x,int y){long px=2L*x+1L,py=2L*y+1L;boolean inside=false;for(int i=0,j=points.length-1;i<points.length;j=i++){long ax=2L*points[j][0]+1L,ay=2L*points[j][1]+1L,bx=2L*points[i][0]+1L,by=2L*points[i][1]+1L;if((bx-ax)*(py-ay)==(by-ay)*(px-ax)&&px>=Math.min(ax,bx)&&px<=Math.max(ax,bx)&&py>=Math.min(ay,by)&&py<=Math.max(ay,by))return true;if((ay>py)!=(by>py)){long left=(px-ax)*(by-ay),right=(bx-ax)*(py-ay);if(by>ay?left<right:left>right)inside=!inside;}}return inside;}
	private static boolean intersects(int[] a,int[] b,int[] c,int[] d){long o1=orient(a,b,c),o2=orient(a,b,d),o3=orient(c,d,a),o4=orient(c,d,b);if(o1==0&&between(a,b,c)||o2==0&&between(a,b,d)||o3==0&&between(c,d,a)||o4==0&&between(c,d,b))return true;return(o1<0)!=(o2<0)&&(o3<0)!=(o4<0);}
	private static long orient(int[] a,int[] b,int[] c){return((long)b[0]-a[0])*((long)c[1]-a[1])-((long)b[1]-a[1])*((long)c[0]-a[0]);}
	private static boolean between(int[] a,int[] b,int[] p){return p[0]>=Math.min(a[0],b[0])&&p[0]<=Math.max(a[0],b[0])&&p[1]>=Math.min(a[1],b[1])&&p[1]<=Math.max(a[1],b[1]);}
	private static void validate(int[] point){if(point==null||point.length!=2||point[0]<0||point[0]>32767||point[1]<0||point[1]>32767)throw new IllegalArgumentException("Lockdown selection contains an invalid tile.");}
}
