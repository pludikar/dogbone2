import logging
import adsk.core, adsk.fusion
import traceback
from .register import Register
from ..common import dbutils as util


logger = logging.getLogger('dogbone.parametric')
makeNative = lambda x: x.nativeObject if x.nativeObject else x
reValidateFace = lambda comp, x: comp.findBRepUsingPoint(x, adsk.fusion.BRepEntityTypes.BRepFaceEntityType,-1.0 ,False ).item(0)


def createParametricDogbones():
    logger.info('Creating parametric dogbones')
    self.errorCount = 0
    if not self.design:
        raise RuntimeError('No active Fusion design')
    holeInput: adsk.fusion.HoleFeatureInput = None
    offsetByStr = adsk.core.ValueInput.createByString('dbHoleOffset')
    centreDistance = self.radius*(1+self.minimalPercent/100 if self.dbType=='Minimal Dogbone' else  1)
    
    for occurrenceFace in self.selectedOccurrences.values():
        startTlMarker = self.design.timeline.markerPosition

        if occurrenceFace[0].face.assemblyContext:
            comp = occurrenceFace[0].face.assemblyContext.component
            occ = occurrenceFace[0].face.assemblyContext
            logger.debug(f'processing component  = {comp.name}')
            logger.debug(f'processing occurrence  = {occ.name}')
            #entityName = occ.name.split(':')[-1]
        else:
            comp = self.rootComp
            occ = None
            logger.debug(f'processing Rootcomponent')

        if self.fromTop:
            (topFace, topFaceRefPoint) = util.getTopFace(makeNative(occurrenceFace[0].face))
            logger.info(f'Processing holes from top face - {topFace.body.name}')

        for selectedFace in occurrenceFace:
            if len(selectedFace.selectedEdges.values()) <1:
                logger.debug(f'Face has no edges')
            face = makeNative(selectedFace.face)
            
            comp: adsk.fusion.Component = comp
            
            if not face.isValid:
                logger.debug(f'revalidating Face')
                face = reValidateFace(comp, selectedFace.refPoint)
            logger.debug(f'Processing Face = {face.tempId}')
            
            #faceNormal = util.getFaceNormal(face.nativeObject)
            if self.fromTop:
                logger.debug(f'topFace type {type(topFace)}')
                if not topFace.isValid:
                    logger.debug(f'revalidating topFace') 
                    topFace = reValidateFace(comp, topFaceRefPoint)

                topFace = makeNative(topFace)
                    
                logger.debug(f'topFace isValid = {topFace.isValid}')
                transformVector = util.getTranslateVectorBetweenFaces(face, topFace)
                logger.debug(f'creating transformVector to topFace = ({transformVector.x}, {transformVector.y}, {transformVector.z}) length = {transformVector.length}')
                            
            for selectedEdge in selectedFace.selectedEdges.values():
                
                logger.debug(f'Processing edge - {selectedEdge.edge.tempId}')

                if not selectedEdge.selected:
                    logger.debug(f'  Not selected. Skipping...')
                    continue

                if not face.isValid:
                    logger.debug(f'Revalidating face')
                    face = reValidateFace(comp, selectedFace.refPoint)

                if not selectedEdge.edge.isValid:
                    continue # edges that have been processed already will not be valid any more - at the moment this is easier than removing the 
#                    affected edge from self.edges after having been processed
                edge = makeNative(selectedEdge.edge)
                try:
                    if not util.isEdgeAssociatedWithFace(face, edge):
                        continue  # skip if edge is not associated with the face currently being processed
                except:
                    pass
                
                startVertex: adsk.fusion.BRepVertex = util.getVertexAtFace(face, edge)
                extentToEntity = util.findExtent(face, edge)

                extentToEntity = makeNative(extentToEntity)
                logger.debug(f'extentToEntity - {extentToEntity.isValid}')
                if not extentToEntity.isValid:
                    logger.debug(f'To face invalid')

                try:
                    (edge1, edge2) = util.getCornerEdgesAtFace(face, edge)
                except:
                    logger.exception('Failed at findAdjecentFaceEdges')
                    util.messageBox(f'Failed at findAdjecentFaceEdges:\n{traceback.format_exc()}')
                
                centrePoint = makeNative(startVertex).geometry.copy()
                    
                selectedEdgeFaces = makeNative(selectedEdge.edge).faces
                
                dirVect: adsk.core.Vector3D = util.getFaceNormal(selectedEdgeFaces[0]).copy()
                dirVect.add(util.getFaceNormal(selectedEdgeFaces[1]))
                dirVect.normalize()
                dirVect.scaleBy(centreDistance)  #ideally radius should be linked to parameters, 

                if self.dbType == 'Mortise Dogbone':
                    direction0 = util.correctedEdgeVector(edge1,startVertex) 
                    direction1 = util.correctedEdgeVector(edge2,startVertex)
                    
                    if self.longside:
                        if (edge1.length > edge2.length):
                            dirVect = direction0
                            edge1OffsetByStr = adsk.core.ValueInput.createByReal(0)
                            edge2OffsetByStr = offsetByStr
                        else:
                            dirVect = direction1
                            edge2OffsetByStr = adsk.core.ValueInput.createByReal(0)
                            edge1OffsetByStr = offsetByStr
                    else:
                        if (edge1.length > edge2.length):
                            dirVect = direction1
                            edge2OffsetByStr = adsk.core.ValueInput.createByReal(0)
                            edge1OffsetByStr = offsetByStr
                        else:
                            dirVect = direction0
                            edge1OffsetByStr = adsk.core.ValueInput.createByReal(0)
                            edge2OffsetByStr = offsetByStr
                else:
                    dirVect: adsk.core.Vector3D = util.getFaceNormal(makeNative(selectedEdgeFaces[0])).copy()
                    dirVect.add(util.getFaceNormal(makeNative(selectedEdgeFaces[1])))
                    edge1OffsetByStr = offsetByStr
                    edge2OffsetByStr = offsetByStr

                centrePoint.translateBy(dirVect)
                logger.debug(f'centrePoint = ({centrePoint.x}, {centrePoint.y}, {centrePoint.z})')

                if self.fromTop:
                    centrePoint.translateBy(transformVector)
                    logger.debug(f'centrePoint at topFace = {centrePoint.asArray()}')
                    holePlane = topFace if self.fromTop else face
                    if not holePlane.isValid:
                        holePlane = reValidateFace(comp, topFaceRefPoint)
                else:
                    holePlane = makeNative(face)
                        
                holes =  comp.features.holeFeatures
                holeInput = holes.createSimpleInput(adsk.core.ValueInput.createByString('dbRadius*2'))
#                    holeInput.creationOccurrence = occ #This needs to be uncommented once AD fixes component copy issue!!
                holeInput.isDefaultDirection = True
                holeInput.tipAngle = adsk.core.ValueInput.createByString('180 deg')
#                    holeInput.participantBodies = [face.nativeObject.body if occ else face.body]  #Restore this once AD fixes occurrence bugs
                holeInput.participantBodies = [makeNative(face.body)]
                
                logger.debug(f'extentToEntity before setPositionByPlaneAndOffsets - {extentToEntity.isValid}')
                holeInput.setPositionByPlaneAndOffsets(holePlane, centrePoint, edge1, edge1OffsetByStr, edge2, edge2OffsetByStr)
                logger.debug(f'extentToEntity after setPositionByPlaneAndOffsets - {extentToEntity.isValid}')
                holeInput.setOneSideToExtent(extentToEntity, False)
                logger.info('hole added to list - {}'.format(centrePoint.asArray()))

                holeFeature = holes.add(holeInput)
                holeFeature.name = 'dogbone'
                holeFeature.isSuppressed = True
                
            for hole in holes:
                if hole.name[:7] != 'dogbone':
                    break
                hole.isSuppressed = False
                
        endTlMarker = self.design.timeline.markerPosition-1
        if endTlMarker - startTlMarker >0:
            timelineGroup = self.design.timeline.timelineGroups.add(startTlMarker,endTlMarker)
            timelineGroup.name = 'dogbone'
#            logger.debug(f'doEvents - allowing display to refresh')
#            adsk.doEvents()
        

