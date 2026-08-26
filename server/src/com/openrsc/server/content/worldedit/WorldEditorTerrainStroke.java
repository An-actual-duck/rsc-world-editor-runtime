package com.openrsc.server.content.worldedit;

/** Pure bounds and draft-size accounting for authoritative terrain brush strokes. */
public final class WorldEditorTerrainStroke {
	public static final int MAX_TILES = 64;
	public static final int MAX_OPERATION_TILES = 4096;
	private static final int BRUSH_TILES = 9;
	private WorldEditorTerrainStroke() {}
	public static final class RectanglePlan {
		public final int[][] coordinates;
		public final int[] fieldMasks;
		private RectanglePlan(int[][] coordinates,int[] fieldMasks){this.coordinates=coordinates;this.fieldMasks=fieldMasks;}
	}

	public static int[][] coordinates(int centerX,int centerY,int brushSize,int fieldMask) {
		if(brushSize!=1&&brushSize!=3)throw new IllegalArgumentException("Terrain brush must be 1x1 or 3x3.");
		if(brushSize==1)return new int[][]{{centerX,centerY}};
		int[][] tiles=new int[BRUSH_TILES][2];tiles[0][0]=centerX;tiles[0][1]=centerY;int at=1;
		for(int dx=-1;dx<=1;dx++)for(int dy=-1;dy<=1;dy++)if(dx!=0||dy!=0){tiles[at][0]=centerX+dx;tiles[at++][1]=centerY+dy;}
		return tiles;
	}
	public static int[][] validateTiles(int[][] requested){
		return validateTiles(requested,MAX_TILES,"Terrain stroke must contain 1 to 64 tiles.");
	}
	public static int[][] validateOperationTiles(int[][] requested){
		return validateTiles(requested,MAX_OPERATION_TILES,"Terrain operation must contain 1 to 4096 tiles.");
	}
	private static int[][] validateTiles(int[][] requested,int maximum,String boundsMessage){
		if(requested==null||requested.length<1||requested.length>maximum)throw new IllegalArgumentException(boundsMessage);
		int[][] copy=new int[requested.length][2];java.util.HashSet<Long> unique=new java.util.HashSet<Long>();
		for(int i=0;i<requested.length;i++){
			if(requested[i]==null||requested[i].length!=2)throw new IllegalArgumentException("Terrain stroke tile coordinate is malformed.");
			int x=requested[i][0],y=requested[i][1];long key=((long)x<<32)^(y&0xffffffffL);
			if(!unique.add(key))throw new IllegalArgumentException("Terrain stroke contains duplicate tiles.");copy[i][0]=x;copy[i][1]=y;
		}
		return copy;
	}
	public static int[][] lineFootprint(int startX,int startY,int endX,int endY,int brushSize){
		if(brushSize!=1&&brushSize!=3&&brushSize!=5&&brushSize!=7)
			throw new IllegalArgumentException("Terrain line brush must be 1x1, 3x3, 5x5, or 7x7.");
		java.util.LinkedHashMap<Long,int[]> unique=new java.util.LinkedHashMap<Long,int[]>();
		int x=startX,y=startY,dx=Math.abs(endX-startX),sx=startX<endX?1:-1;
		int dy=-Math.abs(endY-startY),sy=startY<endY?1:-1,error=dx+dy,radius=brushSize/2;
		while(true){
			addLineTile(unique,x,y);
			for(int ox=-radius;ox<=radius;ox++)for(int oy=-radius;oy<=radius;oy++){
				if(ox==0&&oy==0)continue;
				int tileX=x+ox,tileY=y+oy;long key=((long)tileX<<32)^(tileY&0xffffffffL);
				if(!unique.containsKey(key))addLineTile(unique,tileX,tileY);
			}
			if(x==endX&&y==endY)break;int doubled=error*2;
			if(doubled>=dy){error+=dy;x+=sx;}if(doubled<=dx){error+=dx;y+=sy;}
		}
		return unique.values().toArray(new int[unique.size()][]);
	}
	private static void addLineTile(java.util.LinkedHashMap<Long,int[]> unique,int x,int y){
		long key=((long)x<<32)^(y&0xffffffffL);if(unique.containsKey(key))return;
		if(unique.size()>=MAX_OPERATION_TILES)throw new IllegalArgumentException("Terrain line exceeds 4096 unique tiles.");
		unique.put(key,new int[]{x,y});
	}
	public static RectanglePlan rectanglePlan(int startX,int startY,int endX,int endY,boolean fill,
		int baseFieldMask,boolean smartWalls,boolean paintSmartWall){
		if(baseFieldMask<0||(baseFieldMask&~127)!=0)throw new IllegalArgumentException("Terrain rectangle capability is invalid.");
		if(smartWalls&&(baseFieldMask&112)!=0)throw new IllegalArgumentException("Smart Walls cannot include raw wall fields.");
		if(!smartWalls&&paintSmartWall)throw new IllegalArgumentException("Smart wall placement requires Smart Walls.");
		if(baseFieldMask==0&&!paintSmartWall)throw new IllegalArgumentException("Terrain rectangle has no selected fields.");
		int minX=Math.min(startX,endX),maxX=Math.max(startX,endX),minY=Math.min(startY,endY),maxY=Math.max(startY,endY);
		long width=(long)maxX-minX+1L,height=(long)maxY-minY+1L;
		long footprint=fill?width*height:width==1L||height==1L?width*height:width*2L+height*2L-4L;
		long possible=footprint+(paintSmartWall?width*2L+height*2L:0L);
		if(footprint<1L||possible>MAX_OPERATION_TILES*2L+4L)throw new IllegalArgumentException("Terrain rectangle exceeds 4096 unique tiles.");
		java.util.LinkedHashMap<Long,int[]> tiles=new java.util.LinkedHashMap<Long,int[]>();
		java.util.LinkedHashMap<Long,Integer> masks=new java.util.LinkedHashMap<Long,Integer>();
		if(baseFieldMask!=0){
			if(fill){for(int x=minX;;x++){for(int y=minY;;y++){addRectangleTile(tiles,masks,x,y,baseFieldMask);if(y==maxY)break;}if(x==maxX)break;}}
			else{
				for(int x=minX;;x++){addRectangleTile(tiles,masks,x,minY,baseFieldMask);if(maxY!=minY)addRectangleTile(tiles,masks,x,maxY,baseFieldMask);if(x==maxX)break;}
				if(height>2L)for(int y=minY+1;y<maxY;y++){addRectangleTile(tiles,masks,minX,y,baseFieldMask);if(maxX!=minX)addRectangleTile(tiles,masks,maxX,y,baseFieldMask);}
			}
		}
		if(paintSmartWall){
			int southY=Math.addExact(maxY,1),eastX=Math.addExact(maxX,1);
			for(int x=minX;;x++){addRectangleTile(tiles,masks,x,minY,32);addRectangleTile(tiles,masks,x,southY,32);if(x==maxX)break;}
			for(int y=minY;;y++){addRectangleTile(tiles,masks,minX,y,16);addRectangleTile(tiles,masks,eastX,y,16);if(y==maxY)break;}
		}
		int[][] coordinates=tiles.values().toArray(new int[tiles.size()][]);int[] fieldMasks=new int[coordinates.length];int at=0;
		for(Integer mask:masks.values())fieldMasks[at++]=mask.intValue();return new RectanglePlan(coordinates,fieldMasks);
	}
	private static void addRectangleTile(java.util.LinkedHashMap<Long,int[]> tiles,java.util.LinkedHashMap<Long,Integer> masks,int x,int y,int fieldMask){
		long key=((long)x<<32)^(y&0xffffffffL);Integer previous=masks.get(key);
		if(previous!=null){masks.put(key,Integer.valueOf(previous.intValue()|fieldMask));return;}
		if(tiles.size()>=MAX_OPERATION_TILES)throw new IllegalArgumentException("Terrain rectangle exceeds 4096 unique tiles.");
		tiles.put(key,new int[]{x,y});masks.put(key,Integer.valueOf(fieldMask));
	}

	public static int projectedDraftSize(int currentSize,boolean[] draftedBefore,boolean[] draftedAfter) {
		return projectedDraftSize(currentSize,draftedBefore,draftedAfter,MAX_TILES);
	}
	public static int projectedOperationDraftSize(int currentSize,boolean[] draftedBefore,boolean[] draftedAfter) {
		return projectedDraftSize(currentSize,draftedBefore,draftedAfter,MAX_OPERATION_TILES);
	}
	private static int projectedDraftSize(int currentSize,boolean[] draftedBefore,boolean[] draftedAfter,int maximum) {
		if(currentSize<0||draftedBefore==null||draftedAfter==null||draftedBefore.length!=draftedAfter.length||draftedBefore.length>maximum)
			throw new IllegalArgumentException("Invalid terrain stroke draft accounting.");
		int projected=currentSize;
		for(int i=0;i<draftedBefore.length;i++){
			if(draftedBefore[i]&&!draftedAfter[i])projected--;else if(!draftedBefore[i]&&draftedAfter[i])projected++;
		}
		if(projected<0)throw new IllegalArgumentException("Terrain stroke draft accounting underflow.");
		return projected;
	}

	/** Calculates a complete v2 elevation stroke without mutating caller state. */
	public static int[] elevationTargets(
		int[] current, int operation, int absolute, int step) {
		if (current == null || current.length < 1 || current.length > MAX_TILES
			|| operation < 0 || operation > 2 || absolute < 0 || absolute > 65535
			|| step < 1 || step > 65535) {
			throw new IllegalArgumentException("Elevation operation capability v2 is invalid.");
		}
		int[] result = new int[current.length];
		for (int index = 0; index < current.length; index++) {
			if (current[index] < 0 || current[index] > 65535) {
				throw new IllegalArgumentException("Current elevation is outside 0..65535.");
			}
			long candidate = operation == 0 ? absolute
				: (long)current[index] + (operation == 1 ? step : -step);
			if (candidate < 0L || candidate > 65535L) {
				throw new IllegalArgumentException(
					"Elevation stroke refused atomically: relative operation exceeds 0..65535.");
			}
			result[index] = (int)candidate;
		}
		return result;
	}
}
