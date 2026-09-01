package com.openrsc.interfaces.misc;

/** Correlates the single in-flight Builder entity mutation with its sequenced reply. */
final class WorldEditorEntityEditTracker {
	private int operation;
	private int expectedNextSequence;
	private boolean saveQueued;

	boolean begin(int currentSequence,int requestedOperation){
		if(requestedOperation<1||requestedOperation>8||isPending())return false;
		operation=requestedOperation;expectedNextSequence=currentSequence+1;return true;
	}

	boolean complete(int nextSequence,int completedOperation){
		if(!isPending()||nextSequence!=expectedNextSequence||completedOperation!=operation)return false;
		operation=0;expectedNextSequence=0;return true;
	}

	boolean isPending(){return operation!=0;}
	int pendingCount(){return isPending()?1:0;}
	void noteSaveQueued(){if(isPending())saveQueued=true;}
	boolean isQueuedSaveReady(){return saveQueued&&!isPending();}
	void clearQueuedSave(){saveQueued=false;}
	void reset(){operation=0;expectedNextSequence=0;saveQueued=false;}
}
