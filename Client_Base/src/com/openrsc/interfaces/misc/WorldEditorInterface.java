package com.openrsc.interfaces.misc;

import com.openrsc.interfaces.InputListener;
import com.openrsc.interfaces.NCustomComponent;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.client.model.Sprite;
import orsc.Config;
import orsc.WorldBuilderClientProfile;
import orsc.WorldBuilderRegionBundleClientBridge;
import orsc.WorldBuilderRegionBundleFileDialog;
import orsc.WorldBuilderRegionCopyClientBridge;
import orsc.WorldBuilderRegionPasteClientBridge;
import orsc.WorldBuilderTerrainOverlay;
import orsc.mudclient;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Desktop-only world editor shell and the first command-backed entity tools. */
public final class WorldEditorInterface extends NCustomComponent {
	private static final int TERRAIN_BATCH_LIMIT=64,TERRAIN_DRAG_LIMIT=4096;
	private static final long TERRAIN_DRAG_FLUSH_NANOS=75000000L,TERRAIN_STROKE_TIMEOUT_NANOS=10000000000L;
	private static final long DEFERRED_SAVE_TIMEOUT_NANOS=10000000000L;
	private static final int MAX_GROUND_ITEM_AMOUNT=99999;
	private static final int DOCK_WIDTH=70,DOCK_HEIGHT=396,FLYOUT_WIDTH=180,FLYOUT_GAP=4,EXPANDED_WIDTH=455;
	private static final int BROWSER_WIDTH=390,BROWSER_HEIGHT=330,BROWSER_GAP=4;
	private static final int BROWSER_CARD_WIDTH=178,BROWSER_CARD_HEIGHT=42,BROWSER_CARD_STEP_Y=45,BROWSER_GRID_Y=100;
	private static final int DOCK_LEFT=6,DOCK_RIGHT=36,DOCK_TOP=4,DOCK_STEP=30;
	public enum Mode { NAVIGATE, INSPECT, TERRAIN, SCENERY, NPC, ITEMS, REGION }
	public enum SceneryTool { PLACE, MOVE, ROTATE, REMOVE }
	public enum NpcTool { PLACE, REMOVE }
	public enum GroundItemTool { PLACE, REMOVE }
	public enum TerrainTool { FREEHAND, LINE, RECTANGLE }
	public enum RegionTool { COPY, CUT, PASTE }
	private static final String[] TABS={"Navigate","Inspect","Terrain","Scenery","NPC","Items","Regions"};
	private final mudclient mc;
	private final WorldEditorIconRegistry icons=new WorldEditorIconRegistry();
	private final WorldEditorToolbarState toolbar=new WorldEditorToolbarState();
	private final WorldEditorDefinitionBrowser definitionBrowser=new WorldEditorDefinitionBrowser();
	private final WorldEditorEntityEditTracker entityEditTracker=new WorldEditorEntityEditTracker();
	private int definitionBrowserTerrainField=0;
	private Mode mode=Mode.NAVIGATE;
	private long sessionId;
	private int nextSequence;
	private String inspectionStatus="Nothing inspected yet";
	private String[] inspectionDetails=new String[0];
	private String inspectionKind="";
	private String copiedInspectionKind="";
	private String[] copiedInspectionDetails=new String[0];
	private boolean copyNextInspection=false;
	private int[] copiedTerrainFields;
	private int[] inspectedTerrainFields;
	private int lastClickedX=-1,lastClickedY=-1,lastClickedLevel=0,brushX=-1,brushY=-1,brushLevel=0;
	private String teleportX="",teleportY="",teleportLevel="0";
	private int coordinateFocus=0;
	private boolean replaceFocusedText=false;
	private boolean clickTeleportPreferred=false;
	private SceneryTool sceneryTool=SceneryTool.PLACE;
	private int sceneryMoveSourceX=-1,sceneryMoveSourceY=-1;
	private int sceneryMoveSourceId=-1,sceneryMoveSourceDirection=0;
	private int sceneryMoveHoverX=-1,sceneryMoveHoverY=-1;
	private NpcTool npcTool=NpcTool.PLACE;
	private GroundItemTool groundItemTool=GroundItemTool.PLACE;
	private int sceneryId=0,npcId=0,npcRadius=0,npcRespawnSeconds=-1;
	private String sceneryIdText="0",npcIdText="0",npcRadiusText="0",npcRespawnText="-1";
	private int groundItemId=10,groundItemAmount=1,groundItemRespawnSeconds=30;
	private String groundItemIdText="10",groundItemAmountText="1",groundItemRespawnText="30";
	private boolean paintElevation=false,paintFloorColor=true,paintFloorTexture=false;
	private int terrainElevation=0,terrainFloorColor=0,terrainFloorTexture=0;
	private String terrainElevationText="0",terrainFloorColorText="0",terrainFloorTextureText="0";
	private int terrainElevationOperation=0,terrainElevationStep=1;
	private String terrainElevationStepText="1";
	private boolean terrainStructureTab=false,paintRoof=false;
	private final WorldEditorRectangleOptions rectangleOptions=new WorldEditorRectangleOptions();
	private int terrainRoof=0,terrainEastWall=0,terrainNorthWall=0,terrainDiagonalWall=0,terrainDiagonalOrientation=0;
	private String terrainRoofText="0",terrainEastWallText="0",terrainNorthWallText="0",terrainDiagonalWallText="0";
	private int terrainSmartWall=0;
	private String terrainSmartWallText="0";
	private int terrainBrushSize=1,terrainStrokeMask=0;
	private long terrainStrokeStartedNanos=0L;
	private int terrainStrokeElevation=0,terrainStrokeColor=0,terrainStrokeTexture=0;
	private int terrainStrokeElevationOperation=0,terrainStrokeElevationStep=1;
	private int terrainHistoryNextToken=1,terrainStrokeHistoryToken=0;
	private boolean terrainHistoryCanUndo=false,terrainHistoryCanRedo=false;
	private boolean terrainHistoryPending=false;
	private int terrainHistoryTotal=0,terrainHistoryReceived=0;
	private int terrainStrokeRoof=0,terrainStrokeEastWall=0,terrainStrokeNorthWall=0,terrainStrokeDiagonal=0;
	private int[][] terrainStrokeTiles=null;
	private boolean terrainBuildMode=false,terrainDragActive=false,terrainDragReleasePending=false;
	private int terrainDragHoverX=-1,terrainDragHoverY=-1,terrainDragCenterX=-1,terrainDragCenterY=-1,terrainDragAccepted=0;
	private TerrainTool terrainTool=TerrainTool.FREEHAND;
	private int terrainLineAnchorX=-1,terrainLineAnchorY=-1;
	private int[][] terrainLineCommitTiles=null;
	private int[] terrainLineCommitMasks=null;
	private int terrainLineReceived=0;
	private long terrainLineLastResponseNanos=0L;
	private String terrainGestureLabel="Brush";
	private long terrainDragAckMillis=0L,terrainDragRebuildMillis=0L,terrainDragPendingSinceNanos=0L;
	private final LinkedHashMap<Long,int[]> terrainDragPending=new LinkedHashMap<Long,int[]>();
	private final HashSet<Long> terrainDragSeen=new HashSet<Long>();
	private int dragX=-1,dragY=-1;
	private int compactMouseX=-1,compactMouseY=-1,terrainActiveField=7;
	private String toolbarTooltip="";
	private boolean keyboardShortcutsEnabled=true;
	private boolean unsavedChanges=false,saveRequested=false,saveAfterPendingEdits=false,closeArmed=false;
	private long deferredSaveProgressNanos=0L;
	private long lastAckMillis=0L,lastRebuildMillis=0L;
	private final WorldBuilderRegionCopyClientBridge regionCopyBridge=
		new WorldBuilderRegionCopyClientBridge();
	private final WorldBuilderRegionPasteClientBridge regionPasteBridge=
		new WorldBuilderRegionPasteClientBridge();
	private final WorldBuilderRegionBundleClientBridge regionBundleBridge=
		new WorldBuilderRegionBundleClientBridge();
	private final WorldBuilderRegionBundleFileDialog regionBundleDialog=
		new WorldBuilderRegionBundleFileDialog();
	private RegionTool regionTool=RegionTool.COPY;
	private final List<WorldBuilderRegionPasteClientBridge.Snapshot> regionLibrary=
		new ArrayList<WorldBuilderRegionPasteClientBridge.Snapshot>();
	private int regionLibraryIndex=-1;
	private int regionPasteX=-1,regionPasteY=-1,regionPasteLevel=0;
	private int[][] regionPastePreviewTiles=new int[0][2];
	private int[][] regionPasteCollisionTiles=new int[0][2];
	private String regionPastePlanHash="";
	private boolean regionPasteBlocked=false,regionPasteOverwrite=false;
	private boolean regionPasteOverwritePrompted=false,regionPasteOverwriteArmed=false;
	private String regionCutSnapshotId="",regionCutPlanHash="";
	private boolean regionCutBlocked=false;
	private final List<int[]> regionMarkers=new ArrayList<int[]>();
	private int regionHoverX=-1,regionHoverY=-1;
	private boolean regionClosed=false;
	private String regionName="Region snapshot";
	private String lastRegionSnapshotId="",lastRegionSnapshotName="";
	private String regionClipboardSnapshotId="",regionClipboardSnapshotName="";
	private int lastRegionTileCount=0,lastRegionPlacementCount=0,lastRegionCrossingCount=0;
	private int[][] regionPreviewTiles=new int[0][2];
	private String regionLibraryRefreshStatus="";
	private String regionLibraryPreferredSnapshotId="";

	public WorldEditorInterface(mudclient client) {
		super(client);mc=client;setLocation(8,8);setSize(DOCK_WIDTH+FLYOUT_GAP+FLYOUT_WIDTH,DOCK_HEIGHT);setVisible(false);setIsOverlay(true);
		setInputListener(new InputListener(){
			@Override public boolean onMouseDown(int mx,int my,int down,int click){return handleMouse(mx,my,down,click);}
			@Override public boolean onCharTyped(char c,int key){return handleKey(c,key);}
			@Override public boolean onMouseMove(int mx,int my){compactMouseX=mx;compactMouseY=my;return false;}
		});
	}

	public void open(long id,int sequence){
		if(Config.isAndroid())return;
		sessionId=id;nextSequence=sequence;mode=Mode.NAVIGATE;terrainTool=TerrainTool.FREEHAND;clearTerrainLine();clearSceneryMove();clearRegionSelection();resetRegionPaste();regionCopyBridge.reset();regionPasteBridge.reset();regionBundleBridge.reset();regionBundleDialog.reset();toolbar.reset();definitionBrowser.close();icons.initialize();
		normalizeProjectBoundSelections();
		int x=mc.getEditorPlayerWorldX(),y=mc.getEditorPlayerWorldY(),level=mc.getEditorPlayerWorldLevel();
		brushX=x;brushY=y;brushLevel=level;teleportX=String.valueOf(x);teleportY=String.valueOf(y);teleportLevel=String.valueOf(level);
		clickTeleportPreferred=false;keyboardShortcutsEnabled=true;unsavedChanges=false;saveRequested=false;saveAfterPendingEdits=false;deferredSaveProgressNanos=0L;closeArmed=false;entityEditTracker.reset();
		terrainHistoryNextToken=1;terrainStrokeHistoryToken=0;terrainHistoryCanUndo=false;terrainHistoryCanRedo=false;terrainHistoryPending=false;terrainHistoryTotal=terrainHistoryReceived=0;
		setTerrainBuildMode(false);mc.setWorldEditorNavigateClickTeleport(false);clearTerrainDrag();updatePresentationBounds();setVisible(true);
	}
	public void closeFromServer(){setTerrainBuildMode(false);mc.setWorldEditorNavigateClickTeleport(false);setVisible(false);sessionId=0;coordinateFocus=0;clearTerrainLine();clearTerrainDrag();clearSceneryMove();clearRegionSelection();resetRegionPaste();regionCopyBridge.reset();regionPasteBridge.reset();regionBundleBridge.reset();regionBundleDialog.reset();definitionBrowser.close();toolbar.reset();}
	public boolean isEditorOpen(){return isVisible()&&sessionId!=0;}
	public boolean isKeyboardCaptureActive(){return isEditorOpen()&&(keyboardShortcutsEnabled||coordinateFocus!=0||definitionBrowser.isOpen());}
	public boolean isKeyboardShortcutMode(){return isEditorOpen()&&keyboardShortcutsEnabled;}
	public boolean isInspecting(){return isEditorOpen()&&mode==Mode.INSPECT;}
	public boolean isNavigating(){return isEditorOpen()&&mode==Mode.NAVIGATE;}
	public boolean isTerrainPainting(){return isEditorOpen()&&(!isLayeredReview()||isLayeredPlacementDraftLevel())&&mode==Mode.TERRAIN;}
	public boolean isTerrainLineTool(){return isTerrainPainting()&&terrainTool==TerrainTool.LINE;}
	public String terrainPaintActionLabel(){if(terrainTool==TerrainTool.LINE)return terrainLineAnchorX<0?"Set line anchor":"Commit terrain line";
		if(terrainTool==TerrainTool.RECTANGLE)return terrainLineAnchorX<0?"Set rectangle corner":"Commit terrain rectangle";return "Paint terrain";}
	public int terrainToolPreviewColor(){return terrainTool==TerrainTool.RECTANGLE?0x8fd14f:terrainTool==TerrainTool.LINE?0xffa52f:0x33d6ff;}
	public int[][] terrainToolPreviewTiles(){
		if(terrainLineCommitTiles!=null)return terrainLineCommitTiles;
		if(!isTerrainPainting()||terrainDragHoverX<0||terrainDragHoverY<0)return new int[0][2];
		try{return terrainTool==TerrainTool.LINE&&terrainLineAnchorX>=0
			?WorldEditorTerrainBrush.lineFootprint(terrainLineAnchorX,terrainLineAnchorY,terrainDragHoverX,terrainDragHoverY,terrainBrushSize,TERRAIN_DRAG_LIMIT)
			:terrainTool==TerrainTool.RECTANGLE&&terrainLineAnchorX>=0
				?WorldEditorTerrainBrush.rectangleFootprint(terrainLineAnchorX,terrainLineAnchorY,terrainDragHoverX,terrainDragHoverY,rectangleOptions.isFill(),TERRAIN_DRAG_LIMIT)
				:WorldEditorTerrainBrush.centeredFootprint(terrainDragHoverX,terrainDragHoverY,terrainBrushSize);
		}catch(IllegalArgumentException ignored){return new int[0][2];}
	}
	public int[] terrainLineAnchorTile(){return terrainTool!=TerrainTool.FREEHAND&&terrainLineAnchorX>=0?new int[]{terrainLineAnchorX,terrainLineAnchorY}:null;}
	public boolean isSceneryPlacing(){return isEditorOpen()&&definitionAllowed("scenery",sceneryId)&&(!isLayeredReview()||isLayeredSceneryDraftLevel())&&mode==Mode.SCENERY&&sceneryTool==SceneryTool.PLACE;}
	public boolean isSceneryMoving(){return isEditorOpen()&&(!isLayeredReview()||isLayeredSceneryDraftLevel())&&mode==Mode.SCENERY&&sceneryTool==SceneryTool.MOVE;}
	public boolean isSceneryMoveArmed(){return isSceneryMoving()&&sceneryMoveSourceX>=0&&sceneryMoveSourceY>=0;}
	public boolean isSceneryRotating(){return isEditorOpen()&&(!isLayeredReview()||isLayeredSceneryDraftLevel())&&mode==Mode.SCENERY&&sceneryTool==SceneryTool.ROTATE;}
	public boolean isSceneryRemoving(){return isEditorOpen()&&(!isLayeredReview()||isLayeredSceneryDraftLevel())&&mode==Mode.SCENERY&&sceneryTool==SceneryTool.REMOVE;}
	public boolean isNpcPlacing(){return isEditorOpen()&&definitionAllowed("npc",npcId)&&(!isLayeredReview()||isLayeredPlacementDraftLevel())&&mode==Mode.NPC&&npcTool==NpcTool.PLACE;}
	public boolean isNpcRemoving(){return isEditorOpen()&&(!isLayeredReview()||isLayeredPlacementDraftLevel())&&mode==Mode.NPC&&npcTool==NpcTool.REMOVE;}
	public boolean isGroundItemPlacing(){return isEditorOpen()&&definitionAllowed("item",groundItemId)&&isLayeredPlacementDraftLevel()&&mode==Mode.ITEMS&&groundItemTool==GroundItemTool.PLACE;}
	public boolean isGroundItemRemoving(){return isEditorOpen()&&isLayeredPlacementDraftLevel()&&mode==Mode.ITEMS&&groundItemTool==GroundItemTool.REMOVE;}
	public boolean isRegionSelecting(){return isEditorOpen()&&mode==Mode.REGION&&regionTool!=RegionTool.PASTE;}
	public boolean isRegionPasteSelectingDestination(){return isEditorOpen()&&mode==Mode.REGION&&regionTool==RegionTool.PASTE&&!regionPasteBridge.isPending()&&!isRegionSharingPending();}
	public boolean isRegionClosed(){return isRegionSelecting()&&regionClosed;}
	public boolean isRegionCopyPending(){return regionCopyBridge.isPending();}
	public int getSceneryId(){return sceneryId;}
	public int getNpcId(){return npcId;}
	public int getNpcRadius(){return npcRadius;}
	public int getNpcRespawnSeconds(){return npcRespawnSeconds;}
	public int getGroundItemId(){return groundItemId;}
	public int getGroundItemAmount(){return groundItemAmount;}
	public int getGroundItemRespawnSeconds(){return groundItemRespawnSeconds;}
	public boolean canPlaceSelectedScenery(){return definitionAllowed("scenery",sceneryId);}
	public boolean canPlaceSelectedNpc(){return definitionAllowed("npc",npcId);}
	public boolean canPlaceSelectedGroundItem(){return definitionAllowed("item",groundItemId);}
	public void selectScenery(int id){setSceneryId(id);}
	public void selectSceneryMoveSource(int worldX,int worldY,int id,int direction){
		if(!isSceneryMoving())return;sceneryMoveSourceX=worldX;sceneryMoveSourceY=worldY;sceneryMoveSourceId=id;sceneryMoveSourceDirection=direction;sceneryMoveHoverX=sceneryMoveHoverY=-1;
		recordWorldClick(worldX,worldY);inspectionStatus="Move selected: "+WorldEditorDefinitionCatalog.sceneryReference(id)+" at "+worldX+","+worldY+". Hover terrain and click its destination; Escape or right-click cancels.";closeArmed=false;
	}
	public boolean updateSceneryMovePointer(boolean secondaryDown,int worldX,int worldY){
		if(!isSceneryMoving())return false;if(secondaryDown&&isSceneryMoveArmed()){clearSceneryMove();inspectionStatus="Scenery move cancelled; the source was not changed.";return true;}
		if(!isSceneryMoveArmed())return false;sceneryMoveHoverX=worldX;sceneryMoveHoverY=worldY;return false;
	}
	public void commitSceneryMove(int destinationX,int destinationY){
		if(!isSceneryMoveArmed())return;if(entityEditTracker.isPending()){inspectionStatus="Wait for the authoritative scenery response before choosing another destination.";return;}if(destinationX==sceneryMoveSourceX&&destinationY==sceneryMoveSourceY){inspectionStatus="Choose a different destination; the source was not changed.";return;}
		sceneryMoveHoverX=destinationX;sceneryMoveHoverY=destinationY;requestEntityEdit(4,0,sceneryMoveSourceX,sceneryMoveSourceY,destinationX,destinationY,0,0);inspectionStatus="Moving scenery atomically; the source remains intact unless the destination is accepted.";
	}
	public int[][] sceneryMovePreviewTiles(){
		if(!isSceneryMoveArmed()||sceneryMoveHoverX<0||sceneryMoveHoverY<0)return new int[0][2];
		try{com.openrsc.client.entityhandling.defs.GameObjectDef definition=EntityHandler.getObjectDef(sceneryMoveSourceId);int width,height;
			if(sceneryMoveSourceDirection!=0&&sceneryMoveSourceDirection!=4){width=definition.getHeight();height=definition.getWidth();}else{width=definition.getWidth();height=definition.getHeight();}
			int minX=sceneryMoveHoverX,minY=sceneryMoveHoverY,maxX=minX+width-1,maxY=minY+height-1;
			if(definition.getType()==2||definition.getType()==3){if(sceneryMoveSourceDirection==0){width++;minX--;}if(sceneryMoveSourceDirection==2)height++;if(sceneryMoveSourceDirection==6){minY--;height++;}if(sceneryMoveSourceDirection==4)width++;maxX=sceneryMoveHoverX+width-1;maxY=sceneryMoveHoverY+height-1;}
			long tileCount=(long)(maxX-minX+1)*(maxY-minY+1);if(tileCount<1||tileCount>4096)return new int[][]{{sceneryMoveHoverX,sceneryMoveHoverY}};int[][] tiles=new int[(int)tileCount][2];int index=0;for(int x=minX;x<=maxX;x++)for(int y=minY;y<=maxY;y++){tiles[index][0]=x;tiles[index++][1]=y;}return tiles;
		}catch(Exception ignored){return new int[][]{{sceneryMoveHoverX,sceneryMoveHoverY}};}
	}
	public int[] sceneryMoveSourceTile(){return isSceneryMoveArmed()?new int[]{sceneryMoveSourceX,sceneryMoveSourceY}:null;}
	public int[] sceneryMoveDestinationTile(){return isSceneryMoveArmed()&&sceneryMoveHoverX>=0?new int[]{sceneryMoveHoverX,sceneryMoveHoverY}:null;}
	private void clearSceneryMove(){sceneryMoveSourceX=sceneryMoveSourceY=sceneryMoveSourceId=sceneryMoveHoverX=sceneryMoveHoverY=-1;sceneryMoveSourceDirection=0;}
	public void updateRegionSelectionPointer(int worldX,int worldY){if(!isRegionSelecting()||regionClosed)return;regionHoverX=worldX;regionHoverY=worldY;}
	public void addRegionMarker(int worldX,int worldY){
		if(!isRegionSelecting()||regionCopyBridge.isPending())return;if(regionClosed){inspectionStatus="Reopen or clear the selection before adding another marker.";return;}
		for(int[] marker:regionMarkers)if(marker[0]==worldX&&marker[1]==worldY){inspectionStatus="Marker coordinates must be unique; that tile is already selected.";return;}
		if(regionMarkers.size()>=256){inspectionStatus="A region selection is limited to 256 ordered markers.";return;}
		regionMarkers.add(new int[]{worldX,worldY});regionHoverX=worldX;regionHoverY=worldY;regionPreviewTiles=new int[0][2];
		inspectionStatus="Placed region marker "+regionMarkers.size()+" at "+worldX+","+worldY+". "+(regionMarkers.size()>=3?"Close the polygon when its order is correct.":"Place at least "+(3-regionMarkers.size())+" more marker"+(regionMarkers.size()==2?"":"s")+".");closeArmed=false;
	}
	private void removeLastRegionMarker(){
		if(regionCopyBridge.isPending()){inspectionStatus="Wait for Region Copy to finish before changing its selection.";return;}
		if(regionMarkers.isEmpty()){inspectionStatus="The region selection has no markers to remove.";return;}
		int[] removed=regionMarkers.remove(regionMarkers.size()-1);regionClosed=false;regionPreviewTiles=new int[0][2];clearRegionCutPlan();regionHoverX=removed[0];regionHoverY=removed[1];inspectionStatus="Removed the last region marker; "+regionMarkers.size()+" remain.";
	}
	private void closeRegionSelection(){
		if(regionCopyBridge.isPending())return;if(regionMarkers.size()<3){inspectionStatus="Place at least three ordered markers before closing the selection.";return;}
		try{int[][] markers=regionMarkerTiles();WorldEditorRegionSelection.validateClosed(markers);regionPreviewTiles=WorldEditorRegionSelection.ownedTiles(markers,65536);regionClosed=true;inspectionStatus="Selection stopped: "+regionPreviewTiles.length+" terrain tiles. Review the preview, then select Copy.";}
		catch(IllegalArgumentException invalid){regionClosed=false;regionPreviewTiles=new int[0][2];inspectionStatus="Region cannot close: "+invalid.getMessage();}
	}
	private void clearRegionSelection(){
		regionMarkers.clear();regionClosed=false;regionHoverX=regionHoverY=-1;regionPreviewTiles=new int[0][2];
		clearRegionCutPlan();
	}
	private void cancelRegionSelection(){if(regionCopyBridge.isPending()){inspectionStatus="Region Copy is already running; wait for its response.";return;}clearRegionSelection();inspectionStatus="Selection reset; the world and clipboard were unchanged.";}
	private void advanceRegionSelectionState(){
		if(regionCopyBridge.isPending()){inspectionStatus="Wait for Region Copy to finish before changing its selection.";return;}
		if(regionClosed){clearRegionSelection();inspectionStatus="Selection reset. Click terrain to place marker 1 and start again.";return;}
		if(regionMarkers.isEmpty()){inspectionStatus="Selection started. Click terrain to place marker 1, then continue around the boundary.";return;}
		closeRegionSelection();
	}
	private String regionSelectionActionLabel(){return regionClosed?"Reset":regionMarkers.isEmpty()?"Start":"Stop";}
	private String regionCutActionLabel(){if(regionCopyBridge.isPending())return "Working";if(regionCutBlocked)return "Blocked";return regionCutPlanHash.isEmpty()?"Cut":"Confirm Cut";}
	private String regionPasteActionLabel(){if(regionPasteBridge.isPending())return "Working";if(regionPasteBlocked)return "Blocked";if(regionPasteOverwriteArmed)return "Confirm";if(regionPasteOverwritePrompted)return "Overwrite?";return "Paste";}
	private void requestRegionCopy(){
		if(!regionClosed){inspectionStatus="Close a valid region selection before copying it.";return;}
		if(terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragActive||terrainDragReleasePending||entityEditTracker.isPending()){inspectionStatus="Wait for authoritative edit responses before copying the region.";return;}
		try{regionCopyBridge.submit(regionName,mc.getEditorPlayerWorldLevel(),regionMarkerTiles());mc.sendCommandString("copyregion");inspectionStatus="Saving pending edits, then copying the exact closed region...";closeArmed=false;}
		catch(Exception failure){inspectionStatus="Region Copy could not start: "+failure.getMessage();}
	}
	private void requestRegionCut(){
		if(!regionClosed){inspectionStatus="Close a valid region selection before cutting it.";return;}
		if(terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragActive||terrainDragReleasePending||entityEditTracker.isPending()){inspectionStatus="Wait for authoritative edit responses before cutting the region.";return;}
		if(regionCutBlocked){inspectionStatus="This Cut plan is blocked; reset or correct the selection before retrying.";return;}
		try{
			if(regionCutPlanHash.isEmpty()){
				regionCopyBridge.requestCutPreview(regionName,mc.getEditorPlayerWorldLevel(),regionMarkerTiles());
				mc.sendCommandString("cutregion");inspectionStatus="Saving pending edits and securing an exact reusable snapshot before Cut...";
			}else{
				regionCopyBridge.requestCutApply(regionCutSnapshotId,regionCutPlanHash);
				mc.sendCommandString("cutregion");inspectionStatus="Applying the exact atomic Cut plan...";
			}
			closeArmed=false;
		}catch(Exception failure){inspectionStatus="Region Cut could not start: "+failure.getMessage();}
	}
	private void pollRegionCopy(){
		WorldBuilderRegionCopyClientBridge.Result result=regionCopyBridge.poll();if(result==null)return;
		if(!result.accepted){inspectionStatus="Region "+(result.operation!=null&&result.operation.startsWith("cut")?"Cut":"Copy")+" refused ["+result.errorCode+"]: "+result.message+" Next: "+result.nextStep;return;}
		saveRequested=false;unsavedChanges=false;
		if("copy".equals(result.operation)){rememberCapturedRegionSnapshot(result);inspectionStatus="Copied '"+result.name+"': "+result.tileCount+" tiles, "+result.placementCount+" placements, snapshot "+shortHash(result.snapshotId)+(result.crossingReportCount>0?"; "+result.crossingReportCount+" crossing footprint report(s).":".");return;}
		if("cut-preview".equals(result.operation)){rememberCapturedRegionSnapshot(result);regionCutSnapshotId=result.snapshotId;regionCutPlanHash=result.planHash;regionCutBlocked=result.blocked;inspectionStatus=result.blocked?"Cut snapshot was secured, but the exact plan is blocked. Reset or correct the selection; the world was unchanged.":"Cut snapshot secured: "+result.tileCount+" tiles and "+result.placementCount+" placements. Review the selection, then select Confirm Cut.";return;}
		if("cut-apply".equals(result.operation)){inspectionStatus="Region cut atomically. Activating the published region live...";clearRegionSelection();mc.sendCommandString("activateregioncut "+result.requestId);}
	}
	private void rememberCapturedRegionSnapshot(WorldBuilderRegionCopyClientBridge.Result result){
		lastRegionSnapshotId=result.snapshotId;lastRegionSnapshotName=result.name;regionClipboardSnapshotId=result.snapshotId;regionClipboardSnapshotName=result.name;lastRegionTileCount=result.tileCount;lastRegionPlacementCount=result.placementCount;lastRegionCrossingCount=result.crossingReportCount;
		WorldBuilderRegionPasteClientBridge.Snapshot snapshot=new WorldBuilderRegionPasteClientBridge.Snapshot(result.snapshotId,result.name,result.tileCount,result.placementCount,1);
		regionLibraryIndex=-1;for(int i=0;i<regionLibrary.size();i++)if(regionLibrary.get(i).id.equals(result.snapshotId)){regionLibrary.set(i,snapshot);regionLibraryIndex=i;break;}
		if(regionLibraryIndex<0){regionLibrary.add(snapshot);regionLibraryIndex=regionLibrary.size()-1;}
	}
	private boolean selectRegionLibrarySnapshot(String snapshotId){
		regionLibraryIndex=-1;if(snapshotId==null||snapshotId.isEmpty())return false;
		for(int i=0;i<regionLibrary.size();i++)if(regionLibrary.get(i).id.equals(snapshotId)){regionLibraryIndex=i;return true;}
		return false;
	}
	private void selectRegionTool(RegionTool selected){
		if(regionCopyBridge.isPending()||regionPasteBridge.isPending()||isRegionSharingPending()){inspectionStatus="Wait for the active region operation before changing Copy/Cut/Paste tools.";return;}
		regionTool=selected;coordinateFocus=0;regionPasteOverwritePrompted=false;regionPasteOverwriteArmed=false;
		if(selected==RegionTool.PASTE){clearRegionSelection();regionLibraryPreferredSnapshotId=regionClipboardSnapshotId;if(selectRegionLibrarySnapshot(regionClipboardSnapshotId)){regionLibraryPreferredSnapshotId="";clearPastePreview();inspectionStatus="Clipboard ready: '"+selectedRegionSnapshot().name+"'. Click terrain to choose its Paste destination.";}else requestRegionLibrary();}
		else{clearPastePreview();clearRegionSelection();inspectionStatus=selected==RegionTool.CUT?"Cut selected: trace and Stop a boundary, then Cut to secure its snapshot and preview.":"Copy selected: click terrain to start an ordered boundary, Stop it, then Copy.";}
	}
	private void requestRegionLibrary(){
		if(regionPasteBridge.isPending()||isRegionSharingPending())return;
		try{regionPasteBridge.requestLibrary();mc.sendCommandString("pasteregion");inspectionStatus="Loading the verified project snapshot library...";}
		catch(Exception failure){inspectionStatus="Snapshot library could not open: "+failure.getMessage();}
	}
	private void requestRegionImport(){
		if(regionPasteBridge.isPending()||isRegionSharingPending())return;
		try{regionBundleDialog.openImport();inspectionStatus="Choose an existing portable .wbr file. The Builder remains live while the file chooser is open.";}
		catch(Exception failure){inspectionStatus="Region Import could not start: "+failure.getMessage();}
	}
	private void requestRegionExport(){
		if(regionPasteBridge.isPending()||isRegionSharingPending())return;if(regionClipboardSnapshotId.isEmpty()){inspectionStatus="Copy or import a region before exporting it.";mc.showWorldEditorStatus("There is nothing copied to clipboard");return;}
		try{regionBundleDialog.openExport(regionClipboardSnapshotId,regionClipboardSnapshotName);inspectionStatus="Choose a new .wbr destination. The Builder remains live while the file chooser is open.";}
		catch(Exception failure){inspectionStatus="Region Export could not start: "+failure.getMessage();}
	}
	private boolean isRegionSharingPending(){return regionBundleDialog.isPending()||regionBundleBridge.isPending();}
	private void pollRegionBundleDialog(){
		WorldBuilderRegionBundleFileDialog.Selection selection=regionBundleDialog.poll();if(selection==null)return;
		String label="import".equals(selection.operation)?"Import":"Export";
		if(!selection.error.isEmpty()){inspectionStatus="Region "+label+" file chooser failed: "+selection.error;return;}
		if(selection.cancelled){inspectionStatus="Region "+label+" cancelled; the library and world were unchanged.";return;}
		try{
			if("import".equals(selection.operation)){if(!Files.isRegularFile(selection.path,LinkOption.NOFOLLOW_LINKS)||Files.isSymbolicLink(selection.path)){inspectionStatus="Choose an existing regular .wbr file to import.";return;}regionBundleBridge.requestImport(selection.path);}
			else{if(Files.exists(selection.path,LinkOption.NOFOLLOW_LINKS)){inspectionStatus="That export file already exists. Choose a new .wbr filename; exports never overwrite.";return;}regionBundleBridge.requestExport(selection.snapshotId,selection.path);}
			mc.sendCommandString("shareregion");inspectionStatus="import".equals(selection.operation)?"Validating and importing the portable Region bundle...":"Exporting the selected snapshot as a portable .wbr file...";
		}catch(Exception failure){inspectionStatus="Region "+label+" could not start: "+failure.getMessage();}
	}
	private void cycleRegionSnapshot(int amount){
		if(regionPasteBridge.isPending()||isRegionSharingPending()||regionLibrary.isEmpty())return;
		regionLibraryIndex=Math.floorMod(regionLibraryIndex+amount,regionLibrary.size());clearPastePreview();
		inspectionStatus="Selected snapshot '"+selectedRegionSnapshot().name+"'. Click terrain to place its marker-1 anchor.";
	}
	private WorldBuilderRegionPasteClientBridge.Snapshot selectedRegionSnapshot(){return regionLibraryIndex>=0&&regionLibraryIndex<regionLibrary.size()?regionLibrary.get(regionLibraryIndex):null;}
	public void setRegionPasteDestination(int worldX,int worldY){
		if(!isRegionPasteSelectingDestination())return;WorldBuilderRegionPasteClientBridge.Snapshot snapshot=selectedRegionSnapshot();if(snapshot==null){inspectionStatus="There is nothing copied to clipboard";mc.showWorldEditorStatus(inspectionStatus);return;}
		regionPasteX=worldX;regionPasteY=worldY;regionPasteLevel=mc.getEditorPlayerWorldLevel();clearPastePreview();
		try{regionPasteBridge.requestPreview(snapshot.id,regionPasteLevel,worldX,worldY);mc.sendCommandString("pasteregion");inspectionStatus="Saving pending edits and calculating the exact Paste preview...";}
		catch(Exception failure){inspectionStatus="Region Paste preview could not start: "+failure.getMessage();}
	}
	private void requestRegionPasteApply(){
		if(regionPasteBridge.isPending()||isRegionSharingPending())return;if(regionPastePlanHash.isEmpty()){inspectionStatus="Choose a destination and wait for its exact Paste preview first.";return;}if(regionPasteBlocked){inspectionStatus="This Paste plan is blocked; choose another destination or compatible snapshot.";return;}
		if(regionPasteOverwrite&&!regionPasteOverwritePrompted){regionPasteOverwritePrompted=true;inspectionStatus="This destination is occupied. Select Overwrite? to continue.";return;}
		if(regionPasteOverwrite&&!regionPasteOverwriteArmed){regionPasteOverwriteArmed=true;inspectionStatus="Overwrite will replace the highlighted content. Select Confirm to apply this exact plan.";return;}
		WorldBuilderRegionPasteClientBridge.Snapshot snapshot=selectedRegionSnapshot();if(snapshot==null)return;
		try{regionPasteBridge.requestApply(snapshot.id,regionPasteLevel,regionPasteX,regionPasteY,regionPastePlanHash,regionPasteOverwrite);mc.sendCommandString("pasteregion");inspectionStatus="Applying the exact atomic Paste plan...";}
		catch(Exception failure){inspectionStatus="Region Paste could not start: "+failure.getMessage();}
	}
	private void requestRegionPasteUndo(){
		if(regionPasteBridge.isPending()||isRegionSharingPending())return;
		try{regionPasteBridge.requestUndo();mc.sendCommandString("pasteregion");inspectionStatus="Checking whether the exact last Paste can be undone safely...";}
		catch(Exception failure){inspectionStatus="Region Paste Undo could not start: "+failure.getMessage();}
	}
	private void pollRegionPaste(){
		WorldBuilderRegionPasteClientBridge.Result result=regionPasteBridge.poll();if(result==null)return;
		if(!result.accepted){regionPasteOverwriteArmed=false;inspectionStatus="Region Paste refused ["+result.errorCode+"]: "+result.message+" Next: "+result.nextStep;return;}
		if("library".equals(result.operation)){
			String selected=regionLibraryPreferredSnapshotId.isEmpty()?regionClipboardSnapshotId:regionLibraryPreferredSnapshotId;
			regionLibrary.clear();regionLibrary.addAll(result.snapshots);regionLibraryIndex=-1;
			selectRegionLibrarySnapshot(selected);
			if(regionLibraryIndex<0)selectRegionLibrarySnapshot(result.activeSnapshotId);
			if(regionLibraryIndex<0&&selected.isEmpty()&&regionLibrary.size()==1)regionLibraryIndex=0;
			if(regionLibraryIndex>=0){regionClipboardSnapshotId=regionLibrary.get(regionLibraryIndex).id;regionClipboardSnapshotName=regionLibrary.get(regionLibraryIndex).name;}
			clearPastePreview();
			inspectionStatus=regionLibraryRefreshStatus.isEmpty()?(regionLibraryIndex<0?(regionLibrary.isEmpty()?"There is nothing copied to clipboard. Use Copy or Import first.":"The snapshot library has multiple entries but no active clipboard selection. Copy or import the region you want to Paste."):"Clipboard ready: '"+selectedRegionSnapshot().name+"'. Click terrain to choose its Paste destination."):regionLibraryRefreshStatus;
			regionLibraryRefreshStatus="";regionLibraryPreferredSnapshotId="";return;
		}
		if("preview".equals(result.operation)){regionPastePlanHash=result.planHash;regionPasteBlocked=result.blocked;regionPasteOverwrite=result.overwrite;regionPasteOverwriteArmed=false;try{regionPastePreviewTiles=WorldEditorRegionSelection.ownedTiles(result.markers,65536);}catch(Exception invalid){regionPastePreviewTiles=new int[0][2];regionPasteBlocked=true;}List<int[]> collisions=new ArrayList<int[]>();for(int[] collision:result.collisions)if(collision[0]==mc.getEditorPlayerWorldLevel())collisions.add(new int[]{collision[1],collision[2]});regionPasteCollisionTiles=collisions.toArray(new int[collisions.size()][2]);inspectionStatus=result.blocked?"Paste preview is blocked with "+result.collisions.length+" collision/compatibility issue(s).":result.overwrite?"Paste preview ready: "+result.tileCount+" tiles and "+result.placementCount+" placements; overwrite confirmation is required.":"Paste preview ready: "+result.tileCount+" tiles and "+result.placementCount+" placements. Review the ghost, then Apply Paste.";return;}
		if("apply".equals(result.operation)||"undo".equals(result.operation)){saveRequested=false;unsavedChanges=false;inspectionStatus="undo".equals(result.operation)?"Last Paste restored atomically. Activating the restored region live...":"Region pasted atomically. Activating the published region live...";mc.sendCommandString("activateregionpaste "+result.requestId);}
	}
	private void pollRegionBundle(){
		WorldBuilderRegionBundleClientBridge.Result result=regionBundleBridge.poll();if(result==null)return;
		if(!result.accepted){inspectionStatus="Region "+("import".equals(result.operation)?"Import":"Export")+" refused ["+result.errorCode+"]: "+result.message+" Next: "+result.nextStep;return;}
		if("import".equals(result.operation)){regionClipboardSnapshotId=result.snapshotId;regionClipboardSnapshotName="Imported region";regionLibraryPreferredSnapshotId=result.snapshotId;regionLibraryRefreshStatus=result.compatible?"Imported and selected shared snapshot "+shortHash(result.snapshotId)+". Click terrain to preview its Paste destination.":"Imported snapshot "+shortHash(result.snapshotId)+", but "+result.issueCount+" compatibility issue(s) must be resolved before Paste.";requestRegionLibrary();}
		else inspectionStatus="Exported the selected snapshot to "+result.outputPath+". Share that .wbr file with another creator.";
	}
	private void clearPastePreview(){regionPastePreviewTiles=new int[0][2];regionPasteCollisionTiles=new int[0][2];regionPastePlanHash="";regionPasteBlocked=false;regionPasteOverwrite=false;regionPasteOverwritePrompted=false;regionPasteOverwriteArmed=false;}
	private void clearRegionCutPlan(){regionCutSnapshotId="";regionCutPlanHash="";regionCutBlocked=false;}
	private void resetRegionPaste(){regionTool=RegionTool.COPY;regionLibrary.clear();regionLibraryIndex=-1;regionPasteX=regionPasteY=-1;regionPasteLevel=0;regionClipboardSnapshotId=regionClipboardSnapshotName="";regionLibraryRefreshStatus="";regionLibraryPreferredSnapshotId="";clearPastePreview();}
	public int[][] regionMarkerTiles(){int[][] result=new int[regionMarkers.size()][2];for(int index=0;index<regionMarkers.size();index++){result[index][0]=regionMarkers.get(index)[0];result[index][1]=regionMarkers.get(index)[1];}return result;}
	public int[][] regionSelectionPreviewTiles(){return regionClosed?regionPreviewTiles:new int[0][2];}
	public int[] regionSelectionHoverTile(){return isRegionSelecting()&&!regionClosed&&regionHoverX>=0?new int[]{regionHoverX,regionHoverY}:null;}
	public int[][] regionPastePreviewTiles(){return regionTool==RegionTool.PASTE?regionPastePreviewTiles:new int[0][2];}
	public int[][] regionPasteCollisionTiles(){return regionTool==RegionTool.PASTE?regionPasteCollisionTiles:new int[0][2];}
	public int[] regionPasteAnchorTile(){return regionTool==RegionTool.PASTE&&regionPasteX>=0?new int[]{regionPasteX,regionPasteY}:null;}
	private static String shortHash(String value){return value==null?"":value.substring(0,Math.min(12,value.length()));}
	public void selectNpc(int id,int radius){setNpcId(id);setNpcRadius(radius);}
	public void selectNpc(int id,int radius,int respawnSeconds){selectNpc(id,radius);setNpcRespawnSeconds(respawnSeconds);}
	public void setSequence(int sequence){nextSequence=sequence;}
	public void setTerrainHistoryAvailability(boolean canUndo,boolean canRedo){terrainHistoryCanUndo=canUndo;terrainHistoryCanRedo=canRedo;}
	public void recordWorldClick(int x,int y){
		int level=mc.getEditorPlayerWorldLevel();lastClickedX=x;lastClickedY=y;lastClickedLevel=level;
		if(mode!=Mode.NAVIGATE){brushX=x;brushY=y;brushLevel=level;}
		coordinateFocus=0;toolbar.closeUnpinnedAfterWorldAction();updatePresentationBounds();
	}
	public void requestPlaceScenery(int x,int y){requestEntityEdit(1,sceneryId,x,y,0,0,0,0);}
	public void requestRemoveScenery(int x,int y){requestEntityEdit(2,0,x,y,0,0,0,0);}
	public void requestRotateScenery(int x,int y){requestEntityEdit(3,0,x,y,0,0,-1,0);}
	public void requestPlaceNpc(int x,int y){requestEntityEdit(5,npcId,x,y,0,0,npcRadius,npcRespawnSeconds);}
	public void requestRemoveNpc(int instanceId){requestEntityEdit(6,instanceId,0,0,0,0,0,0);}
	public void requestPlaceGroundItem(int x,int y){requestEntityEdit(7,groundItemId,x,y,0,0,groundItemAmount,groundItemRespawnSeconds);}
	public void requestRemoveGroundItem(int id,int x,int y){requestEntityEdit(8,id,x,y,0,0,0,0);}
	private void requestEntityEdit(int operation,int id,int x,int y,int endX,int endY,int argument0,int argument1){
		if(!isEditorOpen())return;if(!entityEditTracker.begin(nextSequence,operation)){inspectionStatus="Wait for the authoritative entity response before editing another placement.";return;}
		saveRequested=false;closeArmed=false;inspectionStatus="Awaiting authoritative World Builder response.";
		mc.packetHandler.getClientStream().newPacket(152);mc.packetHandler.getClientStream().bufferBits.putByte(12);
		mc.packetHandler.getClientStream().bufferBits.putLong(sessionId);mc.packetHandler.getClientStream().bufferBits.putInt(nextSequence);
		mc.packetHandler.getClientStream().bufferBits.putByte(operation);mc.packetHandler.getClientStream().bufferBits.putShort(id);
		mc.packetHandler.getClientStream().bufferBits.putShort(x);mc.packetHandler.getClientStream().bufferBits.putShort(y);
		mc.packetHandler.getClientStream().bufferBits.putShort(endX);mc.packetHandler.getClientStream().bufferBits.putShort(endY);
		mc.packetHandler.getClientStream().bufferBits.putInt(argument0);mc.packetHandler.getClientStream().bufferBits.putInt(argument1);
		mc.packetHandler.getClientStream().finishPacket();
	}
	public void acceptEntityEdit(int sequence,int operation,boolean accepted,boolean canUndo,boolean canRedo,String message){
		if(!entityEditTracker.complete(sequence,operation)){showError("Server returned an uncorrelated entity-edit response.");return;}
		nextSequence=sequence;noteDeferredSaveProgress(System.nanoTime());terrainHistoryCanUndo=canUndo;terrainHistoryCanRedo=canRedo;
		if(accepted){unsavedChanges=true;closeArmed=false;if(operation==4)clearSceneryMove();}
		inspectionStatus=message==null?"Entity edit completed.":message;mc.showWorldEditorStatus(inspectionStatus);maybeSubmitDeferredSave();
	}
	public void observeGameMessage(String message){
		if(!isEditorOpen()||message==null)return;
		mc.observeAutomatedBuilderPlacementMessage(message);
		if((message.contains("Saved ")&&message.contains(" world edits."))
				||message.contains("Saved the complete isolated working package:")
				||message.contains("Saved pending edits to the isolated working package:")
				||message.contains("No pending world edits to save.")){
			unsavedChanges=false;saveRequested=false;saveAfterPendingEdits=false;deferredSaveProgressNanos=0L;entityEditTracker.reset();closeArmed=false;inspectionStatus="World edits saved; no pending changes.";
			mc.showWorldEditorStatus("World edits saved successfully; no pending changes.");
		}else if(message.contains("Failed to save world edits:")){saveRequested=false;saveAfterPendingEdits=false;deferredSaveProgressNanos=0L;inspectionStatus=message;mc.showWorldEditorStatus(message);}
		if(message.contains("Region Paste activated live")||message.contains("Region Paste Undo activated live")){
			clearPastePreview();inspectionStatus=message.contains("Paste Undo")?"Last Paste was undone and activated live; the Builder stayed open.":"Region pasted and activated live; the Builder stayed open.";
		}else if(message.contains("Region Cut activated live")){
			clearRegionCutPlan();inspectionStatus="Region cut and activated live; its reusable snapshot remains on the clipboard.";
		}else if(message.contains("Live Region Paste activation failed:")||message.contains("Live Region Cut activation failed:"))inspectionStatus=message;
	}
	public void showInfo(int responseType,String text){
		inspectionKind=responseType==5?"NPC":(text!=null&&text.contains("type=boundary")?"Boundary":"Scenery");
		inspectionStatus="Authoritative "+inspectionKind.toLowerCase()+" inspection";inspectionDetails=wrap(text,58);
		if(responseType==4){int id=valueAfter(text,"id=");if(id>=0&&copyNextInspection)setSceneryId(id);}
		if(responseType==5){int id=valueAfter(text,"id="),radius=valueAfter(text,"radius="),respawn=valueAfter(text,"respawn=");if(copyNextInspection){if(id>=0)setNpcId(id);if(radius>=0)setNpcRadius(radius);if(respawn>=-1)setNpcRespawnSeconds(respawn);}}
		if(copyNextInspection)copyInspected();copyNextInspection=false;
	}
	public void showError(String text){
		boolean saveAcceptedDraft=saveAfterPendingEdits&&!saveRequested;
		int unacknowledged=saveAcceptedDraft?pendingAuthoritativeEditCount():0;
		if(entityEditTracker.isPending()){entityEditTracker.reset();noteDeferredSaveProgress(System.nanoTime());}
		copyNextInspection=false;saveAfterPendingEdits=false;deferredSaveProgressNanos=0L;terrainStrokeTiles=null;terrainStrokeStartedNanos=0L;clearTerrainLine();clearTerrainDrag();
		if(terrainHistoryPending){terrainHistoryPending=false;terrainHistoryTotal=terrainHistoryReceived=0;if(text!=null&&text.contains("nothing to undo"))terrainHistoryCanUndo=false;if(text!=null&&text.contains("nothing to redo"))terrainHistoryCanRedo=false;}
		inspectionStatus="Server rejected request";inspectionDetails=wrap(text,58);
		mc.observeAutomatedBuilderEditorError(text);
		if(saveAcceptedDraft){boolean timeout=text!=null&&text.contains("response timed out");submitWorldEditSave(timeout
			?"Timed out waiting for "+unacknowledged+" edit response"+(unacknowledged==1?"":"s")+"; saving every change accepted by the server. Reopen after completion to reconcile unacknowledged edits."
			:"The final edit was rejected; saving all earlier changes accepted by the server. Wait for the completion message before closing.");}
	}
	public void showTerrain(int sequence,int x,int y,int plane,int sx,int sy,int lx,int ly,int elev,int texture,int overlay,int roof,int hwall,int vwall,int diag,int collision,boolean projectile,boolean copied,String definitions){
		nextSequence=sequence;inspectionKind="Terrain";inspectionStatus="Authoritative terrain inspection";
		inspectedTerrainFields=new int[]{elev,texture,overlay,roof,hwall,vwall,diag};
		String[] names=definitions==null?new String[0]:definitions.split("\\t",-1);
		String northName=names.length>0?names[0]:"unknown",eastName=names.length>1?names[1]:"unknown",diagonalName=names.length>2?names[2]:"unknown";
		int northId=vwall>0?vwall-1:-1,eastId=hwall>0?hwall-1:-1,diagonalId=diagonalDefinitionId(diag);
		int displayY=isLayeredReview()?y:Math.floorMod(y,944);
		int displayLevel=isLayeredReview()?plane:logicalLevelForLegacyPlane(plane);
		java.util.List<String> lines=new java.util.ArrayList<String>();java.util.Collections.addAll(lines,
			"Coordinates: "+x+", "+displayY+", L"+displayLevel,"Level: "+displayLevel+" ("+planeName(displayLevel)+")","Elevation: "+elev,
			"Floor Color: "+texture,"Floor Texture: "+overlay,
			"Walls: North "+wall(northId,northName)+" | East "+wall(eastId,eastName),
			"Diagonal "+wall(diagonalId,diagonalName)+" ("+diagonalRotation(diag)+")",
			"Collision: 0x"+Integer.toHexString(collision)+" | Projectiles: "+(projectile?"allowed":"blocked"),
			"Archive: sector "+sx+","+sy+" | local "+lx+","+ly);
		inspectionDetails=lines.toArray(new String[lines.size()]);
		if(copied||copyNextInspection)copyInspected();copyNextInspection=false;
	}
	public void acceptTerrainPaint(int sequence,int x,int y,int plane,int sx,int sy,int lx,int ly,int elev,int texture,int overlay,int roof,int hwall,int vwall,int diag,int collision,boolean projectile,int fieldMask,String definitions){
		noteDeferredSaveProgress(System.nanoTime());
		showTerrain(sequence,x,y,plane,sx,sy,lx,ly,elev,texture,overlay,roof,hwall,vwall,diag,collision,projectile,false,definitions);
		mc.applyWorldEditorTerrainPatch(x,y,plane,elev,texture,overlay,roof,hwall,vwall,diag,(fieldMask&4)!=0,true);
		terrainStrokeTiles=null;unsavedChanges=true;closeArmed=false;inspectionStatus="Paint accepted: 1 tile (unsaved draft)";
	}
	public void acceptTerrainStroke(int sequence,int fieldMask,int[][] tiles,boolean[] projectiles,String definitions){
		if(tiles==null||tiles.length<1||tiles.length>64||projectiles==null||projectiles.length!=tiles.length){showError("Server returned an invalid terrain stroke.");return;}
		long responseNanos=System.nanoTime();noteDeferredSaveProgress(responseNanos);int[] center=tiles[0];
		showTerrain(sequence,center[0],center[1],center[2],center[3],center[4],center[5],center[6],center[7],center[8],center[9],center[10],center[11],center[12],center[13],center[14],projectiles[0],false,definitions);
		for(int i=0;i<tiles.length;i++){int[] tile=tiles[i];
			mc.applyWorldEditorTerrainPatch(tile[0],tile[1],tile[2],tile[7],tile[8],tile[9],tile[10],tile[11],tile[12],tile[13],(fieldMask&4)!=0,i==tiles.length-1);
		}
		mc.observeAutomatedBuilderTerrainStroke(fieldMask,tiles);
		long completedNanos=System.nanoTime();long ackMs=terrainStrokeStartedNanos==0L?0L:(responseNanos-terrainStrokeStartedNanos)/1000000L;
		long rebuildMs=(completedNanos-responseNanos)/1000000L;terrainStrokeTiles=null;terrainStrokeStartedNanos=0L;
		lastAckMillis=ackMs;lastRebuildMillis=rebuildMs;
		unsavedChanges=true;closeArmed=false;
		boolean dragStroke=terrainDragActive||terrainDragReleasePending||!terrainDragSeen.isEmpty();
		if(!dragStroke){inspectionStatus="Paint accepted: "+tiles.length+" tile"+(tiles.length==1?"":"s")+" | ack "+ackMs+"ms, rebuild "+rebuildMs+"ms";maybeSubmitDeferredSave();return;}
		terrainDragAccepted+=tiles.length;terrainDragAckMillis+=ackMs;terrainDragRebuildMillis+=rebuildMs;
		if(!terrainDragPending.isEmpty())sendNextTerrainDragBatch();
		if(terrainDragReleasePending&&terrainStrokeTiles==null&&terrainDragPending.isEmpty())completeTerrainDrag();
		else inspectionStatus=terrainDragStatus();
	}
	public void acceptTerrainLineChunk(int sequence,int fieldMask,int total,int offset,int[][] tiles,boolean[] projectiles,String definitions){
		if(terrainLineCommitTiles==null||terrainLineCommitMasks==null||terrainLineCommitMasks.length!=terrainLineCommitTiles.length||total<1||total>TERRAIN_DRAG_LIMIT||total!=terrainLineCommitTiles.length
			||offset!=terrainLineReceived||tiles==null||tiles.length<1||tiles.length>TERRAIN_BATCH_LIMIT
			||offset+tiles.length>total||projectiles==null||projectiles.length!=tiles.length){showError("Server returned an invalid terrain line result.");return;}
		for(int i=0;i<tiles.length;i++){int[] expected=terrainLineCommitTiles[offset+i],tile=tiles[i];
			if(tile==null||tile.length<15||tile[0]!=expected[0]||tile[1]!=expected[1]){showError("Server terrain line geometry did not match the preview.");return;}}
		long responseNanos=System.nanoTime();noteDeferredSaveProgress(responseNanos);terrainLineLastResponseNanos=responseNanos;if(offset==0){int[] center=tiles[0];
			showTerrain(sequence,center[0],center[1],center[2],center[3],center[4],center[5],center[6],center[7],center[8],center[9],center[10],center[11],center[12],center[13],center[14],projectiles[0],false,definitions);}
		boolean complete=offset+tiles.length==total;for(int i=0;i<tiles.length;i++){int[] tile=tiles[i];int tileMask=terrainLineCommitMasks[offset+i];
			mc.applyWorldEditorTerrainPatch(tile[0],tile[1],tile[2],tile[7],tile[8],tile[9],tile[10],tile[11],tile[12],tile[13],(tileMask&4)!=0,complete&&i==tiles.length-1);}
		mc.observeAutomatedBuilderTerrainStroke(fieldMask,tiles);terrainLineReceived+=tiles.length;
		if(!complete){inspectionStatus=terrainGestureLabel+" committed authoritatively; receiving "+terrainLineReceived+" of "+total+" tiles.";return;}
		long completedNanos=System.nanoTime(),ackMs=terrainStrokeStartedNanos==0L?0L:(responseNanos-terrainStrokeStartedNanos)/1000000L;
		long rebuildMs=(completedNanos-responseNanos)/1000000L;lastAckMillis=ackMs;lastRebuildMillis=rebuildMs;
		String completedLabel=terrainGestureLabel;unsavedChanges=true;closeArmed=false;clearTerrainLine();terrainStrokeStartedNanos=0L;
		inspectionStatus=completedLabel+" accepted: "+total+" unique tiles | ack "+ackMs+"ms, rebuild "+rebuildMs+"ms";
		maybeSubmitDeferredSave();
	}
	public void acceptTerrainHistoryChunk(int sequence,int total,int offset,int[][] tiles,boolean[] projectiles,boolean canUndo,boolean canRedo,String message){
		if(!terrainHistoryPending||total<1||total>TERRAIN_DRAG_LIMIT||offset!=terrainHistoryReceived
			||tiles==null||tiles.length<1||tiles.length>TERRAIN_BATCH_LIMIT||offset+tiles.length>total
			||projectiles==null||projectiles.length!=tiles.length){showError("Server returned an invalid terrain history result.");return;}
		if(terrainHistoryTotal==0)terrainHistoryTotal=total;else if(terrainHistoryTotal!=total){showError("Server changed the terrain history result size.");return;}
		boolean complete=offset+tiles.length==total;
		for(int i=0;i<tiles.length;i++){int[] tile=tiles[i];if(tile==null||tile.length<15){showError("Server returned an invalid terrain history tile.");return;}
			mc.applyWorldEditorTerrainPatch(tile[0],tile[1],tile[2],tile[7],tile[8],tile[9],tile[10],tile[11],tile[12],tile[13],true,complete&&i==tiles.length-1);}
		terrainHistoryReceived+=tiles.length;
		if(!complete){inspectionStatus="Applying terrain history: "+terrainHistoryReceived+" of "+total+" tiles.";return;}
		setSequence(sequence);terrainHistoryCanUndo=canUndo;terrainHistoryCanRedo=canRedo;
		terrainHistoryPending=false;terrainHistoryTotal=terrainHistoryReceived=0;
		unsavedChanges=true;closeArmed=false;inspectionStatus=message;
	}
	public void acceptPlacementHistory(int sequence,boolean canUndo,boolean canRedo,String message){
		if(!terrainHistoryPending){showError("Server returned an unexpected placement history result.");return;}
		setSequence(sequence);terrainHistoryCanUndo=canUndo;terrainHistoryCanRedo=canRedo;
		terrainHistoryPending=false;terrainHistoryTotal=terrainHistoryReceived=0;
		unsavedChanges=true;closeArmed=false;inspectionStatus=message;
	}
	public int[] getCopiedTerrainFields(){return copiedTerrainFields==null?null:copiedTerrainFields.clone();}
	public void inspectTerrain(int worldX,int worldY,boolean copy){recordWorldClick(worldX,worldY);send(2,worldX,worldY,editorLevel(worldY),0,0,copy?1:0);}
	public void paintTerrain(int worldX,int worldY){
		recordWorldClick(worldX,worldY);int mask=terrainPaintMask();
		boolean smartWallSelected=terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.hasSmartWallSelection();
		if(mask==0&&!smartWallSelected){showError("Select at least one terrain field to paint.");return;}if(!isTerrainPainting()||terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragActive||terrainDragReleasePending)return;
		if(terrainTool==TerrainTool.LINE){
			if(terrainLineAnchorX<0){terrainLineAnchorX=worldX;terrainLineAnchorY=worldY;terrainDragHoverX=worldX;terrainDragHoverY=worldY;inspectionStatus="Line anchor set at "+worldX+","+worldY+"; move the pointer and click the destination.";return;}
			commitTerrainLine(worldX,worldY,mask);return;
		}
		if(terrainTool==TerrainTool.RECTANGLE){
			if(terrainLineAnchorX<0){terrainLineAnchorX=worldX;terrainLineAnchorY=worldY;terrainDragHoverX=worldX;terrainDragHoverY=worldY;inspectionStatus="Rectangle corner set at "+worldX+","+worldY+"; move the pointer and click the opposite corner.";return;}
			commitTerrainRectangle(worldX,worldY,mask);return;
		}
		int strokeSize=terrainBrushSize;terrainStrokeTiles=WorldEditorTerrainBrush.centeredFootprint(worldX,worldY,strokeSize);
		snapshotTerrainPaint(mask);terrainStrokeHistoryToken=nextTerrainHistoryToken();
		terrainStrokeStartedNanos=System.nanoTime();sendTerrainStroke();
	}
	private void commitTerrainLine(int worldX,int worldY,int mask){
		int[][] tiles;try{tiles=WorldEditorTerrainBrush.lineFootprint(terrainLineAnchorX,terrainLineAnchorY,worldX,worldY,terrainBrushSize,TERRAIN_DRAG_LIMIT);}
		catch(IllegalArgumentException exception){inspectionStatus="Line exceeds the 4096-tile operation limit; choose a closer destination.";inspectionDetails=new String[]{"The entire line is validated and committed atomically; no terrain was changed."};return;}
		int plane=editorLevel(terrainLineAnchorY);for(int[] tile:tiles){
			if(tile[0]<0||tile[0]>32767||tile[1]<0||tile[1]>32767){inspectionStatus="Line crosses unsupported terrain coordinates; choose another destination.";return;}
			if(!isLayeredReview()&&Math.floorDiv(tile[1],944)!=plane){inspectionStatus="Line cannot cross a legacy wilderness-level boundary.";return;}
		}
		int startX=terrainLineAnchorX,startY=terrainLineAnchorY;clearTerrainDrag();terrainGestureLabel="Line";snapshotTerrainPaint(mask);terrainStrokeHistoryToken=nextTerrainHistoryToken();
		terrainLineCommitTiles=tiles;terrainLineCommitMasks=new int[tiles.length];java.util.Arrays.fill(terrainLineCommitMasks,mask);terrainLineReceived=0;terrainDragHoverX=worldX;terrainDragHoverY=worldY;terrainStrokeStartedNanos=System.nanoTime();terrainLineLastResponseNanos=terrainStrokeStartedNanos;
		sendTerrainLine(startX,startY,worldX,worldY);inspectionStatus="Committing line atomically: "+tiles.length+" unique tiles.";
	}
	private void commitTerrainRectangle(int worldX,int worldY,int mask){
		WorldEditorTerrainBrush.RectanglePlan plan;try{plan=WorldEditorTerrainBrush.rectanglePlan(terrainLineAnchorX,terrainLineAnchorY,worldX,worldY,
			rectangleOptions.isFill(),mask,rectangleOptions.isSmartWalls(),rectangleOptions.isNorthWall(),rectangleOptions.isEastWall(),TERRAIN_DRAG_LIMIT);}
		catch(IllegalArgumentException exception){inspectionStatus="Rectangle exceeds the 4096-tile operation limit or has no applicable fields.";inspectionDetails=new String[]{"The entire rectangle is validated and committed atomically; no terrain was changed."};return;}
		int[][] tiles=plan.tiles();int plane=editorLevel(terrainLineAnchorY);for(int[] tile:tiles){
			if(tile[0]<0||tile[0]>32767||tile[1]<0||tile[1]>32767){inspectionStatus="Rectangle crosses unsupported terrain coordinates; choose another corner.";return;}
			if(!isLayeredReview()&&Math.floorDiv(tile[1],944)!=plane){inspectionStatus="Rectangle cannot cross a legacy wilderness-level boundary.";return;}
		}
		int startX=terrainLineAnchorX,startY=terrainLineAnchorY;clearTerrainDrag();terrainGestureLabel="Rectangle";snapshotTerrainPaint(mask);terrainStrokeHistoryToken=nextTerrainHistoryToken();
		terrainLineCommitTiles=tiles;terrainLineCommitMasks=plan.fieldMasks();terrainLineReceived=0;terrainDragHoverX=worldX;terrainDragHoverY=worldY;terrainStrokeStartedNanos=System.nanoTime();terrainLineLastResponseNanos=terrainStrokeStartedNanos;
		sendTerrainRectangle(startX,startY,worldX,worldY);inspectionStatus="Committing rectangle atomically: "+tiles.length+" unique tiles.";
	}
	public boolean sendAutomatedBoundaryPlacementProbe(int worldX,int worldY,int raw){
		if(!Boolean.getBoolean("openrsc.worldBuilderAutomatedDefinitionProbe")
			||!isEditorOpen()||terrainStrokeTiles!=null||terrainLineCommitTiles!=null)return false;
		terrainStrokeTiles=new int[][]{{worldX,worldY}};terrainStrokeMask=16;
		terrainStrokeElevation=terrainStrokeColor=terrainStrokeTexture=terrainStrokeRoof=0;
		terrainStrokeEastWall=raw;terrainStrokeNorthWall=terrainStrokeDiagonal=0;
		terrainStrokeHistoryToken=nextTerrainHistoryToken();terrainStrokeStartedNanos=System.nanoTime();sendTerrainStroke();return true;
	}
	public boolean sendAutomatedFloorPlacementProbe(int worldX,int worldY,int raw){
		if(!Boolean.getBoolean("openrsc.worldBuilderAutomatedDefinitionProbe")
			||!isEditorOpen()||terrainStrokeTiles!=null||terrainLineCommitTiles!=null)return false;
		terrainStrokeTiles=new int[][]{{worldX,worldY}};terrainStrokeMask=4;
		terrainStrokeElevation=terrainStrokeColor=terrainStrokeRoof=0;
		terrainStrokeTexture=raw;terrainStrokeEastWall=terrainStrokeNorthWall=terrainStrokeDiagonal=0;
		terrainStrokeHistoryToken=nextTerrainHistoryToken();terrainStrokeStartedNanos=System.nanoTime();sendTerrainStroke();return true;
	}
	public boolean sendAutomatedWideElevationProbe(int operation,int elevation,int step,int[][] tiles){
		if(!"author".equals(System.getProperty("openrsc.worldBuilderAutomatedWideElevationProbe",""))
			||!isEditorOpen()||terrainStrokeTiles!=null||terrainLineCommitTiles!=null||tiles==null||tiles.length<1||tiles.length>TERRAIN_BATCH_LIMIT)return false;
		terrainStrokeTiles=new int[tiles.length][2];for(int i=0;i<tiles.length;i++){if(tiles[i]==null||tiles[i].length!=2){terrainStrokeTiles=null;return false;}terrainStrokeTiles[i]=tiles[i].clone();}
		terrainStrokeMask=1;terrainStrokeElevationOperation=operation;terrainStrokeElevation=elevation;terrainStrokeElevationStep=step;
		terrainStrokeColor=terrainStrokeTexture=terrainStrokeRoof=terrainStrokeEastWall=terrainStrokeNorthWall=terrainStrokeDiagonal=0;
		terrainStrokeHistoryToken=nextTerrainHistoryToken();terrainStrokeStartedNanos=System.nanoTime();sendTerrainStroke();return true;
	}
	public boolean updateTerrainDrag(boolean controlDown,boolean primaryDown,int worldX,int worldY){
		long now=System.nanoTime();if(recoverTerrainStrokeTimeout(now))return true;
		if(isTerrainPainting()){if(worldX>=0&&worldY>=0){terrainDragHoverX=worldX;terrainDragHoverY=worldY;}else if(!terrainDragActive){terrainDragHoverX=terrainDragHoverY=-1;}}
		if(terrainTool!=TerrainTool.FREEHAND){
			if(terrainLineAnchorX>=0&&terrainDragHoverX>=0){try{if(terrainTool==TerrainTool.LINE)WorldEditorTerrainBrush.lineFootprint(terrainLineAnchorX,terrainLineAnchorY,terrainDragHoverX,terrainDragHoverY,terrainBrushSize,TERRAIN_DRAG_LIMIT);
				else WorldEditorTerrainBrush.rectanglePlan(terrainLineAnchorX,terrainLineAnchorY,terrainDragHoverX,terrainDragHoverY,rectangleOptions.isFill(),terrainPaintMask(),rectangleOptions.isSmartWalls(),rectangleOptions.isNorthWall(),rectangleOptions.isEastWall(),TERRAIN_DRAG_LIMIT);}
				catch(IllegalArgumentException ignored){inspectionStatus=(terrainTool==TerrainTool.LINE?"Line":"Rectangle")+" preview exceeds the 4096-tile atomic operation limit or has no applicable fields.";}}
			return false;
		}
		boolean gesture=controlDown&&primaryDown&&isTerrainPainting();
		if(!terrainDragActive){
			if(!gesture||worldX<0||worldY<0||terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragReleasePending)return false;
			int mask=terrainPaintMask();if(mask==0){showError("Select at least one terrain field to paint.");return true;}
			clearTerrainDrag();terrainGestureLabel="Brush";terrainDragActive=true;snapshotTerrainPaint(mask);terrainStrokeHistoryToken=nextTerrainHistoryToken();addTerrainDragCenter(worldX,worldY,now);inspectionStatus=terrainDragStatus();return true;
		}
		if(!gesture){releaseTerrainDrag();return true;}
		if(worldX>=0&&worldY>=0)addTerrainDragCenter(worldX,worldY,now);maybeFlushTerrainDrag(now,false);inspectionStatus=terrainDragStatus();return true;
	}
	private int terrainPaintMask(){int nonWalls=(paintElevation?1:0)|(paintFloorColor?2:0)|(paintFloorTexture?4:0)|(paintRoof?8:0);
		return nonWalls+(terrainTool==TerrainTool.RECTANGLE?rectangleOptions.rawWallMask()
			:(rectangleOptions.isEastWall()?16:0)|(rectangleOptions.isNorthWall()?32:0)|(rectangleOptions.isDiagonalWall()?64:0));}
	private void snapshotTerrainPaint(int mask){terrainStrokeMask=mask;terrainStrokeElevation=terrainElevation;terrainStrokeElevationOperation=terrainElevationOperation;terrainStrokeElevationStep=terrainElevationStep;terrainStrokeColor=terrainFloorColor;terrainStrokeTexture=terrainFloorTexture;terrainStrokeRoof=terrainRoof;terrainStrokeEastWall=terrainEastWall;terrainStrokeNorthWall=terrainNorthWall;terrainStrokeDiagonal=encodedDiagonalWall();}
	private void addTerrainDragCenter(int worldX,int worldY,long now){
		terrainDragHoverX=worldX;terrainDragHoverY=worldY;
		if(worldX==terrainDragCenterX&&worldY==terrainDragCenterY)return;
		int[][] centers=terrainDragCenterX<0?new int[][]{{worldX,worldY}}
			:WorldEditorTerrainBrush.lineCenters(terrainDragCenterX,terrainDragCenterY,worldX,worldY);
		terrainDragCenterX=worldX;terrainDragCenterY=worldY;recordWorldClick(worldX,worldY);int strokeSize=terrainBrushSize;
		for(int[] center:centers){int[][] footprint=WorldEditorTerrainBrush.centeredFootprint(center[0],center[1],strokeSize);int plane=editorLevel(center[1]);
			for(int[] tile:footprint){if(!isLayeredReview()&&Math.floorDiv(tile[1],944)!=plane)continue;long key=terrainTileKey(tile[0],tile[1]);
				if(terrainDragSeen.size()>=TERRAIN_DRAG_LIMIT&&!terrainDragSeen.contains(key))continue;
				if(terrainDragSeen.add(key)){if(terrainDragPending.isEmpty())terrainDragPendingSinceNanos=now;terrainDragPending.put(key,new int[]{tile[0],tile[1]});}}
		}
		maybeFlushTerrainDrag(now,false);
	}
	private void releaseTerrainDrag(){terrainDragActive=false;terrainDragReleasePending=true;terrainDragHoverX=terrainDragHoverY=-1;if(terrainStrokeTiles==null)sendNextTerrainDragBatch();if(terrainStrokeTiles==null&&terrainDragPending.isEmpty())completeTerrainDrag();}
	private void maybeFlushTerrainDrag(long now,boolean force){
		if(terrainStrokeTiles!=null||terrainDragPending.isEmpty())return;
		if(force||terrainDragPending.size()>=TERRAIN_BATCH_LIMIT||now-terrainDragPendingSinceNanos>=TERRAIN_DRAG_FLUSH_NANOS)sendNextTerrainDragBatch();
	}
	private void sendNextTerrainDragBatch(){
		if(terrainStrokeTiles!=null||terrainDragPending.isEmpty())return;int count=Math.min(TERRAIN_BATCH_LIMIT,terrainDragPending.size());terrainStrokeTiles=new int[count][2];
		Iterator<Map.Entry<Long,int[]>> iterator=terrainDragPending.entrySet().iterator();for(int i=0;i<count;i++){terrainStrokeTiles[i]=iterator.next().getValue();iterator.remove();}
		if(terrainDragPending.isEmpty())terrainDragPendingSinceNanos=0L;else terrainDragPendingSinceNanos=System.nanoTime();
		terrainStrokeStartedNanos=System.nanoTime();inspectionStatus=terrainDragStatus();sendTerrainStroke();
	}
	private boolean recoverTerrainStrokeTimeout(long now){
		long activity=terrainLineCommitTiles==null?terrainStrokeStartedNanos:terrainLineLastResponseNanos;
		if((terrainStrokeTiles==null&&terrainLineCommitTiles==null)||activity==0L||now-activity<TERRAIN_STROKE_TIMEOUT_NANOS)return false;
		showError("Terrain operation response timed out. The tool was reset; reopen the project to reconcile authoritative state before retrying.");return true;
	}
	private void completeTerrainDrag(){int accepted=terrainDragAccepted;long ack=terrainDragAckMillis,rebuild=terrainDragRebuildMillis;String label=terrainGestureLabel;clearTerrainDrag();inspectionStatus=label+" accepted: "+accepted+" unique tile"+(accepted==1?"":"s")+" | ack "+ack+"ms, rebuild "+rebuild+"ms";maybeSubmitDeferredSave();}
	private void clearTerrainDrag(){terrainDragActive=false;terrainDragReleasePending=false;terrainDragHoverX=terrainDragHoverY=terrainDragCenterX=terrainDragCenterY=-1;terrainDragAccepted=0;terrainDragAckMillis=terrainDragRebuildMillis=terrainDragPendingSinceNanos=0L;terrainStrokeTiles=null;terrainStrokeStartedNanos=0L;terrainStrokeHistoryToken=0;terrainDragPending.clear();terrainDragSeen.clear();}
	private void clearTerrainLine(){terrainLineAnchorX=terrainLineAnchorY=-1;terrainLineCommitTiles=null;terrainLineCommitMasks=null;terrainLineReceived=0;terrainLineLastResponseNanos=0L;}
	private String terrainDragStatus(){return terrainGestureLabel+" "+(terrainDragActive?"dragging":"committing")+": "+terrainDragSeen.size()+" unique | pending "+terrainDragPending.size()+" | accepted "+terrainDragAccepted+(terrainDragHoverX>=0?" | hover "+terrainDragHoverX+","+terrainDragHoverY:"");}
	private static long terrainTileKey(int x,int y){return ((long)x<<32)^(y&0xffffffffL);}
	private int nextTerrainHistoryToken(){int token=terrainHistoryNextToken++;if(terrainHistoryNextToken<=0)terrainHistoryNextToken=1;return token;}
	private void sendTerrainStroke(){
		boolean wide=isLayeredTerrainDraft();mc.packetHandler.getClientStream().newPacket(152);mc.packetHandler.getClientStream().bufferBits.putByte(wide?7:6);
		mc.packetHandler.getClientStream().bufferBits.putLong(sessionId);mc.packetHandler.getClientStream().bufferBits.putInt(nextSequence);
		mc.packetHandler.getClientStream().bufferBits.putByte(editorLevel(terrainStrokeTiles[0][1]));mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeMask);
		if(wide){mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeElevationOperation);mc.packetHandler.getClientStream().bufferBits.putShort(terrainStrokeElevation);mc.packetHandler.getClientStream().bufferBits.putShort(terrainStrokeElevationStep);}
		else mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeElevation);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeColor);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeTexture);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeRoof);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeEastWall);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeNorthWall);
		mc.packetHandler.getClientStream().bufferBits.putInt(terrainStrokeDiagonal);mc.packetHandler.getClientStream().bufferBits.putInt(terrainStrokeHistoryToken);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeTiles.length);
		for(int[] tile:terrainStrokeTiles){mc.packetHandler.getClientStream().bufferBits.putShort(tile[0]);mc.packetHandler.getClientStream().bufferBits.putShort(tile[1]);}
		mc.packetHandler.getClientStream().finishPacket();
	}
	private void sendTerrainLine(int startX,int startY,int endX,int endY){
		mc.packetHandler.getClientStream().newPacket(152);mc.packetHandler.getClientStream().bufferBits.putByte(8);
		mc.packetHandler.getClientStream().bufferBits.putLong(sessionId);mc.packetHandler.getClientStream().bufferBits.putInt(nextSequence);
		mc.packetHandler.getClientStream().bufferBits.putByte(editorLevel(startY));mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeMask);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeElevationOperation);mc.packetHandler.getClientStream().bufferBits.putShort(terrainStrokeElevation);
		mc.packetHandler.getClientStream().bufferBits.putShort(terrainStrokeElevationStep);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeColor);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeTexture);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeRoof);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeEastWall);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeNorthWall);
		mc.packetHandler.getClientStream().bufferBits.putInt(terrainStrokeDiagonal);mc.packetHandler.getClientStream().bufferBits.putInt(terrainStrokeHistoryToken);mc.packetHandler.getClientStream().bufferBits.putByte(terrainBrushSize);
		mc.packetHandler.getClientStream().bufferBits.putShort(startX);mc.packetHandler.getClientStream().bufferBits.putShort(startY);
		mc.packetHandler.getClientStream().bufferBits.putShort(endX);mc.packetHandler.getClientStream().bufferBits.putShort(endY);mc.packetHandler.getClientStream().finishPacket();
	}
	private void sendTerrainRectangle(int startX,int startY,int endX,int endY){
		mc.packetHandler.getClientStream().newPacket(152);mc.packetHandler.getClientStream().bufferBits.putByte(9);
		mc.packetHandler.getClientStream().bufferBits.putLong(sessionId);mc.packetHandler.getClientStream().bufferBits.putInt(nextSequence);
		mc.packetHandler.getClientStream().bufferBits.putByte(editorLevel(startY));mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeMask);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeElevationOperation);mc.packetHandler.getClientStream().bufferBits.putShort(terrainStrokeElevation);
		mc.packetHandler.getClientStream().bufferBits.putShort(terrainStrokeElevationStep);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeColor);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeTexture);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeRoof);
		mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeEastWall);mc.packetHandler.getClientStream().bufferBits.putByte(terrainStrokeNorthWall);
		mc.packetHandler.getClientStream().bufferBits.putInt(terrainStrokeDiagonal);mc.packetHandler.getClientStream().bufferBits.putInt(terrainStrokeHistoryToken);
		int flags=rectangleOptions.rectangleFlags();
		mc.packetHandler.getClientStream().bufferBits.putByte(flags);mc.packetHandler.getClientStream().bufferBits.putByte(terrainSmartWall);
		mc.packetHandler.getClientStream().bufferBits.putShort(startX);mc.packetHandler.getClientStream().bufferBits.putShort(startY);
		mc.packetHandler.getClientStream().bufferBits.putShort(endX);mc.packetHandler.getClientStream().bufferBits.putShort(endY);mc.packetHandler.getClientStream().finishPacket();
	}
	public void inspectObject(int worldX,int worldY,int id,int direction,int type){inspectObject(worldX,worldY,id,direction,type,false);}
	public void inspectObject(int worldX,int worldY,int id,int direction,int type,boolean copy){recordWorldClick(worldX,worldY);copyNextInspection=copy;send(3,worldX,worldY,editorLevel(worldY),id,direction,type);}
	public void inspectNpc(int serverIndex){inspectNpc(serverIndex,false);}
	public void inspectNpc(int serverIndex,boolean copy){copyNextInspection=copy;send(4,0,0,0,serverIndex,0,0);}
	public void copyInspected(){
		if(inspectionKind.isEmpty())return;copiedInspectionKind=inspectionKind;copiedInspectionDetails=inspectionDetails.clone();
		if("Terrain".equals(inspectionKind)&&inspectedTerrainFields!=null){copiedTerrainFields=inspectedTerrainFields.clone();seedTerrain(inspectedTerrainFields);}
		if("Scenery".equals(inspectionKind)){int id=valueAfter(join(inspectionDetails),"id=");if(id>=0)setSceneryId(id);}
		if("NPC".equals(inspectionKind)){String text=join(inspectionDetails);int id=valueAfter(text,"id="),radius=valueAfter(text,"radius="),respawn=valueAfter(text,"respawn=");if(id>=0)setNpcId(id);if(radius>=0)setNpcRadius(radius);if(respawn>=-1)setNpcRespawnSeconds(respawn);}
		inspectionStatus="Copied "+inspectionKind.toLowerCase()+" inspection into its editor selection";
	}

	private void selectMode(Mode selected){
		if(terrainLineCommitTiles!=null){inspectionStatus="Wait for the authoritative line response before changing modes.";return;}
		definitionBrowser.close();
		if(selected==Mode.ITEMS&&!isLayeredTerrainDraft()){
			mode=Mode.NAVIGATE;
			rejectLayeredReviewMutation(
				"Respawning item authoring is available only in a layered Builder draft.");
			coordinateFocus=0;toolbar.open(WorldEditorToolbarState.Flyout.NAVIGATE);
			updatePresentationBounds();return;
		}
		if(isLayeredReview()&&((selected==Mode.TERRAIN&&!isLayeredPlacementDraftLevel())||(selected==Mode.SCENERY&&!isLayeredSceneryDraftLevel())||(selected==Mode.NPC&&!isLayeredPlacementDraftLevel())||(selected==Mode.ITEMS&&!isLayeredPlacementDraftLevel()))){
			mode=Mode.NAVIGATE;rejectLayeredReviewMutation(isLayeredTerrainDraft()
				?"Terrain, scenery, NPC, and ground-item editing are limited to Builder-created levels; boundaries remain locked."
				:"Layered package review is read-only; create a draft level before editing terrain.");
			coordinateFocus=0;toolbar.open(WorldEditorToolbarState.Flyout.NAVIGATE);updatePresentationBounds();return;
		}
		if(mode==Mode.TERRAIN&&selected!=Mode.TERRAIN){if(terrainDragActive)releaseTerrainDrag();clearTerrainLine();}
		if(mode==Mode.SCENERY&&selected!=Mode.SCENERY)clearSceneryMove();
		boolean same=mode==selected;mode=selected;coordinateFocus=0;replaceFocusedText=false;closeArmed=false;
		WorldEditorToolbarState.Flyout flyout=flyoutFor(selected);if(same)toolbar.selectMode(flyout);else toolbar.open(flyout);
		mc.setWorldEditorNavigateClickTeleport(mode==Mode.NAVIGATE&&clickTeleportPreferred);updatePresentationBounds();
	}
	private void setTerrainBuildMode(boolean enabled){terrainBuildMode=enabled;mc.setWorldEditorBuildMode(enabled);}
	private void setSceneryId(int id){if(!acceptDefinitionInput("scenery",id,EntityHandler.objectCount()-1)){sceneryIdText=sceneryId<0?"-":String.valueOf(sceneryId);return;}sceneryId=Math.max(0,Math.min(id,EntityHandler.objectCount()-1));sceneryIdText=String.valueOf(sceneryId);}
	private void setNpcId(int id){if(!acceptDefinitionInput("npc",id,EntityHandler.npcs.size()-1)){npcIdText=npcId<0?"-":String.valueOf(npcId);return;}npcId=Math.max(0,Math.min(id,EntityHandler.npcs.size()-1));npcIdText=String.valueOf(npcId);}
	private void setNpcRadius(int radius){npcRadius=Math.max(0,Math.min(radius,64));npcRadiusText=String.valueOf(npcRadius);}
	private void setNpcRespawnSeconds(int seconds){npcRespawnSeconds=Math.max(-1,Math.min(seconds,86400));npcRespawnText=String.valueOf(npcRespawnSeconds);}
	private String npcRespawnLabel(){return npcRespawnSeconds<0?"Definition default":npcRespawnSeconds==0?"Never":npcRespawnSeconds+" seconds";}
	private void setGroundItemId(int id){if(!acceptDefinitionInput("item",id,EntityHandler.itemCount()-1)){groundItemIdText=groundItemId<0?"-":String.valueOf(groundItemId);return;}groundItemId=Math.max(0,Math.min(id,EntityHandler.itemCount()-1));groundItemIdText=String.valueOf(groundItemId);if(!groundItemStackable())setGroundItemAmount(1);}
	private void setGroundItemAmount(int amount){groundItemAmount=groundItemStackable()?Math.max(1,Math.min(amount,MAX_GROUND_ITEM_AMOUNT)):1;groundItemAmountText=String.valueOf(groundItemAmount);}
	private void setGroundItemRespawnSeconds(int seconds){groundItemRespawnSeconds=Math.max(1,Math.min(seconds,86400));groundItemRespawnText=String.valueOf(groundItemRespawnSeconds);}
	private void setTerrainElevation(int value){terrainElevation=isLayeredTerrainDraft()?unsignedShort(value):rawByte(value);terrainElevationText=String.valueOf(terrainElevation);}
	private void setTerrainElevationStep(int value){terrainElevationStep=Math.max(1,Math.min(value,65535));terrainElevationStepText=String.valueOf(terrainElevationStep);}
	private void setTerrainFloorColor(int value){terrainFloorColor=rawByte(value);terrainFloorColorText=String.valueOf(terrainFloorColor);}
	private void setTerrainFloorTexture(int value){terrainFloorTexture=rawByte(value);terrainFloorTextureText=String.valueOf(terrainFloorTexture);}
	private void setTerrainRoof(int value){terrainRoof=Math.max(0,Math.min(value,EntityHandler.elevationCount()));terrainRoofText=String.valueOf(terrainRoof);}
	private void setTerrainEastWall(int value){if(!acceptWallInput(value)){terrainEastWallText=String.valueOf(terrainEastWall);return;}terrainEastWall=Math.max(0,Math.min(value,EntityHandler.doorCount()));terrainEastWallText=String.valueOf(terrainEastWall);}
	private void setTerrainNorthWall(int value){if(!acceptWallInput(value)){terrainNorthWallText=String.valueOf(terrainNorthWall);return;}terrainNorthWall=Math.max(0,Math.min(value,EntityHandler.doorCount()));terrainNorthWallText=String.valueOf(terrainNorthWall);}
	private void setTerrainDiagonalWall(int value){if(!acceptWallInput(value)){terrainDiagonalWallText=String.valueOf(terrainDiagonalWall);return;}terrainDiagonalWall=Math.max(0,Math.min(value,EntityHandler.doorCount()));terrainDiagonalWallText=String.valueOf(terrainDiagonalWall);}
	private void setTerrainSmartWall(int value){if(!acceptWallInput(value)){terrainSmartWallText=String.valueOf(terrainSmartWall);return;}terrainSmartWall=Math.max(0,Math.min(value,EntityHandler.doorCount()));terrainSmartWallText=String.valueOf(terrainSmartWall);}
	private boolean acceptDefinitionInput(String family,int id,int maximum){
		if(!WorldBuilderClientProfile.current().hasAuthoringDefinitionBinding())return true;
		if(id>=0&&id<=maximum&&definitionAllowed(family,id))return true;
		rejectDefinitionSelection(family,id);return false;
	}
	private boolean acceptWallInput(int raw){
		if(raw<0||raw>255){rejectDefinitionSelection("boundary",raw<=0?raw:raw-1);return false;}
		if(!WorldBuilderClientProfile.current().hasAuthoringDefinitionBinding())return true;
		if(raw==0)return true;
		if(raw>0&&raw<=EntityHandler.doorCount()&&definitionAllowed("boundary",raw-1))return true;
		rejectDefinitionSelection("boundary",raw<=0?raw:raw-1);return false;
	}
	private boolean definitionAllowed(String family,int id){return WorldBuilderClientProfile.current().isDefinitionAllowed(family,id);}
	private int[] projectDefinitionIds(String family){return WorldBuilderClientProfile.current().hasAuthoringDefinitionBinding()?WorldBuilderClientProfile.current().definitionIds(family):null;}
	private int[] projectFloorOverlayIds(){
		int[] ids=projectDefinitionIds("floor");if(ids==null)return null;
		java.util.TreeSet<Integer> overlays=new java.util.TreeSet<Integer>();overlays.add(Integer.valueOf(0));overlays.add(Integer.valueOf(WorldBuilderTerrainOverlay.BLOCKING_BASE_COLOR));
		for(int id:ids){if(id>=0&&id<255&&id+1!=250)overlays.add(Integer.valueOf(id+1));if(id==1)overlays.add(Integer.valueOf(250));}
		int[] result=new int[overlays.size()];int index=0;for(Integer overlay:overlays)result[index++]=overlay.intValue();return result;
	}
	private int terrainWallValue(int field){switch(field){case 10:return terrainNorthWall;case 11:return terrainEastWall;case 12:return terrainDiagonalWall;case 18:return terrainSmartWall;default:return 0;}}
	private void setTerrainWallValue(int field,int value){switch(field){case 10:setTerrainNorthWall(value);break;case 11:setTerrainEastWall(value);break;case 12:setTerrainDiagonalWall(value);break;case 18:setTerrainSmartWall(value);break;default:break;}}
	private void rejectDefinitionSelection(String family,int id){
		inspectionStatus="Project-bound "+family+" definition ID "+id+" is unavailable.";
		inspectionDetails=new String[]{"Choose an ID exposed by this project's definition browser."};
		mc.showWorldEditorStatus(inspectionStatus);
	}
	private void normalizeProjectBoundSelections(){
		if(!WorldBuilderClientProfile.current().hasAuthoringDefinitionBinding())return;
		sceneryId=normalizedProjectId("scenery",sceneryId);sceneryIdText=sceneryId<0?"-":String.valueOf(sceneryId);
		npcId=normalizedProjectId("npc",npcId);npcIdText=npcId<0?"-":String.valueOf(npcId);
		groundItemId=normalizedProjectId("item",groundItemId);groundItemIdText=groundItemId<0?"-":String.valueOf(groundItemId);
		if(groundItemId>=0&&!groundItemStackable())setGroundItemAmount(1);
	}
	private int normalizedProjectId(String family,int current){int[] ids=projectDefinitionIds(family);if(ids==null||ids.length==0)return -1;for(int id:ids)if(id==current)return current;return ids[0];}
	private int steppedProjectId(String family,int current,int amount){
		int[] ids=projectDefinitionIds(family);if(ids==null)return current+amount;if(ids.length==0)return current;
		int index=java.util.Arrays.binarySearch(ids,current);if(index<0)index=amount<0?ids.length: -1;
		return ids[Math.max(0,Math.min(ids.length-1,index+(amount<0?-1:1)))];
	}
	private int steppedWallValue(int current,int amount){
		if(!WorldBuilderClientProfile.current().hasAuthoringDefinitionBinding())return current+amount;
		int[] ids=projectDefinitionIds("boundary");if(ids.length==0)return 0;
		if(current==0)return amount<0?0:ids[0]+1;
		int id=current-1,index=java.util.Arrays.binarySearch(ids,id);if(index<0)index=amount<0?ids.length: -1;
		int next=index+(amount<0?-1:1);return next<0?0:ids[Math.min(ids.length-1,next)]+1;
	}
	private void seedTerrain(int[] fields){setTerrainElevation(fields[0]);setTerrainFloorColor(fields[1]);setTerrainFloorTexture(fields[2]);setTerrainRoof(fields[3]);setTerrainEastWall(fields[4]);setTerrainNorthWall(fields[5]);int diagonal=fields[6];terrainDiagonalOrientation=diagonal>12000?1:0;setTerrainDiagonalWall(diagonal>12000?diagonal-12000:diagonal);}
	private int encodedDiagonalWall(){return terrainDiagonalWall==0?0:(terrainDiagonalOrientation==0?terrainDiagonalWall:12000+terrainDiagonalWall);}
	private static int rawByte(int value){return Math.max(0,Math.min(value,255));}
	private static int unsignedShort(int value){return Math.max(0,Math.min(value,65535));}
	private void teleportToFields(){
		try{int x=Integer.parseInt(teleportX),y=Integer.parseInt(teleportY),level=Integer.parseInt(teleportLevel);
			if(x<0||x>32767||y<0||y>32767||!validTeleportLevel(level))throw new NumberFormatException();
			lastClickedX=x;lastClickedY=y;lastClickedLevel=level;coordinateFocus=0;mc.worldEditorTeleport(x,y,level);
		}catch(NumberFormatException e){inspectionStatus=isLayeredTerrainDraft()
			?"X/Y must be 0..32767; Level may be any signed whole number."
			:isLayeredReview()
			?"X/Y must be 0..32767 and Level must be one of "+WorldBuilderClientProfile.current().layeredLevelsLabel()
			:"Coordinates must be whole numbers from 0 to 32767";inspectionDetails=new String[0];}
	}
	private void send(int type,int x,int y,int plane,int id,int direction,int subtype){
		if(!isEditorOpen())return;mc.packetHandler.getClientStream().newPacket(152);mc.packetHandler.getClientStream().bufferBits.putByte(type);
		mc.packetHandler.getClientStream().bufferBits.putLong(sessionId);mc.packetHandler.getClientStream().bufferBits.putInt(nextSequence);
		if(type==2){mc.packetHandler.getClientStream().bufferBits.putShort(x);mc.packetHandler.getClientStream().bufferBits.putShort(y);mc.packetHandler.getClientStream().bufferBits.putByte(plane);mc.packetHandler.getClientStream().bufferBits.putByte(subtype);}
		else if(type==3){mc.packetHandler.getClientStream().bufferBits.putShort(x);mc.packetHandler.getClientStream().bufferBits.putShort(y);mc.packetHandler.getClientStream().bufferBits.putByte(plane);mc.packetHandler.getClientStream().bufferBits.putShort(id);mc.packetHandler.getClientStream().bufferBits.putByte(direction);mc.packetHandler.getClientStream().bufferBits.putByte(subtype);}
		else if(type==4)mc.packetHandler.getClientStream().bufferBits.putShort(id);mc.packetHandler.getClientStream().finishPacket();
	}

	private boolean handleKey(char c,int key){
		if(!mc.isAdaptiveWorldStateReadyForEditor())return true;
		if(definitionBrowser.isOpen())return handleDefinitionBrowserKey(c,key);
		WorldEditorKeyboardShortcuts.Action shortcut=WorldEditorKeyboardShortcuts.resolve(c,key,mc.getDesktopKeyCode(),mc.controlPressed,mc.shiftPressed,mode==Mode.TERRAIN,keyboardShortcutsEnabled);
		if(shortcut==WorldEditorKeyboardShortcuts.Action.TOGGLE_CHAT){
			keyboardShortcutsEnabled=!keyboardShortcutsEnabled;coordinateFocus=0;replaceFocusedText=false;
			inspectionStatus=keyboardShortcutsEnabled?"Editor shortcuts enabled; Ctrl+Enter opens chat input.":"Chat input enabled; Ctrl+Enter restores editor shortcuts.";
			return true;
		}
		if(key==27){
			coordinateFocus=0;replaceFocusedText=false;
			if(terrainLineCommitTiles!=null){inspectionStatus="The terrain operation is already committing; wait for the authoritative result.";return true;}
			if(terrainLineAnchorX>=0){terrainLineAnchorX=terrainLineAnchorY=-1;inspectionStatus=(terrainTool==TerrainTool.RECTANGLE?"Rectangle corner":"Line anchor")+" cancelled.";return true;}
			if(isSceneryMoveArmed()){clearSceneryMove();inspectionStatus="Scenery move cancelled; the source was not changed.";return true;}
			if(isRegionSelecting()&&!regionMarkers.isEmpty()){cancelRegionSelection();return true;}
			if(toolbar.isExpandedFallback()){toolbar.setExpandedFallback(false);updatePresentationBounds();return true;}
			if(toolbar.closeFlyout()){updatePresentationBounds();return true;}
			requestEditorClose();return true;
		}
		if(coordinateFocus==0){
			if(!keyboardShortcutsEnabled)return false;
			if(shortcut!=WorldEditorKeyboardShortcuts.Action.NONE)applyKeyboardShortcut(shortcut);
			return true;
		}
		if(coordinateFocus==19){
			if(key==8){if(replaceFocusedText)regionName="";else if(regionName.length()>0)regionName=regionName.substring(0,regionName.length()-1);replaceFocusedText=false;return true;}
			if(key==10||key==13){coordinateFocus=0;replaceFocusedText=false;if(regionName.trim().isEmpty())regionName="Region snapshot";return true;}
			if(c>=0x20&&c!=0x7f&&c!='\uffff'&&!Character.isSurrogate(c)&&regionName.length()<128){regionName=replaceFocusedText?String.valueOf(c):regionName+c;replaceFocusedText=false;}return true;
		}
		String value=focusedText();
		if(key==8){if(replaceFocusedText)value="";else if(value.length()>0)value=value.substring(0,value.length()-1);replaceFocusedText=false;}
		else if(key==9){
			if(coordinateFocus==1)coordinateFocus=2;
			else if(coordinateFocus==2)coordinateFocus=isLayeredReview()?13:1;
			else if(coordinateFocus==13)coordinateFocus=1;
			replaceFocusedText=true;return true;
		}
		else if((key==10||key==13)&&!value.isEmpty()){applyFocusedValue(value);return true;}
		else if(c=='-'&&coordinateFocus==13&&(replaceFocusedText||value.isEmpty())){value="-";replaceFocusedText=false;}
		else if(c>='0'&&c<='9'&&(replaceFocusedText||value.length()<5)){value=replaceFocusedText?String.valueOf(c):value+c;replaceFocusedText=false;}
		else return true;
		setFocusedText(value);return true;
	}
	private boolean handleDefinitionBrowserKey(char c,int key){
		if(key==27){closeDefinitionBrowser();return true;}
		if(key==8){definitionBrowser.backspace();return true;}
		if(key==10||key==13){WorldEditorDefinitionCatalog.Entry first=definitionBrowser.resultAtVisibleSlot(0);if(first!=null)selectDefinitionBrowserEntry(first);return true;}
		definitionBrowser.append(c);return true;
	}
	private void applyKeyboardShortcut(WorldEditorKeyboardShortcuts.Action shortcut){
		switch(shortcut){
			case UNDO:requestTerrainHistory(false);return;
			case REDO:requestTerrainHistory(true);return;
			case SAVE:requestWorldEditSave();return;
			case BRUSH:if(mode==Mode.TERRAIN&&terrainActiveField==0)toggleBrushSize();else openTerrainTool(0);return;
			case NAVIGATE:
				if(mode!=Mode.NAVIGATE){selectMode(Mode.NAVIGATE);return;}
				clickTeleportPreferred=!clickTeleportPreferred;mc.setWorldEditorNavigateClickTeleport(clickTeleportPreferred);
				inspectionStatus="Navigate click teleport "+(clickTeleportPreferred?"enabled":"disabled")+".";return;
			case INSPECT:if(mode==Mode.INSPECT)copyInspected();else selectMode(Mode.INSPECT);return;
			case DOCK:
				coordinateFocus=0;replaceFocusedText=false;if(toolbar.isExpandedFallback())toolbar.setExpandedFallback(false);
				definitionBrowser.close();toolbar.toggleCollapsed();updatePresentationBounds();return;
			case TOGGLE_ELEVATION:toggleTerrainField(6);return;
			case TOGGLE_FLOOR_COLOR:toggleTerrainField(7);return;
			case TOGGLE_FLOOR_TEXTURE:toggleTerrainField(8);return;
			case TOGGLE_ROOF:toggleTerrainField(9);return;
			case TOGGLE_NORTH_WALL:toggleTerrainField(10);return;
			case TOGGLE_EAST_WALL:toggleTerrainField(11);return;
			case TOGGLE_DIAGONAL_WALL:toggleTerrainField(12);return;
			case EDIT_ELEVATION:openTerrainValueEditor(6);return;
			case EDIT_FLOOR_COLOR:openTerrainValueEditor(7);return;
			case EDIT_FLOOR_TEXTURE:openTerrainValueEditor(8);return;
			case EDIT_ROOF:openTerrainValueEditor(9);return;
			case EDIT_NORTH_WALL:openTerrainValueEditor(10);return;
			case EDIT_EAST_WALL:openTerrainValueEditor(11);return;
			case EDIT_DIAGONAL_WALL:openTerrainValueEditor(12);return;
			default:return;
		}
	}
	private void openTerrainValueEditor(int field){
		if(toolbar.isCollapsed())toolbar.toggleCollapsed();openTerrainTool(field);focusNumber(field);updatePresentationBounds();
	}
	private void openSceneryBrowser(){
		coordinateFocus=0;replaceFocusedText=false;toolbar.open(WorldEditorToolbarState.Flyout.SCENERY);
		definitionBrowser.open(WorldEditorDefinitionBrowser.Family.SCENERY,sceneryId,projectDefinitionIds("scenery"));updatePresentationBounds();
	}
	private void openNpcBrowser(){
		coordinateFocus=0;replaceFocusedText=false;toolbar.open(WorldEditorToolbarState.Flyout.NPC);
		definitionBrowser.open(WorldEditorDefinitionBrowser.Family.NPC,npcId,projectDefinitionIds("npc"));updatePresentationBounds();
	}
	private void openGroundItemBrowser(){
		coordinateFocus=0;replaceFocusedText=false;toolbar.open(WorldEditorToolbarState.Flyout.ITEMS);
		definitionBrowser.open(WorldEditorDefinitionBrowser.Family.ITEM,groundItemId,projectDefinitionIds("item"));updatePresentationBounds();
	}
	private void openWallBrowser(int field){
		coordinateFocus=0;replaceFocusedText=false;definitionBrowserTerrainField=field;
		toolbar.open(WorldEditorToolbarState.Flyout.TERRAIN);
		int raw=terrainWallValue(field);int selected=raw==0?-1:raw-1;
		definitionBrowser.open(WorldEditorDefinitionBrowser.Family.BOUNDARY,selected,projectDefinitionIds("boundary"));updatePresentationBounds();
	}
	private void openFloorBrowser(){
		coordinateFocus=0;replaceFocusedText=false;definitionBrowserTerrainField=8;
		toolbar.open(WorldEditorToolbarState.Flyout.TERRAIN);
		definitionBrowser.open(WorldEditorDefinitionBrowser.Family.FLOOR,terrainFloorTexture,projectFloorOverlayIds());updatePresentationBounds();
	}
	private void closeDefinitionBrowser(){definitionBrowser.close();definitionBrowserTerrainField=0;updatePresentationBounds();}
	private void selectDefinitionBrowserEntry(WorldEditorDefinitionCatalog.Entry entry){
		if(entry==null)return;
		switch(definitionBrowser.family()){
			case NPC:setNpcId(entry.id());break;
			case ITEM:setGroundItemId(entry.id());break;
			case SCENERY:setSceneryId(entry.id());break;
			case FLOOR:setTerrainFloorTexture(entry.id());break;
			case BOUNDARY:setTerrainWallValue(definitionBrowserTerrainField,entry.id()+1);break;
			default:return;
		}
		inspectionStatus="Selected "+entry.displayName()+" [#"+entry.id()+"] from search.";closeDefinitionBrowser();
	}
	public boolean scrollDefinitionBrowser(int delta){
		if(!definitionBrowser.isOpen())return false;int left=getX()+definitionBrowserOffsetX(),top=getY();
		if(compactMouseX<left||compactMouseX>=left+BROWSER_WIDTH||compactMouseY<top||compactMouseY>=top+BROWSER_HEIGHT)return false;
		if(delta!=0)definitionBrowser.scrollRows(delta>0?1:-1);return true;
	}
	private void applyFocusedValue(String value){
		try{int parsed=Integer.parseInt(value);if(coordinateFocus==1||coordinateFocus==2||coordinateFocus==13){teleportToFields();return;}if(coordinateFocus==3)setSceneryId(parsed);else if(coordinateFocus==4)setNpcId(parsed);else if(coordinateFocus==5)setNpcRadius(parsed);else if(coordinateFocus==20)setNpcRespawnSeconds(parsed);else if(coordinateFocus==14)setGroundItemId(parsed);else if(coordinateFocus==15)setGroundItemAmount(parsed);else if(coordinateFocus==16)setGroundItemRespawnSeconds(parsed);else if(coordinateFocus==17)setTerrainElevationStep(parsed);else if(coordinateFocus==18)setTerrainSmartWall(parsed);else if(coordinateFocus==6)setTerrainElevation(parsed);else if(coordinateFocus==7)setTerrainFloorColor(parsed);else if(coordinateFocus==8)setTerrainFloorTexture(parsed);else if(coordinateFocus==9)setTerrainRoof(parsed);else if(coordinateFocus==10)setTerrainNorthWall(parsed);else if(coordinateFocus==11)setTerrainEastWall(parsed);else setTerrainDiagonalWall(parsed);}
		catch(NumberFormatException ignored){}coordinateFocus=0;
	}
	private String focusedText(){switch(coordinateFocus){case 1:return teleportX;case 2:return teleportY;case 13:return teleportLevel;case 3:return sceneryIdText;case 4:return npcIdText;case 5:return npcRadiusText;case 20:return npcRespawnText;case 14:return groundItemIdText;case 15:return groundItemAmountText;case 16:return groundItemRespawnText;case 17:return terrainElevationStepText;case 18:return terrainSmartWallText;case 19:return regionName;case 6:return terrainElevationText;case 7:return terrainFloorColorText;case 8:return terrainFloorTextureText;case 9:return terrainRoofText;case 10:return terrainNorthWallText;case 11:return terrainEastWallText;default:return terrainDiagonalWallText;}}
	private void setFocusedText(String value){switch(coordinateFocus){case 1:teleportX=value;break;case 2:teleportY=value;break;case 13:teleportLevel=value;break;case 3:sceneryIdText=value;break;case 4:npcIdText=value;break;case 5:npcRadiusText=value;break;case 20:npcRespawnText=value;break;case 14:groundItemIdText=value;break;case 15:groundItemAmountText=value;break;case 16:groundItemRespawnText=value;break;case 17:terrainElevationStepText=value;break;case 18:terrainSmartWallText=value;break;case 19:regionName=value;break;case 6:terrainElevationText=value;break;case 7:terrainFloorColorText=value;break;case 8:terrainFloorTextureText=value;break;case 9:terrainRoofText=value;break;case 10:terrainNorthWallText=value;break;case 11:terrainEastWallText=value;break;default:terrainDiagonalWallText=value;}}
	private void focusNumber(int focus){coordinateFocus=focus;replaceFocusedText=true;}
	private void rejectLayeredReviewMutation(String message){inspectionStatus=message;mc.showWorldEditorStatus(message);}
	private boolean hasPendingAuthoritativeEdits(){return terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragActive||terrainDragReleasePending||entityEditTracker.isPending();}
	private int pendingAuthoritativeEditCount(){return Math.max(1,terrainDragPending.size()+(terrainStrokeTiles==null?0:terrainStrokeTiles.length)+(terrainLineCommitTiles==null?0:terrainLineCommitTiles.length-terrainLineReceived)+entityEditTracker.pendingCount());}
	private void submitWorldEditSave(){submitWorldEditSave("World edit save requested; wait for the completion message before closing.");}
	private void submitWorldEditSave(String statusMessage){mc.sendCommandString("saveworldedits");saveAfterPendingEdits=false;deferredSaveProgressNanos=0L;entityEditTracker.clearQueuedSave();saveRequested=true;closeArmed=false;inspectionStatus=isLayeredTerrainDraft()?"Layered draft save requested; it will commit to working/ when this Builder closes.":"World edit save started; building resumes when completion is reported.";mc.showWorldEditorStatus(statusMessage);}
	private void maybeSubmitDeferredSave(){if(!saveAfterPendingEdits||saveRequested||hasPendingAuthoritativeEdits())return;submitWorldEditSave();}
	private void noteDeferredSaveProgress(long now){if(saveAfterPendingEdits)deferredSaveProgressNanos=now;}
	private void requestWorldEditSave(){if(saveRequested){inspectionStatus="World edit save is already in progress.";mc.showWorldEditorStatus(inspectionStatus);return;}if(saveAfterPendingEdits){inspectionStatus="World edit save is already queued; waiting for "+pendingAuthoritativeEditCount()+" authoritative edit response"+(pendingAuthoritativeEditCount()==1?"":"s")+".";mc.showWorldEditorStatus(inspectionStatus);return;}if(isLayeredReview()&&!isLayeredTerrainDraft()){rejectLayeredReviewMutation("Layered package review is read-only; no files were changed.");saveRequested=false;return;}if(terrainDragActive)releaseTerrainDrag();if(hasPendingAuthoritativeEdits()){saveAfterPendingEdits=true;entityEditTracker.noteSaveQueued();deferredSaveProgressNanos=System.nanoTime();inspectionStatus="Save queued; waiting for "+pendingAuthoritativeEditCount()+" authoritative edit response"+(pendingAuthoritativeEditCount()==1?"":"s")+".";mc.showWorldEditorStatus(inspectionStatus);return;}submitWorldEditSave();}
	private void pollDeferredSave(){
		if(!saveAfterPendingEdits||saveRequested)return;
		if(!hasPendingAuthoritativeEdits()){submitWorldEditSave();return;}
		long now=System.nanoTime();if(deferredSaveProgressNanos==0L){deferredSaveProgressNanos=now;return;}
		if(now-deferredSaveProgressNanos<DEFERRED_SAVE_TIMEOUT_NANOS)return;
		int unacknowledged=pendingAuthoritativeEditCount();
		terrainStrokeTiles=null;terrainStrokeStartedNanos=0L;clearTerrainLine();clearTerrainDrag();entityEditTracker.reset();
		submitWorldEditSave("Timed out waiting for "+unacknowledged+" edit response"+(unacknowledged==1?"":"s")+"; saving every change accepted by the server. Reopen after completion to reconcile unacknowledged edits.");
	}
	private void requestTerrainHistory(boolean redo){
		if(!isLayeredTerrainDraft()){inspectionStatus="Operation Undo/Redo is available in an editable layered Builder project.";return;}
		if(terrainHistoryPending||terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragActive||terrainDragReleasePending||entityEditTracker.isPending()){inspectionStatus="Wait for the current authoritative edit before using Undo or Redo.";return;}
		// Availability is presentation state, not authority. Placements arrive on
		// a separate message stream, so a missed/stale hint must never prevent the
		// server from answering a legitimate Undo or Redo request.
		terrainHistoryPending=true;terrainHistoryTotal=terrainHistoryReceived=0;send(redo?11:10,0,0,0,0,0,0);
		inspectionStatus=redo?"Redoing the next Builder operation...":"Undoing the last Builder operation...";
	}
	private void requestEditorClose(){
		if(terrainLineCommitTiles!=null){inspectionStatus="Wait for the authoritative terrain response before closing.";return;}
		if(saveRequested||saveAfterPendingEdits){inspectionStatus="Wait for the active world edit save to finish before closing.";mc.showWorldEditorStatus(inspectionStatus);return;}
		if(unsavedChanges&&!closeArmed){closeArmed=true;inspectionStatus="Unsaved edits remain. Select Close again to exit without saving.";return;}
		setTerrainBuildMode(false);mc.setWorldEditorNavigateClickTeleport(false);clearTerrainLine();clearSceneryMove();definitionBrowser.close();send(1,0,0,0,0,0,0);setVisible(false);
	}
	private static WorldEditorToolbarState.Flyout flyoutFor(Mode selected){
		switch(selected){case INSPECT:return WorldEditorToolbarState.Flyout.INSPECT;case TERRAIN:return WorldEditorToolbarState.Flyout.TERRAIN;
			case SCENERY:return WorldEditorToolbarState.Flyout.SCENERY;case NPC:return WorldEditorToolbarState.Flyout.NPC;case ITEMS:return WorldEditorToolbarState.Flyout.ITEMS;case REGION:return WorldEditorToolbarState.Flyout.REGION;default:return WorldEditorToolbarState.Flyout.NAVIGATE;}
	}
	private void updatePresentationBounds(){
		int width=basePresentationWidth(),height;if(toolbar.isExpandedFallback())height=330;else{
			setLocation(8,8);height=toolbar.isCollapsed()?38:DOCK_HEIGHT;}
		if(definitionBrowser.isOpen()){width+=BROWSER_GAP+BROWSER_WIDTH;height=Math.max(height,BROWSER_HEIGHT);}setSize(width,height);
	}
	private int basePresentationWidth(){return toolbar.isExpandedFallback()?EXPANDED_WIDTH:toolbar.isCollapsed()?40:toolbar.isFlyoutOpen()?DOCK_WIDTH+FLYOUT_GAP+FLYOUT_WIDTH:DOCK_WIDTH;}
	private int definitionBrowserOffsetX(){return basePresentationWidth()+BROWSER_GAP;}
	private boolean handleMouse(int mx,int my,int down,int click){
		if(!mc.isAdaptiveWorldStateReadyForEditor())return true;
		if(!isVisible())return false;int rx=mx-getX(),ry=my-getY();
		if(rx<0||ry<0||ry>=getHeight())return false;
		if(definitionBrowser.isOpen()){
			int browserX=definitionBrowserOffsetX();
			if(rx>=browserX&&rx<browserX+BROWSER_WIDTH)return handleDefinitionBrowserMouse(rx-browserX,ry,click);
			if(rx>=browserX-BROWSER_GAP)return true;
		}
		if(toolbar.isExpandedFallback())return handleExpandedMouse(mx,my,down,click);
		if(click==0)return true;
		if(click!=1&&click!=2)return false;
		if(rx<DOCK_WIDTH){
			if(dockHit(rx,ry,0,0)){if(click==1){coordinateFocus=0;definitionBrowser.close();toolbar.toggleCollapsed();updatePresentationBounds();}return true;}
			if(toolbar.isCollapsed())return true;
			Mode selected=dockModeAt(rx,ry);if(selected!=null){if(click==1)selectMode(selected);return true;}
			if(mode==Mode.REGION&&dockHit(rx,ry,1,0)){if(click==1)selectRegionTool(RegionTool.COPY);return true;}
			if(mode==Mode.REGION&&dockHit(rx,ry,1,1)){if(click==1)selectRegionTool(RegionTool.CUT);return true;}
			if(mode==Mode.REGION&&dockHit(rx,ry,1,2)){if(click==1)selectRegionTool(RegionTool.PASTE);return true;}
			int action=contextActionAtDock(rx,ry);if(action>=0){if(click==1)selectContextAction(action);return true;}
			if(mode==Mode.TERRAIN&&terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()){
				if(dockHit(rx,ry,1,4)){if(click==2)rectangleOptions.toggleNorthWall();else openTerrainTool(18);clearTerrainLine();return true;}
				if(dockHit(rx,ry,1,5)){if(click==2)rectangleOptions.toggleEastWall();else openTerrainTool(18);clearTerrainLine();return true;}
				if(dockHit(rx,ry,1,6)){if(click==1)selectTerrainTool(TerrainTool.RECTANGLE);return true;}
			}
			int field=terrainFieldAtDock(rx,ry);if(field>=0){if(click==2)toggleTerrainField(field);else openTerrainTool(field);return true;}
			TerrainTool terrainSelection=terrainToolAtDock(rx,ry);if(terrainSelection!=null){if(click==1)selectTerrainTool(terrainSelection);return true;}
			if(dockHit(rx,ry,0,7)){if(click==2)toggleBrushSize();else selectTerrainTool(TerrainTool.FREEHAND);return true;}
			if(dockHit(rx,ry,0,8)){if(click==1)setTerrainBuildMode(!terrainBuildMode);return true;}
			if(dockHit(rx,ry,0,9)){if(click==1)requestTerrainHistory(false);return true;}
			if(dockHit(rx,ry,0,10)){if(click==1)requestTerrainHistory(true);return true;}
			if(dockHit(rx,ry,0,11)){if(click==1)requestWorldEditSave();return true;}
			if(dockHit(rx,ry,0,12)){if(click==1)requestEditorClose();return true;}
			return true;
		}
		if(!toolbar.isFlyoutOpen()||rx<DOCK_WIDTH+FLYOUT_GAP)return false;
		int fx=rx-(DOCK_WIDTH+FLYOUT_GAP);
		if(ry<28){
			if(click==1&&fx>=100&&fx<136)toolbar.togglePinned();
			else if(click==1&&fx>=138&&fx<178){toolbar.setExpandedFallback(true);updatePresentationBounds();}
			return true;
		}
		if(click==2)return true;
		if(mode==Mode.NAVIGATE)handleCompactNavigateMouse(fx,ry);
		else if(mode==Mode.INSPECT)handleCompactInspectMouse(fx,ry);
		else if(mode==Mode.TERRAIN)handleCompactTerrainMouse(fx,ry);
		else if(mode==Mode.SCENERY)handleCompactSceneryMouse(fx,ry);
		else if(mode==Mode.NPC)handleCompactNpcMouse(fx,ry);
		else if(mode==Mode.ITEMS)handleCompactGroundItemMouse(fx,ry);
		else handleCompactRegionMouse(fx,ry);
		return true;
	}
	private static boolean hitRow(int y,int start){return y>=start&&y<start+28;}
	private static boolean dockHit(int x,int y,int column,int row){int startX=column==0?DOCK_LEFT:DOCK_RIGHT;return x>=startX&&x<startX+28&&hitRow(y,DOCK_TOP+row*DOCK_STEP);}
	private Mode dockModeAt(int x,int y){if(dockHit(x,y,0,1))return Mode.NAVIGATE;if(dockHit(x,y,0,2))return Mode.INSPECT;if(dockHit(x,y,0,3))return Mode.SCENERY;if(dockHit(x,y,0,4))return Mode.NPC;if(dockHit(x,y,0,5))return Mode.ITEMS;if(dockHit(x,y,0,6))return Mode.REGION;return null;}
	private int contextActionAtDock(int x,int y){
		if(mode==Mode.SCENERY){if(dockHit(x,y,1,0))return 0;if(dockHit(x,y,1,1))return 1;if(dockHit(x,y,1,2))return 2;if(dockHit(x,y,1,3))return 3;}
		else if(mode==Mode.NPC||mode==Mode.ITEMS){if(dockHit(x,y,1,0))return 0;if(dockHit(x,y,1,1))return 1;}
		return -1;
	}
	private void selectContextAction(int action){
		boolean same=false;
		if(mode==Mode.SCENERY){SceneryTool selected=action==0?SceneryTool.PLACE:action==1?SceneryTool.MOVE:action==2?SceneryTool.ROTATE:SceneryTool.REMOVE;same=sceneryTool==selected;clearSceneryMove();sceneryTool=selected;}
		else if(mode==Mode.NPC){NpcTool selected=action==0?NpcTool.PLACE:NpcTool.REMOVE;same=npcTool==selected;npcTool=selected;}
		else if(mode==Mode.ITEMS){GroundItemTool selected=action==0?GroundItemTool.PLACE:GroundItemTool.REMOVE;same=groundItemTool==selected;groundItemTool=selected;}
		else return;
		definitionBrowser.close();coordinateFocus=0;replaceFocusedText=false;closeArmed=false;
		WorldEditorToolbarState.Flyout flyout=flyoutFor(mode);if(same)toolbar.selectMode(flyout);else toolbar.open(flyout);updatePresentationBounds();
	}
	private int terrainFieldAtDock(int x,int y){if(mode!=Mode.TERRAIN)return -1;if(dockHit(x,y,1,0))return 6;if(dockHit(x,y,1,1))return 7;if(dockHit(x,y,1,2))return 8;if(dockHit(x,y,1,3))return 9;if(terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls())return -1;if(dockHit(x,y,1,4))return 10;if(dockHit(x,y,1,5))return 11;if(dockHit(x,y,1,6))return 12;return -1;}
	private TerrainTool terrainToolAtDock(int x,int y){if(mode!=Mode.TERRAIN)return null;if(dockHit(x,y,1,7))return TerrainTool.FREEHAND;if(dockHit(x,y,1,8))return TerrainTool.LINE;if(dockHit(x,y,1,9))return TerrainTool.RECTANGLE;return null;}
	private void selectTerrainTool(TerrainTool selected){
		if(selected==null)return;if(terrainStrokeTiles!=null||terrainLineCommitTiles!=null||terrainDragReleasePending){inspectionStatus="Wait for the current terrain operation before changing tools.";return;}if(terrainDragActive)releaseTerrainDrag();terrainTool=selected;clearTerrainLine();closeArmed=false;
		definitionBrowser.close();mode=Mode.TERRAIN;terrainActiveField=0;coordinateFocus=0;replaceFocusedText=false;toolbar.open(WorldEditorToolbarState.Flyout.TERRAIN);mc.setWorldEditorNavigateClickTeleport(false);updatePresentationBounds();
		inspectionStatus=selected==TerrainTool.FREEHAND?"Freehand selected: click once or Ctrl-drag to paint.":selected==TerrainTool.LINE?"Line selected: click an anchor, preview, then click the destination.":"Rectangle selected: click two opposite corners; Smart Walls is on by default.";
	}
	private void openTerrainTool(int field){
		if(isLayeredReview()&&!isLayeredTerrainDraft()){selectMode(Mode.TERRAIN);return;}
		definitionBrowser.close();mode=Mode.TERRAIN;terrainActiveField=field;if(field>0)terrainStructureTab=field>=9;coordinateFocus=0;replaceFocusedText=false;closeArmed=false;
		mc.setWorldEditorNavigateClickTeleport(false);toolbar.open(WorldEditorToolbarState.Flyout.TERRAIN);updatePresentationBounds();
	}
	private void toggleBrushSize(){terrainBrushSize=WorldEditorTerrainBrush.nextSize(terrainBrushSize);closeArmed=false;}
	private void toggleTerrainField(int field){
		switch(field){case 6:paintElevation=!paintElevation;break;case 7:paintFloorColor=!paintFloorColor;break;case 8:paintFloorTexture=!paintFloorTexture;break;
			case 9:paintRoof=!paintRoof;break;case 10:rectangleOptions.toggleNorthWall();break;case 11:rectangleOptions.toggleEastWall();break;case 12:rectangleOptions.toggleDiagonalWall();break;case 18:rectangleOptions.toggleBothCardinalWalls();break;default:return;}
		closeArmed=false;
	}
	private void handleCompactNavigateMouse(int x,int y){
		if(y>=74&&y<98){clickTeleportPreferred=!clickTeleportPreferred;mc.setWorldEditorNavigateClickTeleport(clickTeleportPreferred);return;}
		if(y>=118&&y<142){
			if(!isLayeredReview()){if(x<90)focusNumber(1);else focusNumber(2);}
			else if(x<62)focusNumber(1);else if(x<120)focusNumber(2);else focusNumber(13);
			return;
		}if(y>=148&&y<172){coordinateFocus=0;teleportToFields();}
	}
	private void handleCompactInspectMouse(int x,int y){if(y>=158&&y<182&&!inspectionKind.isEmpty())copyInspected();}
	private void handleCompactTerrainMouse(int x,int y){
		if(terrainActiveField==0){if(terrainTool==TerrainTool.RECTANGLE){if(y>=58&&y<82)rectangleOptions.setFill(x>=90);else if(y>=88&&y<112)rectangleOptions.toggleSmartWalls();else if(y>=118&&y<142){if(x<40)setTerrainSmartWall(steppedWallValue(terrainSmartWall,-1));else if(x<132)focusNumber(18);else setTerrainSmartWall(steppedWallValue(terrainSmartWall,1));}else if(y>=148&&y<172){if(x<88)rectangleOptions.toggleNorthWall();else rectangleOptions.toggleEastWall();}clearTerrainLine();return;}if(y>=58&&y<82)terrainBrushSize=1;else if(y>=88&&y<112)terrainBrushSize=3;else if(y>=118&&y<142)terrainBrushSize=5;else if(y>=148&&y<172)terrainBrushSize=7;return;}
		if(y>=58&&y<82){if(x>=8&&x<38)adjustActiveTerrain(-1);else if(x>=42&&x<130)focusNumber(terrainActiveField);else if(x>=134&&x<164)adjustActiveTerrain(1);return;}
		if(terrainActiveField==6&&isLayeredTerrainDraft()){if(y>=90&&y<114){terrainElevationOperation=x<60?0:x<114?1:2;return;}if(y>=120&&y<144){if(x<60)setTerrainElevationStep(terrainElevationStep-1);else if(x<114)focusNumber(17);else setTerrainElevationStep(terrainElevationStep+1);return;}}
		boolean wall=terrainActiveField==10||terrainActiveField==11||terrainActiveField==12||terrainActiveField==18;
		if((terrainActiveField==8||wall)&&y>=90&&y<114){if(terrainActiveField==8)openFloorBrowser();else openWallBrowser(terrainActiveField);return;}
		int toggleY=terrainActiveField==6&&isLayeredTerrainDraft()?150:(terrainActiveField==8?150:wall?120:112);if(y>=toggleY&&y<toggleY+24){toggleTerrainField(terrainActiveField);return;}
		if(terrainActiveField==12&&y>=150&&y<174){if(x<88)terrainDiagonalOrientation=0;else terrainDiagonalOrientation=1;}
	}
	private void adjustActiveTerrain(int amount){switch(terrainActiveField){case 6:setTerrainElevation(terrainElevation+amount);break;case 7:setTerrainFloorColor(terrainFloorColor+amount);break;
		case 8:setTerrainFloorTexture(terrainFloorTexture+amount);break;case 9:setTerrainRoof(terrainRoof+amount);break;case 10:setTerrainNorthWall(steppedWallValue(terrainNorthWall,amount));break;
		case 11:setTerrainEastWall(steppedWallValue(terrainEastWall,amount));break;case 12:setTerrainDiagonalWall(steppedWallValue(terrainDiagonalWall,amount));break;case 18:setTerrainSmartWall(steppedWallValue(terrainSmartWall,amount));break;default:break;}}
	private void handleCompactSceneryMouse(int x,int y){
		if(y>=68&&y<92){if(x>=8&&x<38)setSceneryId(steppedProjectId("scenery",sceneryId,-1));else if(x>=42&&x<130)focusNumber(3);else if(x>=134&&x<164)setSceneryId(steppedProjectId("scenery",sceneryId,1));return;}
		if(y>=108&&y<132)openSceneryBrowser();
	}
	private void handleCompactNpcMouse(int x,int y){
		if(y>=56&&y<80){if(x>=8&&x<38)setNpcId(steppedProjectId("npc",npcId,-1));else if(x>=42&&x<130)focusNumber(4);else if(x>=134&&x<164)setNpcId(steppedProjectId("npc",npcId,1));return;}
		if(y>=100&&y<124){if(x>=8&&x<38)setNpcRadius(npcRadius-1);else if(x>=42&&x<130)focusNumber(5);else if(x>=134&&x<164)setNpcRadius(npcRadius+1);return;}
		if(y>=132&&y<156){if(x>=8&&x<38)setNpcRespawnSeconds(npcRespawnSeconds-1);else if(x>=42&&x<130)focusNumber(20);else if(x>=134&&x<164)setNpcRespawnSeconds(npcRespawnSeconds+1);return;}
		if(y>=164&&y<188)openNpcBrowser();
	}
	private void handleCompactGroundItemMouse(int x,int y){
		if(y>=50&&y<74){if(x>=8&&x<38)setGroundItemId(steppedProjectId("item",groundItemId,-1));else if(x>=42&&x<130)focusNumber(14);else if(x>=134&&x<164)setGroundItemId(steppedProjectId("item",groundItemId,1));return;}
		if(y>=80&&y<104){openGroundItemBrowser();return;}
		if(y>=108&&y<132){if(x>=68&&x<92)setGroundItemAmount(groundItemAmount-1);else if(x>=96&&x<144)focusNumber(15);else if(x>=148&&x<172)setGroundItemAmount(groundItemAmount+1);return;}
		if(y>=136&&y<160){if(x>=68&&x<92)setGroundItemRespawnSeconds(groundItemRespawnSeconds-1);else if(x>=96&&x<144)focusNumber(16);else if(x>=148&&x<172)setGroundItemRespawnSeconds(groundItemRespawnSeconds+1);return;}
	}
	private void handleCompactRegionMouse(int x,int y){
		if(regionTool!=RegionTool.PASTE){if(y>=78&&y<102){if(x<88)advanceRegionSelectionState();else removeLastRegionMarker();return;}if(y>=110&&y<134){if(x<88){if(regionTool==RegionTool.CUT)requestRegionCut();else requestRegionCopy();}else requestRegionExport();return;}}
		else{if(y>=82&&y<106){requestRegionPasteApply();return;}if(y>=114&&y<138){if(x<88)requestRegionPasteUndo();else requestRegionImport();return;}}
	}
	private boolean handleDefinitionBrowserMouse(int x,int y,int click){
		if(click==0)return true;if(click!=1)return true;
		if(y<28&&x>=360){closeDefinitionBrowser();return true;}
		if(y>=50&&y<74&&x>=296&&x<380){definitionBrowser.clearQuery();return true;}
		for(int row=0;row<WorldEditorDefinitionBrowser.VISIBLE_ROWS;row++)for(int column=0;column<WorldEditorDefinitionBrowser.COLUMNS;column++){
			int cardX=10+column*(BROWSER_CARD_WIDTH+6),cardY=BROWSER_GRID_Y+row*BROWSER_CARD_STEP_Y;
			if(x>=cardX&&x<cardX+BROWSER_CARD_WIDTH&&y>=cardY&&y<cardY+BROWSER_CARD_HEIGHT){
				selectDefinitionBrowserEntry(definitionBrowser.resultAtVisibleSlot(row*WorldEditorDefinitionBrowser.COLUMNS+column));return true;}
		}
		if(y>=296&&y<320){if(x>=10&&x<80)definitionBrowser.page(-1);else if(x>=310&&x<380)definitionBrowser.page(1);}
		return true;
	}
	private boolean handleExpandedMouse(int mx,int my,int down,int click){
		if(!isVisible())return false;int rx=mx-getX(),ry=my-getY();
		if(down==1&&ry>=0&&ry<24){if(dragX<0){dragX=rx;dragY=ry;}else setLocation(Math.max(0,mx-dragX),Math.max(0,my-dragY));}else{dragX=dragY=-1;}
		if(click==1){
			if(rx>=430&&ry<24){requestEditorClose();return true;}
			if(rx>=343&&rx<425&&ry<24){toolbar.setExpandedFallback(false);updatePresentationBounds();return true;}
			if(ry>=30&&ry<50){int tab=Math.min(TABS.length-1,Math.max(0,rx/65));selectMode(Mode.values()[tab]);return true;}
			if(mode==Mode.NAVIGATE){
				if(ry>=150&&ry<172){clickTeleportPreferred=!clickTeleportPreferred;mc.setWorldEditorNavigateClickTeleport(clickTeleportPreferred);return true;}
				if(ry>=197&&ry<221&&rx>=38&&rx<108){focusNumber(1);return true;}
				if(ry>=197&&ry<221&&rx>=128&&rx<198){focusNumber(2);return true;}
				if(isLayeredReview()&&ry>=197&&ry<221&&rx>=220&&rx<278){focusNumber(13);return true;}
				if(ry>=197&&ry<221&&rx>=295&&rx<375){coordinateFocus=0;teleportToFields();return true;}
			}
			if(mode==Mode.INSPECT&&ry>=276&&ry<300&&rx>=10&&rx<175&&!inspectionKind.isEmpty()){copyInspected();return true;}
			if(mode==Mode.TERRAIN){
				if(ry>=56&&ry<78){if(rx>=10&&rx<75)terrainStructureTab=false;else if(rx>=78&&rx<148)terrainStructureTab=true;else if(rx>=152&&rx<212)selectTerrainTool(TerrainTool.FREEHAND);else if(rx>=215&&rx<259)selectTerrainTool(TerrainTool.LINE);else if(rx>=262&&rx<317)selectTerrainTool(TerrainTool.RECTANGLE);else if(rx>=321&&rx<390)setTerrainBuildMode(!terrainBuildMode);coordinateFocus=0;return true;}
				if(!terrainStructureTab){
					if(ry>=82&&ry<106){if(rx>=10&&rx<30)paintElevation=!paintElevation;else if(rx>=150&&rx<178)setTerrainElevation(terrainElevation-1);else if(rx>=185&&rx<265)focusNumber(6);else if(rx>=272&&rx<300)setTerrainElevation(terrainElevation+1);else if(rx>=307&&isLayeredTerrainDraft())terrainElevationOperation=(terrainElevationOperation+1)%3;return true;}
					if(ry>=122&&ry<146){if(rx>=10&&rx<30)paintFloorColor=!paintFloorColor;else if(rx>=150&&rx<178)setTerrainFloorColor(terrainFloorColor-1);else if(rx>=185&&rx<265)focusNumber(7);else if(rx>=272&&rx<300)setTerrainFloorColor(terrainFloorColor+1);return true;}
					if(ry>=162&&ry<186){if(rx>=10&&rx<30)paintFloorTexture=!paintFloorTexture;else if(rx>=150&&rx<178)setTerrainFloorTexture(terrainFloorTexture-1);else if(rx>=185&&rx<265)focusNumber(8);else if(rx>=272&&rx<300)setTerrainFloorTexture(terrainFloorTexture+1);else if(rx>=307&&rx<435)openFloorBrowser();return true;}
					if(ry>=194&&ry<218){if(terrainTool==TerrainTool.RECTANGLE){if(rx>=65&&rx<137)rectangleOptions.setFill(false);else if(rx>=141&&rx<196)rectangleOptions.setFill(true);else if(rx>=204&&rx<285)rectangleOptions.toggleSmartWalls();else if(rx>=290&&rx<375)requestWorldEditSave();clearTerrainLine();}else if(rx>=65&&rx<110)terrainBrushSize=1;else if(rx>=114&&rx<159)terrainBrushSize=3;else if(rx>=163&&rx<208)terrainBrushSize=5;else if(rx>=212&&rx<257)terrainBrushSize=7;else if(rx>=270&&rx<375)requestWorldEditSave();return true;}
				}else{
					if(ry>=82&&ry<106){if(rx>=10&&rx<30)paintRoof=!paintRoof;else if(rx>=118&&rx<142)setTerrainRoof(terrainRoof-1);else if(rx>=148&&rx<202)focusNumber(9);else if(rx>=208&&rx<232)setTerrainRoof(terrainRoof+1);return true;}
					if(terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()){if(ry>=118&&ry<142){rectangleOptions.setSmartWalls(false);clearTerrainLine();return true;}if(ry>=145&&ry<169){if(rx<105)rectangleOptions.toggleNorthWall();else if(rx<205)rectangleOptions.toggleEastWall();return true;}if(ry>=170&&ry<194){if(rx>=118&&rx<142)setTerrainSmartWall(steppedWallValue(terrainSmartWall,-1));else if(rx>=148&&rx<202)focusNumber(18);else if(rx>=208&&rx<232)setTerrainSmartWall(steppedWallValue(terrainSmartWall,1));else if(rx>=330&&rx<435)openWallBrowser(18);return true;}if(ry>=194&&ry<218){if(rx>=65&&rx<137)rectangleOptions.setFill(false);else if(rx>=141&&rx<196)rectangleOptions.setFill(true);else if(rx>=270&&rx<375)requestWorldEditSave();clearTerrainLine();return true;}return true;}
					if(ry>=118&&ry<142){if(rx>=10&&rx<30)rectangleOptions.toggleNorthWall();else if(rx>=118&&rx<142)setTerrainNorthWall(steppedWallValue(terrainNorthWall,-1));else if(rx>=148&&rx<202)focusNumber(10);else if(rx>=208&&rx<232)setTerrainNorthWall(steppedWallValue(terrainNorthWall,1));else if(rx>=330&&rx<435)openWallBrowser(10);return true;}
					if(ry>=154&&ry<178){if(rx>=10&&rx<30)rectangleOptions.toggleEastWall();else if(rx>=118&&rx<142)setTerrainEastWall(steppedWallValue(terrainEastWall,-1));else if(rx>=148&&rx<202)focusNumber(11);else if(rx>=208&&rx<232)setTerrainEastWall(steppedWallValue(terrainEastWall,1));else if(rx>=330&&rx<435)openWallBrowser(11);return true;}
					if(ry>=190&&ry<214){if(rx>=10&&rx<30)rectangleOptions.toggleDiagonalWall();else if(rx>=118&&rx<142)setTerrainDiagonalWall(steppedWallValue(terrainDiagonalWall,-1));else if(rx>=148&&rx<202)focusNumber(12);else if(rx>=208&&rx<232)setTerrainDiagonalWall(steppedWallValue(terrainDiagonalWall,1));else if(rx>=330&&rx<435)openWallBrowser(12);return true;}
					if(ry>=220&&ry<244){if(rx>=118&&rx<178)terrainDiagonalOrientation=0;else if(rx>=185&&rx<245)terrainDiagonalOrientation=1;else if(terrainTool==TerrainTool.RECTANGLE&&rx>=270){rectangleOptions.setSmartWalls(true);clearTerrainLine();}return true;}
					if(ry>=248&&ry<272){if(rx>=65&&rx<110)terrainBrushSize=1;else if(rx>=114&&rx<159)terrainBrushSize=3;else if(rx>=163&&rx<208)terrainBrushSize=5;else if(rx>=212&&rx<257)terrainBrushSize=7;else if(rx>=270&&rx<375)requestWorldEditSave();return true;}
				}
			}
			if(mode==Mode.SCENERY){
				if(ry>=86&&ry<110&&rx>=10&&rx<38){setSceneryId(steppedProjectId("scenery",sceneryId,-1));return true;}
				if(ry>=86&&ry<110&&rx>=45&&rx<125){focusNumber(3);return true;}
				if(ry>=86&&ry<110&&rx>=132&&rx<160){setSceneryId(steppedProjectId("scenery",sceneryId,1));return true;}
				if(ry>=112&&ry<136&&rx>=175&&rx<309){openSceneryBrowser();return true;}
				if(ry>=145&&ry<169){clearSceneryMove();if(rx>=10&&rx<98)sceneryTool=SceneryTool.PLACE;else if(rx>=104&&rx<192)sceneryTool=SceneryTool.MOVE;else if(rx>=198&&rx<286)sceneryTool=SceneryTool.ROTATE;else if(rx>=292&&rx<380)sceneryTool=SceneryTool.REMOVE;return true;}
				if(ry>=276&&ry<300&&rx>=10&&rx<175){requestWorldEditSave();return true;}
			}
			if(mode==Mode.NPC){
				if(ry>=86&&ry<110&&rx>=10&&rx<38){setNpcId(steppedProjectId("npc",npcId,-1));return true;}
				if(ry>=86&&ry<110&&rx>=45&&rx<125){focusNumber(4);return true;}
				if(ry>=86&&ry<110&&rx>=132&&rx<160){setNpcId(steppedProjectId("npc",npcId,1));return true;}
				if(ry>=112&&ry<136&&rx>=175&&rx<309){openNpcBrowser();return true;}
				if(ry>=145&&ry<169&&rx>=10&&rx<38){setNpcRadius(npcRadius-1);return true;}
				if(ry>=145&&ry<169&&rx>=45&&rx<125){focusNumber(5);return true;}
				if(ry>=145&&ry<169&&rx>=132&&rx<160){setNpcRadius(npcRadius+1);return true;}
				if(ry>=185&&ry<209&&rx>=10&&rx<38){setNpcRespawnSeconds(npcRespawnSeconds-1);return true;}
				if(ry>=185&&ry<209&&rx>=45&&rx<125){focusNumber(20);return true;}
				if(ry>=185&&ry<209&&rx>=132&&rx<160){setNpcRespawnSeconds(npcRespawnSeconds+1);return true;}
				if(ry>=220&&ry<244){if(rx>=10&&rx<105)npcTool=NpcTool.PLACE;else if(rx>=112&&rx<207)npcTool=NpcTool.REMOVE;return true;}
				if(ry>=276&&ry<300&&rx>=10&&rx<175){requestWorldEditSave();return true;}
			}
			if(mode==Mode.ITEMS){
				if(ry>=86&&ry<110&&rx>=10&&rx<38){setGroundItemId(steppedProjectId("item",groundItemId,-1));return true;}
				if(ry>=86&&ry<110&&rx>=45&&rx<125){focusNumber(14);return true;}
				if(ry>=86&&ry<110&&rx>=132&&rx<160){setGroundItemId(steppedProjectId("item",groundItemId,1));return true;}
				if(ry>=112&&ry<136&&rx>=175&&rx<309){openGroundItemBrowser();return true;}
				if(ry>=137&&ry<161&&rx>=118&&rx<146){setGroundItemAmount(groundItemAmount-1);return true;}
				if(ry>=137&&ry<161&&rx>=153&&rx<233){focusNumber(15);return true;}
				if(ry>=137&&ry<161&&rx>=240&&rx<268){setGroundItemAmount(groundItemAmount+1);return true;}
				if(ry>=188&&ry<212&&rx>=118&&rx<146){setGroundItemRespawnSeconds(groundItemRespawnSeconds-1);return true;}
				if(ry>=188&&ry<212&&rx>=153&&rx<233){focusNumber(16);return true;}
				if(ry>=188&&ry<212&&rx>=240&&rx<268){setGroundItemRespawnSeconds(groundItemRespawnSeconds+1);return true;}
				if(ry>=235&&ry<259){if(rx>=10&&rx<105)groundItemTool=GroundItemTool.PLACE;else if(rx>=112&&rx<207)groundItemTool=GroundItemTool.REMOVE;return true;}
				if(ry>=276&&ry<300&&rx>=10&&rx<175){requestWorldEditSave();return true;}
			}
			if(mode==Mode.REGION){
				if(ry>=56&&ry<80){if(rx>=10&&rx<110)selectRegionTool(RegionTool.COPY);else if(rx>=120&&rx<220)selectRegionTool(RegionTool.CUT);else if(rx>=230&&rx<330)selectRegionTool(RegionTool.PASTE);return true;}
				if(regionTool!=RegionTool.PASTE&&ry>=122&&ry<146){if(rx>=10&&rx<110)advanceRegionSelectionState();else if(rx>=120&&rx<220)removeLastRegionMarker();else if(rx>=230&&rx<330){if(regionTool==RegionTool.CUT)requestRegionCut();else requestRegionCopy();}else if(rx>=340&&rx<440)requestRegionExport();return true;}
				if(regionTool==RegionTool.PASTE){if(ry>=122&&ry<146&&rx>=10&&rx<175){requestRegionPasteApply();return true;}if(ry>=154&&ry<178){if(rx>=185&&rx<285)requestRegionPasteUndo();else if(rx>=295&&rx<435)requestRegionImport();return true;}}
			}
			coordinateFocus=0;
		}
		return rx>=0&&ry>=0&&rx<=EXPANDED_WIDTH&&ry<=330;
	}

	@Override public void render(){
		if(!isVisible()||Config.isAndroid())return;
		pollDeferredSave();
		pollRegionCopy();
		pollRegionPaste();
		pollRegionBundleDialog();
		pollRegionBundle();
		if(toolbar.isExpandedFallback())renderExpanded();else renderCompact();
		if(definitionBrowser.isOpen())renderDefinitionBrowser(getX()+definitionBrowserOffsetX(),getY());
	}
	private void renderCompact(){
		int x=getX(),y=getY();
		int dockWidth=toolbar.isCollapsed()?40:DOCK_WIDTH;graphics().drawBoxAlpha(x,y,dockWidth,toolbar.isCollapsed()?38:DOCK_HEIGHT,0x24190c,235);graphics().drawBoxBorder(x,dockWidth,y,toolbar.isCollapsed()?38:DOCK_HEIGHT,0);
		drawIconButton(toolbar.isCollapsed()?WorldEditorIconRegistry.Key.TOOLBAR_EXPAND:WorldEditorIconRegistry.Key.TOOLBAR_COLLAPSE,x+DOCK_LEFT,y+DOCK_TOP,toolbar.isCollapsed(),false,false,false);
		if(toolbar.isCollapsed()){renderCompactTooltip(x,y);return;}
		drawModeIcon(WorldEditorIconRegistry.Key.MODE_NAVIGATE,x+DOCK_LEFT,y+dockRowY(1),Mode.NAVIGATE);
		drawModeIcon(WorldEditorIconRegistry.Key.MODE_INSPECT,x+DOCK_LEFT,y+dockRowY(2),Mode.INSPECT);
		drawModeIcon(WorldEditorIconRegistry.Key.MODE_SCENERY,x+DOCK_LEFT,y+dockRowY(3),Mode.SCENERY);
		drawModeIcon(WorldEditorIconRegistry.Key.MODE_NPC,x+DOCK_LEFT,y+dockRowY(4),Mode.NPC);
		drawModeIcon(WorldEditorIconRegistry.Key.MODE_ITEMS,x+DOCK_LEFT,y+dockRowY(5),Mode.ITEMS);
		drawModeIcon(WorldEditorIconRegistry.Key.MODE_REGION,x+DOCK_LEFT,y+dockRowY(6),Mode.REGION);
			drawBrushIconButton(x+DOCK_LEFT,y+dockRowY(7));
		drawIconButton(WorldEditorIconRegistry.Key.PROFILE_BUILD,x+DOCK_LEFT,y+dockRowY(8),terrainBuildMode,false,false,false);
		drawHistoryIconButton(WorldEditorIconRegistry.Key.ACTION_UNDO,x+DOCK_LEFT,y+dockRowY(9),terrainHistoryCanUndo);
		drawHistoryIconButton(WorldEditorIconRegistry.Key.ACTION_REDO,x+DOCK_LEFT,y+dockRowY(10),terrainHistoryCanRedo);
		drawIconButton(WorldEditorIconRegistry.Key.ACTION_SAVE,x+DOCK_LEFT,y+dockRowY(11),false,false,false,unsavedChanges||saveRequested);
		drawIconButton(WorldEditorIconRegistry.Key.ACTION_CLOSE,x+DOCK_LEFT,y+dockRowY(12),false,false,closeArmed,false);
		renderDockContextActions(x,y);
		if(toolbar.isFlyoutOpen())renderCompactFlyout(x+DOCK_WIDTH+FLYOUT_GAP,y);
		renderCompactTooltip(x,y);
	}
	private static int dockRowY(int row){return DOCK_TOP+row*DOCK_STEP;}
	private void drawModeIcon(WorldEditorIconRegistry.Key key,int x,int y,Mode iconMode){boolean selected=mode==iconMode;drawIconButton(key,x,y,selected,selected&&toolbar.isFlyoutOpen(),false,false);}
	private void drawTerrainIcon(WorldEditorIconRegistry.Key key,int x,int y,int field,boolean enabled){drawIconButton(key,x,y,enabled,mode==Mode.TERRAIN&&terrainActiveField==field&&toolbar.isFlyoutOpen(),terrainFieldInvalid(field),false);}
	private void renderDockContextActions(int x,int y){
		if(mode==Mode.TERRAIN){
			drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_ELEVATION,x+DOCK_RIGHT,y+dockRowY(0),6,paintElevation);
			drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_FLOOR_COLOR,x+DOCK_RIGHT,y+dockRowY(1),7,paintFloorColor);
			drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_FLOOR_TEXTURE,x+DOCK_RIGHT,y+dockRowY(2),8,paintFloorTexture);
			drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_ROOF,x+DOCK_RIGHT,y+dockRowY(3),9,paintRoof);
			if(terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()){
				drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_WALL_NORTH,x+DOCK_RIGHT,y+dockRowY(4),18,rectangleOptions.isNorthWall());
				drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_WALL_EAST,x+DOCK_RIGHT,y+dockRowY(5),18,rectangleOptions.isEastWall());
				drawDisabledTerrainIcon(WorldEditorIconRegistry.Key.FIELD_WALL_DIAGONAL,x+DOCK_RIGHT,y+dockRowY(6));
			}else{
				drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_WALL_NORTH,x+DOCK_RIGHT,y+dockRowY(4),10,rectangleOptions.isNorthWall());
				drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_WALL_EAST,x+DOCK_RIGHT,y+dockRowY(5),11,rectangleOptions.isEastWall());
				drawTerrainIcon(WorldEditorIconRegistry.Key.FIELD_WALL_DIAGONAL,x+DOCK_RIGHT,y+dockRowY(6),12,rectangleOptions.isDiagonalWall());
			}
			drawTerrainToolIcon(WorldEditorIconRegistry.Key.TOOL_FREEHAND,x+DOCK_RIGHT,y+dockRowY(7),terrainTool==TerrainTool.FREEHAND);
			drawTerrainToolIcon(WorldEditorIconRegistry.Key.TOOL_LINE,x+DOCK_RIGHT,y+dockRowY(8),terrainTool==TerrainTool.LINE);
			drawTerrainToolIcon(WorldEditorIconRegistry.Key.TOOL_RECTANGLE,x+DOCK_RIGHT,y+dockRowY(9),terrainTool==TerrainTool.RECTANGLE);
		}else if(mode==Mode.SCENERY){
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_SCENERY,"+",x+DOCK_RIGHT,y+dockRowY(0),sceneryTool==SceneryTool.PLACE);
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_SCENERY,"M",x+DOCK_RIGHT,y+dockRowY(1),sceneryTool==SceneryTool.MOVE);
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_SCENERY,"R",x+DOCK_RIGHT,y+dockRowY(2),sceneryTool==SceneryTool.ROTATE);
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_SCENERY,"-",x+DOCK_RIGHT,y+dockRowY(3),sceneryTool==SceneryTool.REMOVE);
		}else if(mode==Mode.NPC){
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_NPC,"+",x+DOCK_RIGHT,y+dockRowY(0),npcTool==NpcTool.PLACE);
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_NPC,"-",x+DOCK_RIGHT,y+dockRowY(1),npcTool==NpcTool.REMOVE);
		}else if(mode==Mode.ITEMS){
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_ITEMS,"+",x+DOCK_RIGHT,y+dockRowY(0),groundItemTool==GroundItemTool.PLACE);
			drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_ITEMS,"-",x+DOCK_RIGHT,y+dockRowY(1),groundItemTool==GroundItemTool.REMOVE);
		}else if(mode==Mode.REGION){
			drawRegionToolIcon(WorldEditorIconRegistry.Key.MODE_REGION_COPY,x+DOCK_RIGHT,y+dockRowY(0),RegionTool.COPY);
			drawRegionToolIcon(WorldEditorIconRegistry.Key.MODE_REGION_CUT,x+DOCK_RIGHT,y+dockRowY(1),RegionTool.CUT);
			drawRegionToolIcon(WorldEditorIconRegistry.Key.MODE_REGION_PASTE,x+DOCK_RIGHT,y+dockRowY(2),RegionTool.PASTE);
		}
	}
	private void drawRegionToolIcon(WorldEditorIconRegistry.Key key,int x,int y,RegionTool tool){drawIconButton(key,x,y,regionTool==tool,regionTool==tool&&toolbar.isFlyoutOpen(),false,false);}
	private void drawContextActionIcon(WorldEditorIconRegistry.Key key,String action,int x,int y,boolean selected){
		drawIconButton(key,x,y,selected,false,false,false);graphics().drawBoxAlpha(x+16,y+15,10,10,0x111111,240);
		int width=graphics().stringWidth(1,action);graphics().drawString(action,x+21-width/2,y+24,selected?0xffff00:0xffffff,1);
	}
	private void drawTerrainToolIcon(WorldEditorIconRegistry.Key key,int x,int y,boolean selected){
		graphics().drawBoxAlpha(x,y,28,28,selected?0x6b3f82:0x333333,235);graphics().drawBoxBorder(x,28,y,28,selected?0xd7a2ff:0x080808);
		Sprite sprite=icons.get(key);if(sprite!=null)graphics().drawSprite(sprite,x+2,y+2);else{String label=key.fallbackLabel();int width=graphics().stringWidth(1,label);graphics().drawString(label,x+14-width/2,y+17,0xffffff,1);}
		if(selected)graphics().drawBoxAlpha(x+21,y+3,4,4,0xe0b5ff,255);
	}
	private void drawDisabledTerrainIcon(WorldEditorIconRegistry.Key key,int x,int y){
		drawIconButton(key,x,y,false,false,true,false);graphics().drawBoxAlpha(x+3,y+3,22,22,0x330000,150);
		graphics().drawString("X",x+9,y+22,0xff2020,3);
	}
	private void drawHistoryIconButton(WorldEditorIconRegistry.Key key,int x,int y,boolean available){
		drawIconButton(key,x,y,false,terrainHistoryPending,false,available);
		if(!available)graphics().drawBoxAlpha(x+2,y+2,24,24,0x111111,150);
	}
	private void drawIconButton(WorldEditorIconRegistry.Key key,int x,int y,boolean selected,boolean viewed,boolean warning,boolean badge){
		int background=warning?0x7a281f:viewed?0x526f24:selected?0x365b82:0x333333;
		graphics().drawBoxAlpha(x,y,28,28,background,235);graphics().drawBoxBorder(x,28,y,28,viewed?0xb6e36a:selected?0x66b3ff:warning?0xff981f:0x080808);
		Sprite sprite=icons.get(key);if(sprite!=null)graphics().drawSprite(sprite,x+2,y+2);else{
			String label=key.fallbackLabel();int width=graphics().stringWidth(1,label);graphics().drawString(label,x+14-width/2,y+17,0xffffff,1);
		}
		if(selected){graphics().drawBoxAlpha(x+21,y+3,4,4,viewed?0xc8ff75:0x66b3ff,255);}if(warning){graphics().drawString("!",x+21,y+12,0xffff00,1);}if(badge){graphics().drawString("*",x+20,y+13,0xff981f,2);}
	}
	private void drawBrushIconButton(int x,int y){
		drawIconButton(terrainBrushSize==1?WorldEditorIconRegistry.Key.TOOL_BRUSH_1X1:WorldEditorIconRegistry.Key.TOOL_BRUSH_3X3,x,y,mode==Mode.TERRAIN,mode==Mode.TERRAIN&&terrainActiveField==0&&toolbar.isFlyoutOpen(),false,false);
		if(terrainBrushSize>3){graphics().drawBoxAlpha(x+15,y+15,12,12,0x111111,245);graphics().drawString(String.valueOf(terrainBrushSize),x+18,y+25,0xffff00,1);}
	}
	private void renderCompactFlyout(int x,int y){
		graphics().drawBoxAlpha(x,y,FLYOUT_WIDTH,DOCK_HEIGHT,0x24190c,235);graphics().drawBoxBorder(x,FLYOUT_WIDTH,y,DOCK_HEIGHT,0);
		graphics().drawBoxAlpha(x,y,FLYOUT_WIDTH,28,0x4a3620,255);graphics().drawString(compactFlyoutTitle(),x+8,y+19,0xffff00,2);
		drawHeaderIcon(WorldEditorIconRegistry.Key.ACTION_PIN,x+100,y+2,toolbar.isPinned());button(x+138,y+2,40,"Full");
		if(mode==Mode.NAVIGATE)renderCompactNavigate(x,y);else if(mode==Mode.INSPECT)renderCompactInspect(x,y);else if(mode==Mode.TERRAIN)renderCompactTerrain(x,y);
		else if(mode==Mode.SCENERY)renderCompactScenery(x,y);
		else if(mode==Mode.NPC)renderCompactNpc(x,y);
		else if(mode==Mode.ITEMS)renderCompactGroundItems(x,y);
		else renderCompactRegion(x,y);
		renderCompactStatus(x,y);
	}
	private String compactFlyoutTitle(){return mode==Mode.TERRAIN?(terrainActiveField==0?"Brush":activeTerrainLabel()):mode==Mode.REGION?(regionTool==RegionTool.COPY?"Region Copy":regionTool==RegionTool.CUT?"Region Cut":"Region Paste"):TABS[mode.ordinal()];}
	private void drawHeaderIcon(WorldEditorIconRegistry.Key key,int x,int y,boolean active){
		graphics().drawBoxAlpha(x,y,36,24,active?0x365b82:0x333333,235);graphics().drawBoxBorder(x,36,y,24,active?0x66b3ff:0);Sprite sprite=icons.get(key);
		if(sprite!=null)graphics().drawSprite(sprite,x+6,y);else graphics().drawString(key.fallbackLabel(),x+5,y+16,0xffffff,1);
	}
	private void renderCompactNavigate(int x,int y){
		int px=mc.getEditorPlayerWorldX(),py=mc.getEditorPlayerWorldY(),level=mc.getEditorPlayerWorldLevel();graphics().drawString("Player "+px+","+py+",L"+level,x+8,y+47,0xffffff,1);
		graphics().drawString("Clicked "+point(lastClickedX,lastClickedY,lastClickedLevel),x+8,y+63,0xbdbdbd,1);
		checkbox(x+8,y+74,clickTeleportPreferred,"Click teleport");graphics().drawString(isLayeredReview()?"Teleport X / Y / Level":"Teleport X / Y",x+8,y+111,0xffff00,1);
		if(isLayeredReview()){textField(x+8,y+118,50,teleportX,coordinateFocus==1);textField(x+62,y+118,54,teleportY,coordinateFocus==2);textField(x+120,y+118,52,teleportLevel,coordinateFocus==13);}
		else{textField(x+8,y+118,78,teleportX,coordinateFocus==1);textField(x+94,y+118,78,teleportY,coordinateFocus==2);}
		button(x+8,y+148,164,isLayeredTerrainDraft()?"Go/Create":"Teleport");
	}
	private void renderCompactInspect(int x,int y){
		graphics().drawString(compactLine(inspectionStatus,28),x+8,y+47,0xffff00,1);int line=y+64;for(String text:inspectionDetails){if(line>y+145)break;graphics().drawString(compactLine(text,28),x+8,line,0xffffff,1);line+=14;}
		button(x+8,y+158,164,inspectionKind.isEmpty()?"Copy (empty)":"Copy inspected");
	}
	private void renderCompactTerrain(int x,int y){
		if(terrainActiveField==0){if(terrainTool==TerrainTool.RECTANGLE){graphics().drawString("Rectangle settings",x+8,y+49,0xffff00,2);toolButton(x+8,y+58,80,"Outline",!rectangleOptions.isFill());toolButton(x+92,y+58,80,"Fill",rectangleOptions.isFill());toolButton(x+8,y+88,164,"Smart Walls: "+(rectangleOptions.isSmartWalls()?"ON":"OFF"),rectangleOptions.isSmartWalls());button(x+8,y+118,30,"-");textField(x+42,y+118,88,terrainSmartWallText,coordinateFocus==18);button(x+134,y+118,30,"+");toolButton(x+8,y+148,80,"North",rectangleOptions.isNorthWall());toolButton(x+92,y+148,80,"East",rectangleOptions.isEastWall());graphics().drawString("Two corners; one atomic commit.",x+8,y+184,0xff981f,1);graphics().drawString(rectangleOptions.isSmartWalls()?"Diagonal disabled; choose N, E, or both.":"Raw wall fields apply to the footprint.",x+8,y+200,0xff981f,1);return;}graphics().drawString("Footprint: "+terrainBrushSize+"x"+terrainBrushSize,x+8,y+49,0xffff00,2);toolButton(x+8,y+58,164,"1x1 single tile",terrainBrushSize==1);toolButton(x+8,y+88,164,"3x3 centered",terrainBrushSize==3);toolButton(x+8,y+118,164,"5x5 centered",terrainBrushSize==5);toolButton(x+8,y+148,164,"7x7 centered",terrainBrushSize==7);
			graphics().drawString("Right-click cycles brush sizes.",x+8,y+184,0xff981f,1);graphics().drawString(terrainTool==TerrainTool.LINE?"Line width uses the centered brush.":"Ctrl + left-drag paints continuously.",x+8,y+200,0xff981f,1);return;}
		graphics().drawString(activeTerrainLabel(),x+8,y+49,0xffff00,2);button(x+8,y+58,30,"-");textField(x+42,y+58,88,activeTerrainText(),coordinateFocus==terrainActiveField);button(x+134,y+58,30,"+");
		boolean wall=terrainActiveField==10||terrainActiveField==11||terrainActiveField==12||terrainActiveField==18;
		int toggleY=112;if(terrainActiveField==6&&isLayeredTerrainDraft()){toolButton(x+8,y+90,50,"Set",terrainElevationOperation==0);toolButton(x+60,y+90,52,"Raise",terrainElevationOperation==1);toolButton(x+114,y+90,54,"Lower",terrainElevationOperation==2);button(x+8,y+120,30,"-");textField(x+42,y+120,88,terrainElevationStepText,coordinateFocus==17);button(x+134,y+120,30,"+");toggleY=150;}else if(terrainActiveField==8){button(x+8,y+90,164,"Browse floor textures...");graphics().drawString(compactLine(floorTextureVisualName(),28),x+8,y+126,terrainFieldInvalid(terrainActiveField)?0xff981f:0xffffff,1);
			graphics().drawString(floorTextureTraversal(),x+8,y+140,floorTextureTraversalColor(),1);toggleY=150;
		}else if(wall){button(x+8,y+90,164,"Browse walls...");toggleY=120;
		}else{String name=activeTerrainCompactName();if(!name.isEmpty())graphics().drawString(compactLine(name,28),x+8,y+101,terrainFieldInvalid(terrainActiveField)?0xff981f:0xbdbdbd,1);}
		toolButton(x+8,y+toggleY,164,activeTerrainEnabled()?"Paint: ON":"Paint: OFF",activeTerrainEnabled());
		if(terrainActiveField==12){toolButton(x+8,y+150,76,"\\",terrainDiagonalOrientation==0);toolButton(x+92,y+150,76,"/",terrainDiagonalOrientation==1);}
	}
	private void renderCompactScenery(int x,int y){
		graphics().drawString(compactLine(sceneryName(),28),x+8,y+49,0xffff00,1);button(x+8,y+68,30,"-");textField(x+42,y+68,88,sceneryIdText,coordinateFocus==3);button(x+134,y+68,30,"+");
		button(x+8,y+108,164,"Browse scenery...");
	}
	private void renderCompactNpc(int x,int y){
		graphics().drawString(compactLine(npcName(),28),x+8,y+47,0xffff00,1);button(x+8,y+56,30,"-");textField(x+42,y+56,88,npcIdText,coordinateFocus==4);button(x+134,y+56,30,"+");
		graphics().drawString("Roam radius",x+8,y+95,0xffff00,1);button(x+8,y+100,30,"-");textField(x+42,y+100,88,npcRadiusText,coordinateFocus==5);button(x+134,y+100,30,"+");
		graphics().drawString("Respawn: "+npcRespawnLabel(),x+8,y+129,0xffff00,1);button(x+8,y+132,30,"-");textField(x+42,y+132,88,npcRespawnText,coordinateFocus==20);button(x+134,y+132,30,"+");
		button(x+8,y+164,164,"Browse NPCs...");
	}
	private void renderCompactGroundItems(int x,int y){
		graphics().drawString(compactLine(groundItemName(),28),x+8,y+43,0xffff00,1);button(x+8,y+50,30,"-");textField(x+42,y+50,88,groundItemIdText,coordinateFocus==14);button(x+134,y+50,30,"+");
		button(x+8,y+80,164,"Browse items...");
		graphics().drawString("Amount",x+8,y+125,0xffff00,1);button(x+68,y+108,24,"-");textField(x+96,y+108,48,groundItemAmountText,coordinateFocus==15);button(x+148,y+108,24,"+");
		graphics().drawString("Respawn",x+8,y+153,0xffff00,1);button(x+68,y+136,24,"-");textField(x+96,y+136,48,groundItemRespawnText,coordinateFocus==16);button(x+148,y+136,24,"+");
	}
	private void renderCompactRegion(int x,int y){
		if(regionTool!=RegionTool.PASTE){boolean cutting=regionTool==RegionTool.CUT;graphics().drawString(regionMarkers.isEmpty()?"Click terrain to place marker 1.":regionClosed?(cutting?"Selection closed; select Cut.":"Selection closed; select Copy."):"Keep tracing, then select Stop.",x+8,y+49,0xffffff,1);graphics().drawString("Markers: "+regionMarkers.size()+(regionClosed?" | "+regionPreviewTiles.length+" tiles":" | open"),x+8,y+65,regionClosed?0x80c080:0xffff00,1);toolButton(x+8,y+78,78,regionSelectionActionLabel(),!regionClosed);button(x+94,y+78,78,"Undo");button(x+8,y+110,78,cutting?regionCutActionLabel():regionCopyBridge.isPending()?"Copying...":"Copy");button(x+94,y+110,78,isRegionSharingPending()?"Working...":"Export");graphics().drawString(compactLine(lastRegionSnapshotId.isEmpty()?(cutting?"Cut secures a snapshot first.":"Copy stores the closed selection."):"Clipboard: "+lastRegionSnapshotName,28),x+8,y+151,lastRegionSnapshotId.isEmpty()?0xbdbdbd:0x80c080,1);graphics().drawString(cutting?(regionCutPlanHash.isEmpty()?"Cut previews before changing the world.":"Snapshot safe; Confirm Cut to void."):"Reset clears markers, not clipboard.",x+8,y+169,0xff981f,1);}
		else{WorldBuilderRegionPasteClientBridge.Snapshot snapshot=selectedRegionSnapshot();boolean sharing=isRegionSharingPending();graphics().drawString(compactLine(snapshot==null?"Clipboard is empty":snapshot.name,28),x+8,y+49,snapshot==null?0xff981f:0xffff00,1);graphics().drawString(regionPasteX<0?"Click terrain to choose a destination.":"Anchor: "+regionPasteX+","+regionPasteY+",L"+regionPasteLevel,x+8,y+65,0xffffff,1);button(x+8,y+82,164,regionPasteActionLabel());button(x+8,y+114,78,regionPasteBridge.isPending()?"Working...":"Undo");button(x+94,y+114,78,sharing?"Working...":"Import");graphics().drawString(regionPastePlanHash.isEmpty()?"Import loads a shared .wbr.":regionPastePreviewTiles.length+" tiles | "+regionPasteCollisionTiles.length+" collisions",x+8,y+153,regionPasteBlocked?0xff4040:regionPasteOverwrite?0xff981f:0x80c080,1);graphics().drawString(regionPasteOverwrite?"Paste > Overwrite? > Confirm":"Paste applies the exact preview live.",x+8,y+171,regionPasteOverwrite?0xff981f:0xbdbdbd,1);}
	}
	private void renderCompactStatus(int x,int y){
		int px=mc.getEditorPlayerWorldX(),py=mc.getEditorPlayerWorldY(),level=mc.getEditorPlayerWorldLevel(),queued=terrainDragPending.size()+(terrainStrokeTiles==null?0:terrainStrokeTiles.length)
			+(terrainLineCommitTiles==null?0:terrainLineCommitTiles.length-terrainLineReceived)+entityEditTracker.pendingCount();
		graphics().drawLineHoriz(x+8,y+194,FLYOUT_WIDTH-16,0x70512d);graphics().drawString("@yel@"+px+","+py+",L"+level+" @whi@| "+mode,x+8,y+211,0xffffff,1);
		graphics().drawString(compactLine("Awaiting "+queued+" | ack "+lastAckMillis+" | rebuild "+lastRebuildMillis,28),x+8,y+228,0xbdbdbd,1);
		graphics().drawString(unsavedChanges?"Unsaved"+(saveRequested?" (save requested)":saveAfterPendingEdits?" (save queued)":""):"Saved/clean",x+8,y+245,unsavedChanges?0xff981f:0x80c080,1);
		String status=isLayeredReview()?(isLayeredTerrainDraft()?"Draft ":"Review ")+WorldBuilderClientProfile.current().layeredPackageVersion()+" "+WorldBuilderClientProfile.current().layeredManifestShort():(WorldBuilderClientProfile.isEnabled()?"Source "+WorldBuilderClientProfile.current().sourceRevisionShort():inspectionStatus);
		graphics().drawString(compactLine(status,28),x+8,y+264,0xbdbdbd,1);
	}
	private void renderCompactTooltip(int x,int y){
		toolbarTooltip=toolbarTooltipAt(compactMouseX-x,compactMouseY-y);if(toolbarTooltip.isEmpty())return;int width=Math.min(310,Math.max(150,graphics().stringWidth(1,toolbarTooltip)+12));
		graphics().drawBoxAlpha(x+DOCK_WIDTH+4,compactMouseY+6,width,24,0x111111,245);graphics().drawBoxBorder(x+DOCK_WIDTH+4,width,compactMouseY+6,24,0);graphics().drawString(toolbarTooltip,x+DOCK_WIDTH+10,compactMouseY+22,0xffffff,1);
	}
	private String toolbarTooltipAt(int x,int y){
		if(x<0||x>=DOCK_WIDTH||y<0)return "";if(dockHit(x,y,0,0))return "Collapse/expand dock";Mode selected=dockModeAt(x,y);if(selected!=null)return selected==Mode.REGION?"Region Copier | select Copy, Cut, or Paste on the right":selected.name()+" mode | Left: select or toggle flyout";
		if(mode==Mode.REGION&&dockHit(x,y,1,0))return "Region Copy | select and capture reusable content";
		if(mode==Mode.REGION&&dockHit(x,y,1,1))return "Region Cut | snapshot first, then replace selection with void";
		if(mode==Mode.REGION&&dockHit(x,y,1,2))return "Region Paste | preview, apply, import, or undo";
		int action=contextActionAtDock(x,y);if(action>=0)return contextActionTooltip(action);
		if(mode==Mode.TERRAIN&&terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()&&dockHit(x,y,1,4))return "North Smart Wall: "+(rectangleOptions.isNorthWall()?"ON":"OFF")+" | Left: wall type | Right: toggle";
		if(mode==Mode.TERRAIN&&terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()&&dockHit(x,y,1,5))return "East Smart Wall: "+(rectangleOptions.isEastWall()?"ON":"OFF")+" | Left: wall type | Right: toggle";
		if(mode==Mode.TERRAIN&&terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()&&dockHit(x,y,1,6))return "Diagonal Wall: disabled by Smart Walls (red X)";
		int field=terrainFieldAtDock(x,y);if(field>=0)return activeTerrainLabel(field)+": "+terrainText(field)+" | "+(terrainEnabled(field)?"paint ON":"paint OFF")+" | Left: edit | Right: toggle";
		TerrainTool terrainSelection=terrainToolAtDock(x,y);if(terrainSelection!=null)return terrainSelection==TerrainTool.FREEHAND?"Freehand | click or Ctrl-drag":terrainSelection==TerrainTool.LINE?"Line | click anchor, preview, click destination":"Rectangle | click two opposite corners";
		if(dockHit(x,y,0,7))return "Brush "+terrainBrushSize+"x"+terrainBrushSize+" | Left: edit | Right: toggle size";if(dockHit(x,y,0,8))return "Build view: "+(terrainBuildMode?"ON":"OFF")+" | faceted terrain grid";
		if(dockHit(x,y,0,9))return terrainHistoryCanUndo?"Undo last Builder operation | Ctrl+Z":"Undo | no Builder operation available";
		if(dockHit(x,y,0,10))return terrainHistoryCanRedo?"Redo next Builder operation | Ctrl+Y":"Redo | no Builder operation available";
		if(dockHit(x,y,0,11))return "Save | "+(unsavedChanges?"unsaved changes":"clean")+(saveRequested?" | requested":"");if(dockHit(x,y,0,12))return closeArmed?"Close without saving: confirm":"Close editor";return "";
	}
	private String contextActionTooltip(int action){
		if(mode==Mode.SCENERY)return "Scenery: "+(action==0?"Add":action==1?"Move":action==2?"Rotate":"Remove");
		if(mode==Mode.NPC)return "NPCs: "+(action==0?"Add":"Remove");
		if(mode==Mode.ITEMS)return "Items: "+(action==0?"Add":"Remove");
		if(regionTool!=RegionTool.PASTE)return "Region "+(regionTool==RegionTool.CUT?"Cut: ":"Copy: ")+(action==0?regionSelectionActionLabel()+" selection":action==1?"Undo last marker":action==2?(regionTool==RegionTool.CUT?regionCutActionLabel()+" closed selection":"Copy closed selection"):"Export clipboard as .wbr");return "Region Paste: "+(action==0?regionPasteActionLabel()+" exact preview":action==1?"Undo exact last Paste":"Import portable .wbr");
	}
	private boolean activeTerrainEnabled(){return terrainEnabled(terrainActiveField);}
	private boolean terrainEnabled(int field){switch(field){case 6:return paintElevation;case 7:return paintFloorColor;case 8:return paintFloorTexture;case 9:return paintRoof;case 10:return rectangleOptions.isNorthWall();case 11:return rectangleOptions.isEastWall();case 12:return rectangleOptions.isDiagonalPlacementEnabled();case 18:return rectangleOptions.hasSmartWallSelection();default:return false;}}
	private String activeTerrainLabel(){return activeTerrainLabel(terrainActiveField);}
	private String activeTerrainLabel(int field){switch(field){case 6:return "Elevation";case 7:return "Floor Color";case 8:return "Floor Texture";case 9:return "Roof";case 10:return "North Wall";case 11:return "East Wall";case 12:return "Diagonal Wall";case 18:return "Smart Wall";default:return "Brush";}}
	private String activeTerrainText(){return terrainText(terrainActiveField);}
	private String terrainText(int field){switch(field){case 6:return terrainElevationText;case 7:return terrainFloorColorText;case 8:return terrainFloorTextureText;case 9:return terrainRoofText;case 10:return terrainNorthWallText;case 11:return terrainEastWallText;case 12:return terrainDiagonalWallText;case 18:return terrainSmartWallText;default:return terrainBrushSize+"x"+terrainBrushSize;}}
	private String activeTerrainCompactName(){switch(terrainActiveField){case 9:return roofDescription();case 10:return wallDescription(terrainNorthWall);case 11:return wallDescription(terrainEastWall);case 12:return wallDescription(terrainDiagonalWall);case 18:return wallDescription(terrainSmartWall);default:return "";}}
	private boolean terrainFieldInvalid(int field){try{if(field==8&&terrainFloorTexture!=0&&terrainFloorTexture!=250&&!WorldBuilderTerrainOverlay.isBlockingBaseColor(terrainFloorTexture))return EntityHandler.getTileDef(terrainFloorTexture-1)==null;if(field==9)return terrainRoof<0||terrainRoof>EntityHandler.elevationCount();
		if(field==10)return terrainNorthWall<0||terrainNorthWall>EntityHandler.doorCount();if(field==11)return terrainEastWall<0||terrainEastWall>EntityHandler.doorCount();if(field==12)return terrainDiagonalWall<0||terrainDiagonalWall>EntityHandler.doorCount();if(field==18)return terrainSmartWall<0||terrainSmartWall>EntityHandler.doorCount();return false;}catch(Exception e){return true;}}
	private void renderExpanded(){
		if(!isVisible()||Config.isAndroid())return;int x=getX(),y=getY();
		graphics().drawBoxAlpha(x,y,EXPANDED_WIDTH,330,0x24190c,235);graphics().drawBoxBorder(x,EXPANDED_WIDTH,y,330,0);graphics().drawBoxAlpha(x,y,EXPANDED_WIDTH,24,0x4a3620,255);
		String title=isLayeredReview()?(isLayeredTerrainDraft()?"World Builder Draft: ":"World Builder Review: ")+WorldBuilderClientProfile.current().projectName():(WorldBuilderClientProfile.isEnabled()?"World Builder: "+WorldBuilderClientProfile.current().projectName():"World Editor");
		graphics().drawString(compactLine(title,46),x+8,y+17,0xffff00,2);button(x+343,y,82,"Compact");graphics().drawString("X",x+437,y+17,0xffffff,2);
		for(int i=0;i<TABS.length;i++){boolean selected=mode.ordinal()==i;graphics().drawBoxAlpha(x+i*65,y+30,64,20,selected?0x6b8e23:0x333333,220);graphics().drawString(TABS[i],x+i*65+4,y+44,0xffffff,2);}
		if(mode==Mode.NAVIGATE)renderNavigate(x,y);else if(mode==Mode.INSPECT)renderInspect(x,y);else if(mode==Mode.TERRAIN)renderTerrain(x,y);else if(mode==Mode.SCENERY)renderScenery(x,y);else if(mode==Mode.NPC)renderNpc(x,y);else if(mode==Mode.ITEMS)renderGroundItems(x,y);else renderRegion(x,y);
		String revision=isLayeredReview()?" | package "+WorldBuilderClientProfile.current().layeredPackageVersion()+" "+WorldBuilderClientProfile.current().layeredManifestShort():(WorldBuilderClientProfile.isEnabled()?" | source "+WorldBuilderClientProfile.current().sourceRevisionShort():"");
		graphics().drawString("Mode: "+mode+" | session sequence "+nextSequence+revision,x+10,y+321,0xbdbdbd,1);
	}
	private void renderNavigate(int x,int y){
		int px=mc.getEditorPlayerWorldX(),py=mc.getEditorPlayerWorldY(),level=mc.getEditorPlayerWorldLevel();
		graphics().drawString("Navigation",x+10,y+70,0xffff00,2);
		graphics().drawString("Player: "+px+", "+py+", level "+level,x+10,y+91,0xffffff,2);
		graphics().drawString("Last clicked tile: "+point(lastClickedX,lastClickedY,lastClickedLevel),x+10,y+111,0xffffff,2);
		graphics().drawString(isLayeredReview()?"Package: "+WorldBuilderClientProfile.current().layeredPackageId()+" "+WorldBuilderClientProfile.current().layeredPackageVersion():"Brush: inactive at "+point(brushX,brushY,brushLevel),x+10,y+131,0xbdbdbd,2);
		checkbox(x+10,y+150,clickTeleportPreferred,"Click teleport (Navigate only)");
		graphics().drawString("Teleport to coordinates",x+10,y+188,0xffff00,2);
		graphics().drawString("X",x+20,y+214,0xffffff,2);textField(x+38,y+197,70,teleportX,coordinateFocus==1);
		graphics().drawString("Y",x+112,y+214,0xffffff,2);textField(x+128,y+197,70,teleportY,coordinateFocus==2);
		if(isLayeredReview()){graphics().drawString("L",x+204,y+214,0xffffff,2);textField(x+220,y+197,58,teleportLevel,coordinateFocus==13);}
		button(x+295,y+197,80,isLayeredTerrainDraft()?"Go/Create":"Teleport");
		graphics().drawString(isLayeredTerrainDraft()?"New-level terrain, structures, scenery, NPCs, and item spawns are editable; source/export stay locked.":isLayeredReview()?"Read-only package review; navigate and inspect are enabled.":"Navigate uses movement options; brush/edit actions are off.",x+10,y+244,0xff981f,1);
	}
	private void renderInspect(int x,int y){
		graphics().drawString(inspectionStatus,x+10,y+70,0xffff00,2);int line=y+89;
		for(String s:inspectionDetails){if(line>y+242)break;graphics().drawString(s,x+10,line,0xffffff,2);line+=17;}
		graphics().drawString("Right-click targets to inspect or copy authoritative data.",x+10,y+263,0xff981f,1);
		button(x+10,y+276,165,inspectionKind.isEmpty()?"Copy inspected (empty)":"Copy inspected");
	}
	private void renderTerrain(int x,int y){
		toolButton(x+10,y+56,65,"Surface",!terrainStructureTab);toolButton(x+78,y+56,70,"Structure",terrainStructureTab);toolButton(x+152,y+56,60,"Freehand",terrainTool==TerrainTool.FREEHAND);toolButton(x+215,y+56,44,"Line",terrainTool==TerrainTool.LINE);toolButton(x+262,y+56,55,"Rect",terrainTool==TerrainTool.RECTANGLE);checkbox(x+321,y+59,terrainBuildMode,"Build");
		if(terrainStructureTab){renderTerrainStructure(x,y);return;}
		terrainField(x,y+82,"Elevation",paintElevation,terrainElevationText,coordinateFocus==6);
		if(isLayeredTerrainDraft())button(x+307,y+82,68,(terrainElevationOperation==0?"Set":terrainElevationOperation==1?"Raise":"Lower")+" "+terrainElevationStep);
		terrainField(x,y+122,"Floor Color",paintFloorColor,terrainFloorColorText,coordinateFocus==7);
		terrainField(x,y+162,"Floor Texture",paintFloorTexture,terrainFloorTextureText,coordinateFocus==8);
		button(x+307,y+162,128,"Browse textures...");
		if(terrainTool==TerrainTool.RECTANGLE){graphics().drawString("Shape",x+10,y+211,0xffffff,2);toolButton(x+65,y+194,72,"Outline",!rectangleOptions.isFill());toolButton(x+141,y+194,55,"Fill",rectangleOptions.isFill());checkbox(x+204,y+197,rectangleOptions.isSmartWalls(),"Smart");button(x+290,y+194,85,"Save edits");}
		else{graphics().drawString("Brush",x+10,y+211,0xffffff,2);toolButton(x+65,y+194,45,"1x1",terrainBrushSize==1);toolButton(x+114,y+194,45,"3x3",terrainBrushSize==3);toolButton(x+163,y+194,45,"5x5",terrainBrushSize==5);toolButton(x+212,y+194,45,"7x7",terrainBrushSize==7);button(x+270,y+194,105,"Save edits");}
		graphics().drawString(floorTextureVisualName(),x+10,y+231,terrainFieldInvalid(8)?0xff981f:0xffffff,2);
		graphics().drawString(floorTextureTraversal(),x+10,y+247,floorTextureTraversalColor(),2);
		graphics().drawString(terrainTool==TerrainTool.LINE?(terrainLineAnchorX<0?"Line: click an anchor tile.":"Line: preview and click the destination."):terrainTool==TerrainTool.RECTANGLE?(terrainLineAnchorX<0?"Rectangle: click the first corner.":"Rectangle: preview and click the opposite corner."):"Click once, or Ctrl + left-drag across distinct terrain tiles.",x+10,y+264,0xffffff,2);
		graphics().drawString(terrainDragActive||terrainDragReleasePending?terrainDragStatus():"Copy inspected fills values; checked fields are painted.",x+10,y+280,0xff981f,1);
		graphics().drawString(isLayeredTerrainDraft()?"Save journals the layered draft; close/reopen commits it.":"Save commits server/client archives; undo remains disabled.",x+10,y+294,0xff981f,1);
		graphics().drawString(inspectionStatus,x+10,y+307,0xbdbdbd,1);
	}
	private void renderTerrainStructure(int x,int y){
		structureField(x,y+82,"Roof",paintRoof,terrainRoofText,coordinateFocus==9,roofDescription());
		if(terrainTool==TerrainTool.RECTANGLE&&rectangleOptions.isSmartWalls()){checkbox(x+10,y+120,true,"Smart Walls");checkbox(x+10,y+145,rectangleOptions.isNorthWall(),"North");checkbox(x+110,y+145,rectangleOptions.isEastWall(),"East");graphics().drawString("Wall type",x+10,y+187,0xffffff,2);button(x+118,y+170,24,"-");textField(x+148,y+170,54,terrainSmartWallText,coordinateFocus==18);button(x+208,y+170,24,"+");graphics().drawString(compactLine(wallDescription(terrainSmartWall),12),x+240,y+187,0xbdbdbd,1);button(x+330,y+170,105,"Browse walls");graphics().drawString("Shape",x+10,y+211,0xffffff,2);toolButton(x+65,y+194,72,"Outline",!rectangleOptions.isFill());toolButton(x+141,y+194,55,"Fill",rectangleOptions.isFill());button(x+270,y+194,105,"Save edits");graphics().drawString("Smart Walls: choose North, East, or both; diagonal is disabled.",x+10,y+238,0xffffff,1);graphics().drawString(terrainLineCommitTiles!=null?"Rectangle committed; receiving authoritative tiles.":terrainLineAnchorX<0?"Rectangle: click first corner.":"Rectangle: preview and click opposite corner.",x+10,y+286,0xff981f,1);graphics().drawString(inspectionStatus,x+10,y+307,0xbdbdbd,1);return;}
		structureField(x,y+118,"North Wall",rectangleOptions.isNorthWall(),terrainNorthWallText,coordinateFocus==10,wallDescription(terrainNorthWall));
		button(x+330,y+118,105,"Browse walls");
		structureField(x,y+154,"East Wall",rectangleOptions.isEastWall(),terrainEastWallText,coordinateFocus==11,wallDescription(terrainEastWall));
		button(x+330,y+154,105,"Browse walls");
		structureField(x,y+190,"Diagonal",rectangleOptions.isDiagonalWall(),terrainDiagonalWallText,coordinateFocus==12,wallDescription(terrainDiagonalWall));
		button(x+330,y+190,105,"Browse walls");
		graphics().drawString("Diagonal",x+10,y+237,0xffffff,2);toolButton(x+118,y+220,60,"\\",terrainDiagonalOrientation==0);toolButton(x+185,y+220,60,"/",terrainDiagonalOrientation==1);if(terrainTool==TerrainTool.RECTANGLE)checkbox(x+270,y+223,rectangleOptions.isSmartWalls(),"Smart");
		graphics().drawString("Brush",x+10,y+265,0xffffff,2);toolButton(x+65,y+248,45,"1x1",terrainBrushSize==1);toolButton(x+114,y+248,45,"3x3",terrainBrushSize==3);toolButton(x+163,y+248,45,"5x5",terrainBrushSize==5);toolButton(x+212,y+248,45,"7x7",terrainBrushSize==7);button(x+270,y+248,105,"Save edits");
		graphics().drawString(terrainDragActive||terrainDragReleasePending?terrainDragStatus():terrainLineCommitTiles!=null?terrainGestureLabel+" committed; receiving authoritative tiles.":terrainTool==TerrainTool.LINE?(terrainLineAnchorX<0?"Line: click anchor; all checked fields apply.":"Line anchored; click destination to commit."):terrainTool==TerrainTool.RECTANGLE?(terrainLineAnchorX<0?"Rectangle: click first corner.":"Rectangle: click opposite corner to commit."):"Freehand uses centered 1x1 through 7x7 brushes.",x+10,y+286,0xff981f,1);
		graphics().drawString(inspectionStatus,x+10,y+307,0xbdbdbd,1);
	}
	private void terrainField(int x,int y,String label,boolean enabled,String value,boolean focused){checkbox(x+10,y,enabled,label);button(x+150,y,28,"-");textField(x+185,y,80,value,focused);button(x+272,y,28,"+");}
	private void structureField(int x,int y,String label,boolean enabled,String value,boolean focused,String description){checkbox(x+10,y,enabled,label);button(x+118,y,24,"-");textField(x+148,y,54,value,focused);button(x+208,y,24,"+");graphics().drawString(compactLine(description,12),x+240,y+17,0xbdbdbd,1);}
	private String roofDescription(){return terrainRoof==0?"none":"#"+(terrainRoof-1)+" profile";}
	private String wallDescription(int raw){try{return raw==0?"none":WorldEditorDefinitionCatalog.boundaryLabel(raw-1);}catch(Exception e){return "undefined";}}
	private String floorTextureVisualName(){return WorldEditorDefinitionCatalog.floorTextureLabel(terrainFloorTexture);}
	private String floorTextureTraversal(){
		if(WorldBuilderTerrainOverlay.isBlockingBaseColor(terrainFloorTexture))return "Not Walkable";
		int effective=terrainFloorTexture==250?2:terrainFloorTexture;if(effective==0)return "Walkable";
		try{return EntityHandler.getTileDef(effective-1).getObjectType()!=0?"Not Walkable":"Walkable";}catch(Exception e){return "Undefined";}
	}
	private int floorTextureTraversalColor(){String traversal=floorTextureTraversal();return "Walkable".equals(traversal)?0x80c080:"Not Walkable".equals(traversal)?0xff981f:0xff3333;}
	private void renderScenery(int x,int y){
		graphics().drawString("Scenery editing",x+10,y+70,0xffff00,2);
		button(x+10,y+86,28,"-");textField(x+45,y+86,80,sceneryIdText,coordinateFocus==3);button(x+132,y+86,28,"+");
		graphics().drawString(sceneryName(),x+175,y+103,0xffffff,2);
		button(x+175,y+112,134,"Browse scenery...");
		toolButton(x+10,y+145,88,"Place",sceneryTool==SceneryTool.PLACE);toolButton(x+104,y+145,88,"Move",sceneryTool==SceneryTool.MOVE);toolButton(x+198,y+145,88,"Rotate",sceneryTool==SceneryTool.ROTATE);toolButton(x+292,y+145,88,"Remove",sceneryTool==SceneryTool.REMOVE);
		String guidance=sceneryTool==SceneryTool.PLACE?"Click terrain to place one object.":sceneryTool==SceneryTool.MOVE?(isSceneryMoveArmed()?"Preview the ghost, then click its destination.":"Click scenery to select it for an atomic move."):"Click an existing scenery object to "+sceneryTool.name().toLowerCase()+" it.";graphics().drawString(guidance,x+10,y+190,0xffffff,2);
		graphics().drawString("Copying scenery selects its ID. Boundaries remain inspection-only.",x+10,y+218,0xff981f,1);
		button(x+10,y+276,165,"Save queued edits");
	}
	private void renderDefinitionBrowser(int x,int y){
		graphics().drawBoxAlpha(x,y,BROWSER_WIDTH,BROWSER_HEIGHT,0x24190c,245);graphics().drawBoxBorder(x,BROWSER_WIDTH,y,BROWSER_HEIGHT,0);
		graphics().drawBoxAlpha(x,y,BROWSER_WIDTH,28,0x4a3620,255);graphics().drawString("Select "+definitionBrowserFamilyLabel(),x+10,y+19,0xffff00,2);graphics().drawString("X",x+371,y+18,0xffffff,2);
		graphics().drawString("Search by name, description, action, tag, or exact ID",x+10,y+45,0xbdbdbd,1);
		graphics().drawBoxAlpha(x+10,y+50,278,24,0x222222,255);graphics().drawBoxBorder(x+10,278,y+50,24,0x66b3ff);
		String query=definitionBrowser.query();graphics().drawString(compactLine(query.isEmpty()?"Type to search...":query+"|",42),x+16,y+67,query.isEmpty()?0x888888:0xffffff,2);button(x+296,y+50,84,"Clear");
		graphics().drawString(definitionBrowser.resultCount()+" matches | mouse wheel or page buttons",x+10,y+92,0xff981f,1);
		for(int slot=0;slot<WorldEditorDefinitionBrowser.VISIBLE_RESULTS;slot++){
			WorldEditorDefinitionCatalog.Entry entry=definitionBrowser.resultAtVisibleSlot(slot);if(entry==null)continue;
			int row=slot/WorldEditorDefinitionBrowser.COLUMNS,column=slot%WorldEditorDefinitionBrowser.COLUMNS;
			int cardX=x+10+column*(BROWSER_CARD_WIDTH+6),cardY=y+BROWSER_GRID_Y+row*BROWSER_CARD_STEP_Y;boolean selected=entry.id()==selectedDefinitionBrowserId();
			graphics().drawBoxAlpha(cardX,cardY,BROWSER_CARD_WIDTH,BROWSER_CARD_HEIGHT,selected?0x365b82:0x333333,235);graphics().drawBoxBorder(cardX,BROWSER_CARD_WIDTH,cardY,BROWSER_CARD_HEIGHT,selected?0x66b3ff:0x080808);
			graphics().drawString(compactLine(entry.displayName(),27),cardX+6,cardY+16,selected?0xffff00:0xffffff,1);
			graphics().drawString(compactLine(definitionBrowserEntryDetail(entry),27),cardX+6,cardY+33,0xbdbdbd,1);
		}
		if(definitionBrowser.resultCount()==0)graphics().drawString("No "+definitionBrowserFamilyLabel().toLowerCase()+" definitions match this search.",x+10,y+127,0xff981f,2);
		button(x+10,y+296,70,"Previous");button(x+310,y+296,70,"Next");String range=definitionBrowser.rangeLabel();graphics().drawString(range,x+195-graphics().stringWidth(1,range)/2,y+313,0xffffff,1);
	}
	private String definitionBrowserFamilyLabel(){switch(definitionBrowser.family()){
		case BOUNDARY:return "Wall";case FLOOR:return "Floor Texture";case NPC:return "NPC";case ITEM:return "Ground Item";case SCENERY:default:return "Scenery";}}
	private int selectedDefinitionBrowserId(){switch(definitionBrowser.family()){
		case NPC:return npcId;case ITEM:return groundItemId;case SCENERY:return sceneryId;case FLOOR:return terrainFloorTexture;case BOUNDARY:int raw=terrainWallValue(definitionBrowserTerrainField);return raw==0?-1:raw-1;default:return -1;}}
	private String definitionBrowserEntryDetail(WorldEditorDefinitionCatalog.Entry entry){
		if(definitionBrowser.family()==WorldEditorDefinitionBrowser.Family.NPC||definitionBrowser.family()==WorldEditorDefinitionBrowser.Family.ITEM||definitionBrowser.family()==WorldEditorDefinitionBrowser.Family.FLOOR)return "#"+entry.id()+" | "+entry.tags();
		return "#"+entry.id()+" | "+entry.canonicalName();
	}
	private void renderNpc(int x,int y){
		graphics().drawString("NPC editing",x+10,y+70,0xffff00,2);
		button(x+10,y+86,28,"-");textField(x+45,y+86,80,npcIdText,coordinateFocus==4);button(x+132,y+86,28,"+");
		graphics().drawString(npcName(),x+175,y+103,0xffffff,2);
		button(x+175,y+112,134,"Browse NPCs...");
		graphics().drawString("Roam radius",x+10,y+137,0xffffff,2);button(x+10,y+145,28,"-");textField(x+45,y+145,80,npcRadiusText,coordinateFocus==5);button(x+132,y+145,28,"+");
		graphics().drawString("Respawn: "+npcRespawnLabel(),x+10,y+178,0xffffff,2);button(x+10,y+185,28,"-");textField(x+45,y+185,80,npcRespawnText,coordinateFocus==20);button(x+132,y+185,28,"+");
		toolButton(x+10,y+220,95,"Place",npcTool==NpcTool.PLACE);toolButton(x+112,y+220,95,"Remove",npcTool==NpcTool.REMOVE);
		graphics().drawString(npcTool==NpcTool.PLACE?"Click terrain to place one NPC.":"Click an existing NPC to remove it.",x+215,y+235,0xffffff,1);
		button(x+10,y+276,165,"Save queued edits");
	}
	private void renderGroundItems(int x,int y){
		graphics().drawString("Respawning ground-item editing",x+10,y+70,0xffff00,2);
		button(x+10,y+86,28,"-");textField(x+45,y+86,80,groundItemIdText,coordinateFocus==14);button(x+132,y+86,28,"+");
		graphics().drawString(groundItemName(),x+175,y+103,0xffffff,2);
		button(x+175,y+112,134,"Browse items...");
		graphics().drawString("Amount",x+10,y+154,0xffffff,2);button(x+118,y+137,28,"-");textField(x+153,y+137,80,groundItemAmountText,coordinateFocus==15);button(x+240,y+137,28,"+");
		graphics().drawString("Respawn seconds",x+10,y+205,0xffffff,2);button(x+118,y+188,28,"-");textField(x+153,y+188,80,groundItemRespawnText,coordinateFocus==16);button(x+240,y+188,28,"+");
		toolButton(x+10,y+235,95,"Place",groundItemTool==GroundItemTool.PLACE);toolButton(x+112,y+235,95,"Remove",groundItemTool==GroundItemTool.REMOVE);
		graphics().drawString(groundItemTool==GroundItemTool.PLACE?"Click terrain to place.":"Click the visible item to remove.",x+214,y+244,0xffffff,1);
		graphics().drawString(groundItemStackable()?"Stack amount may be 1.."+MAX_GROUND_ITEM_AMOUNT+".":"Non-stackable item: amount is fixed at 1.",x+214,y+258,0xff981f,1);
		button(x+10,y+276,165,"Save queued edits");
	}
	private void renderRegion(int x,int y){
		toolButton(x+10,y+56,100,"Copy",regionTool==RegionTool.COPY);toolButton(x+120,y+56,100,"Cut",regionTool==RegionTool.CUT);toolButton(x+230,y+56,100,"Paste",regionTool==RegionTool.PASTE);
		if(regionTool!=RegionTool.PASTE){boolean cutting=regionTool==RegionTool.CUT;graphics().drawString(regionMarkers.isEmpty()?"Click terrain to place marker 1 and begin tracing the boundary.":regionClosed?(cutting?"Selection stopped. Cut secures a snapshot before changing the world.":"Selection stopped. Review it, then Copy to the clipboard."):"Continue placing ordered markers, then select Stop.",x+10,y+90,0xffffff,2);graphics().drawString("Markers: "+regionMarkers.size()+" | "+(regionClosed?regionPreviewTiles.length+" selected tiles":"selection open"),x+10,y+108,regionClosed?0x80c080:0xffff00,2);toolButton(x+10,y+122,100,regionSelectionActionLabel(),!regionClosed);button(x+120,y+122,100,"Undo");button(x+230,y+122,100,cutting?regionCutActionLabel():regionCopyBridge.isPending()?"Copying...":"Copy");button(x+340,y+122,100,isRegionSharingPending()?"Working...":"Export");graphics().drawString(cutting?"Cut creates/reopens the snapshot and exact plan before confirmation.":"Start/Stop/Reset controls markers. Copy captures the closed selection.",x+10,y+174,0xff981f,1);graphics().drawString(cutting?"Confirm Cut replaces terrain with canonical void and removes owned placements.":"Export saves the current clipboard snapshot as a portable .wbr file.",x+10,y+192,cutting?0xff981f:0xbdbdbd,1);if(!lastRegionSnapshotId.isEmpty()){graphics().drawString("Clipboard: "+lastRegionSnapshotName+" ["+shortHash(lastRegionSnapshotId)+"]",x+10,y+228,0xffff00,2);graphics().drawString(lastRegionTileCount+" tiles, "+lastRegionPlacementCount+" placements, "+lastRegionCrossingCount+" crossing reports",x+10,y+248,0xbdbdbd,1);}graphics().drawString(compactLine(inspectionStatus,62),x+10,y+292,0xbdbdbd,1);}
		else{WorldBuilderRegionPasteClientBridge.Snapshot snapshot=selectedRegionSnapshot();boolean sharing=isRegionSharingPending();graphics().drawString(snapshot==null?"Clipboard is empty. Use Copy or Import first.":"Clipboard: "+snapshot.name+" ["+shortHash(snapshot.id)+"]",x+10,y+90,snapshot==null?0xff981f:0xffff00,2);graphics().drawString(regionPasteX<0?"Click terrain to choose where marker 1 should be placed.":"Destination marker 1: "+regionPasteX+", "+regionPasteY+", level "+regionPasteLevel,x+10,y+110,0xffffff,2);button(x+10,y+122,165,regionPasteActionLabel());button(x+185,y+154,100,regionPasteBridge.isPending()?"Working...":"Undo");button(x+295,y+154,140,sharing?"Working...":"Import .wbr");if(snapshot!=null)graphics().drawString(snapshot.tileCount+" tiles, "+snapshot.placementCount+" placements, "+snapshot.levelCount+" level(s)",x+185,y+139,0xbdbdbd,1);graphics().drawString(regionPastePlanHash.isEmpty()?"Import loads one portable snapshot into the clipboard.":regionPastePreviewTiles.length+" preview tiles | "+regionPasteCollisionTiles.length+" visible collision marker(s)",x+10,y+212,regionPasteBlocked?0xff4040:regionPasteOverwrite?0xff981f:0x80c080,1);graphics().drawString(regionPasteOverwrite?"Occupied destination: Paste > Overwrite? > Confirm.":"Paste applies the exact preview live; Undo restores the exact prior package.",x+10,y+234,regionPasteOverwrite?0xff981f:0xbdbdbd,1);graphics().drawString(compactLine(inspectionStatus,62),x+10,y+292,0xbdbdbd,1);}
	}
	private void toolButton(int x,int y,int w,String text,boolean active){graphics().drawBoxAlpha(x,y,w,24,active?0x365b82:0x333333,220);graphics().drawBoxBorder(x,w,y,24,active?0x66b3ff:0);graphics().drawString(text,x+6,y+17,0xffffff,2);}
	private String sceneryName(){try{return WorldEditorDefinitionCatalog.sceneryLabel(sceneryId);}catch(Exception e){return "Unknown scenery";}}
	private String npcName(){try{return EntityHandler.getNpcDef(npcId).getName();}catch(Exception e){return "Unknown NPC";}}
	private String groundItemName(){try{return EntityHandler.getItemDef(groundItemId).getName();}catch(Exception e){return "Unknown item";}}
	private boolean groundItemStackable(){try{return EntityHandler.getItemDef(groundItemId).isStackable();}catch(Exception e){return false;}}
	private void textField(int x,int y,int w,String text,boolean focused){graphics().drawBoxAlpha(x,y,w,24,focused?0x6580b7:0x222222,240);graphics().drawBoxBorder(x,w,y,24,0);graphics().drawString(text+(focused?"*":""),x+6,y+17,0xffffff,2);}
	private void checkbox(int x,int y,boolean checked,String text){graphics().drawBoxAlpha(x,y,18,18,checked?0x365b82:0x333333,255);graphics().drawBoxBorder(x,18,y,18,checked?0x66b3ff:0);if(checked)graphics().drawString("X",x+5,y+14,0xffffff,2);graphics().drawString(text,x+26,y+14,0xffffff,2);}
	private void button(int x,int y,int w,String text){graphics().drawBoxAlpha(x,y,w,24,0x333333,220);graphics().drawBoxBorder(x,w,y,24,0);graphics().drawString(text,x+6,y+17,0xffffff,2);}
	private boolean isLayeredReview(){return WorldBuilderClientProfile.current().isLayeredReview();}
	private boolean isLayeredTerrainDraft(){return WorldBuilderClientProfile.current().isLayeredTerrainDraft();}
	private boolean isLayeredSceneryDraftLevel(){if(!isLayeredTerrainDraft())return false;return WorldBuilderClientProfile.current().canAuthorLevel(mc.getEditorPlayerWorldLevel());}
	private boolean isLayeredPlacementDraftLevel(){return isLayeredSceneryDraftLevel();}
	private int editorLevel(int worldY){return isLayeredReview()?mc.getEditorPlayerWorldLevel():Math.floorDiv(worldY,944);}
	private boolean validTeleportLevel(int level){return !isLayeredReview()||isLayeredTerrainDraft()||WorldBuilderClientProfile.current().declaresLayer(level);}
	private static int logicalLevelForLegacyPlane(int plane){return plane==3?-1:plane;}
	private static String point(int x,int y){return x<0||y<0?"not set":x+","+y;}
	private static String point(int x,int y,int level){return x<0||y<0?"not set":x+","+y+",L"+level;}
	private static int diagonalDefinitionId(int v){if(v>0&&v<12000)return v-1;if(v>12000&&v<24000)return v-12001;return -1;}
	private static String diagonalRotation(int v){return v>12000&&v<24000?"rotated":v>0&&v<12000?"not rotated":"none";}
	private static String wall(int id,String name){return id<0?"none":WorldEditorDefinitionCatalog.boundaryLabel(id,name);}
	private static String planeName(int plane){switch(plane){case 0:return "Surface";case 1:return "First floor";case 2:return "Second floor";case -1:case 3:return "Underground";default:return plane<0?"Depth "+plane:"Upper level "+plane;}}
	private static int valueAfter(String text,String marker){if(text==null)return -1;int at=text.indexOf(marker);if(at<0)return -1;at+=marker.length();int end=at;if(end<text.length()&&text.charAt(end)=='-')end++;while(end<text.length()&&Character.isDigit(text.charAt(end)))end++;try{return Integer.parseInt(text.substring(at,end));}catch(Exception e){return -1;}}
	private static String join(String[] lines){StringBuilder b=new StringBuilder();for(String line:lines)b.append(line).append(' ');return b.toString();}
	private static String compactLine(String text,int max){if(text==null)return "";return text.length()<=max?text:text.substring(0,Math.max(0,max-3))+"...";}
	private static String[] wrap(String s,int width){if(s==null||s.isEmpty())return new String[0];java.util.List<String> lines=new java.util.ArrayList<String>();while(s.length()>width){int p=s.lastIndexOf(' ',width);if(p<1)p=width;lines.add(s.substring(0,p));s=s.substring(p).trim();}lines.add(s);return lines.toArray(new String[lines.size()]);}
}
