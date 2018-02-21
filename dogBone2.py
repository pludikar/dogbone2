#Author-Peter Ludikar
#Description-An Add-In for making dog-bone fillets.

# This version is a proof of concept 

# I've completely revamped the dogbone add-in by Casey Rogers and Patrick Rainsberry and David Liu
# some of the original utilities have remained, but mostly everything else has changed.

# The original add-in was based on creating sketch points and extruding - I found using sketches and extrusion to be very heavy 
# on processing resources, so this version has been designed to create dogbones directly by using a hole tool. So far the
# the performance of this approach is day and night compared to the original version. 

# Select the face you want the dogbones to drop from. Specify a tool diameter and a radial offset.
# The add-in will then create a dogbone with diamater equal to the tool diameter plus
# twice the offset (as the offset is applied to the radius) at each selected edge.

 
from collections import defaultdict

import adsk.core, adsk.fusion
import math
import traceback
import uuid

import time
from . import dbutils as dbUtils

#constants - to keep attribute group and names consistent
DOGBONEGROUP = 'dogBoneGroup'
FACE_ID = 'faceID'
REV_ID = 'revId'
ID = 'id'



class DogboneCommand(object):
    COMMAND_ID = "dogboneBtn"
    
    faceAssociations = {}

    def __init__(self):
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface

        self.offStr = "0"
        self.offVal = None
        self.circStr = "0.25 in"
        self.circVal = None
        self.edges = []
        self.benchmark = False
        self.errorCount = 0
        self.faceSelections = adsk.core.ObjectCollection.create()

        self.handlers = dbUtils.HandlerHelper()

    def addButton(self):
        # clean up any crashed instances of the button if existing
        try:
            self.removeButton()
        except:
            pass

        # add add-in to UI
        buttonDogbone = self.ui.commandDefinitions.addButtonDefinition(
            self.COMMAND_ID, 'Dogbone', 'Creates dogbones at all inside corners of a face', 'Resources')

        buttonDogbone.commandCreated.add(self.handlers.make_handler(adsk.core.CommandCreatedEventHandler,
                                                                    self.onCreate))

        createPanel = self.ui.allToolbarPanels.itemById('SolidCreatePanel')
        buttonControl = createPanel.controls.addCommand(buttonDogbone, 'dogboneBtn')

        # Make the button available in the panel.
        buttonControl.isPromotedByDefault = True
        buttonControl.isPromoted = True

    def removeButton(self):
        cmdDef = self.ui.commandDefinitions.itemById(self.COMMAND_ID)
        if cmdDef:
            cmdDef.deleteMe()
        createPanel = self.ui.allToolbarPanels.itemById('SolidCreatePanel')
        cntrl = createPanel.controls.itemById(self.COMMAND_ID)
        if cntrl:
            cntrl.deleteMe()

    def onCreate(self, args:adsk.core.CommandCreatedEventArgs):
        inputs = adsk.core.CommandCreatedEventArgs.cast(args)
        self.edges = []
        self.faces = []
        self.faceAssociations = {}
        self.errorCount = 0
        self.faceSelections.clear()
        self.selectedOccurrences = {}
        self.selectedFaces = {}
        self.selectedEdges = {}
        argsCmd = adsk.core.Command.cast(args)

        inputs = adsk.core.CommandInputs.cast(inputs.command.commandInputs)

        selInput0 = inputs.addSelectionInput(
            'select', 'Face',
            'Select a face to apply dogbones to all internal corner edges')
#        selInput0.addSelectionFilter('LinearEdges')
        selInput0.addSelectionFilter('PlanarFaces')
        selInput0.setSelectionLimits(1,0)
        
        selInput1 = inputs.addSelectionInput(
            'edgeSelect', 'DogBone Edges',
            'Select a face to apply dogbones to all internal corner edges')
#        selInput0.addSelectionFilter('LinearEdges')
        selInput1.addSelectionFilter('LinearEdges')
        selInput1.setSelectionLimits(1,0)
        selInput1.isVisible = False

        
        inp = inputs.addValueInput(
            'circDiameter', 'Tool Diameter', self.design.unitsManager.defaultLengthUnits,
            adsk.core.ValueInput.createByString(self.circStr))
        inp.tooltip = "Size of the tool with which you'll cut the dogbone."

        inp = inputs.addValueInput(
            'offset', 'Additional Offset', self.design.unitsManager.defaultLengthUnits,
            adsk.core.ValueInput.createByString(self.offStr))
        inp.tooltip = "Additional increase to the radius of the dogbone."

        inputs.addBoolValueInput("benchmark", "Benchmark running time", True, "", self.benchmark)
        
        textBox = inputs.addTextBoxCommandInput('TextBox', '', '', 1, True)

        cmd = adsk.core.Command.cast(args.command)
        # Add handlers to this command.
        cmd.execute.add(self.handlers.make_handler(adsk.core.CommandEventHandler, self.onExecute))
        cmd.selectionEvent.add(self.handlers.make_handler(adsk.core.SelectionEventHandler, self.onFaceSelect))
        cmd.validateInputs.add(
            self.handlers.make_handler(adsk.core.ValidateInputsEventHandler, self.onValidate))
        cmd.inputChanged.add(
            self.handlers.make_handler(adsk.core.InputChangedEventHandler, self.onChange))

#==============================================================================
#  routine to process any changed selections
#  this is where selection and deselection management takes place
#  also where eligible edges are determined
#==============================================================================
    def onChange(self, args:adsk.core.InputChangedEventArgs):
        
        changedInput = adsk.core.CommandInput.cast(args.input)
        if changedInput.id != 'select' and changedInput.id != 'edgeSelect':
            return
        if changedInput.id == 'select':
#==============================================================================
#            processing changes to face selections
#==============================================================================
            if len(self.selectedFaces) > changedInput.selectionCount:
                
                # a face has been removed
                newFaceList = self.selectedFaces.keys()
                try:
                    faceOccurrenceId = changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext.name.split(':')[-1]
                except OverflowError:  #Overflowed because all faces have been unselected - using the x/delete button
                    self.selectedFaces.clear()
                    self.selectedEdges.clear()
                    changedInput.commandInputs.itemById('edgeSelect').clearSelection()
                    changedInput.commandInputs.itemById('select').hasFocus = True
                   
                    return
                    
                selectionList = [str(changedInput.selection(i).entity.tempId) +':'+ faceOccurrenceId for i in range(changedInput.selectionCount)]
                missingFace = [select for select in newFaceList if select not in selectionList][0]
                edgeList = self.selectedFaces[missingFace][1]
                changedInput.commandInputs.itemById('edgeSelect').hasFocus = True
                if edgeList[0].assemblyContext:
                    activeOccurrenceName = edgeList[0].assemblyContext.name
                else:
                    activeOccurrenceName = 'root'
                del self.selectedFaces[missingFace]
                del self.selectedOccurrences[activeOccurrenceName]
                for edge in edgeList:
                    self.ui.activeSelections.removeByEntity(edge)
                changedInput.commandInputs.itemById('select').hasFocus = True
                return
             
#==============================================================================
#             Face has been added - assume that the last selection entity is the one added
#==============================================================================
            face = adsk.fusion.BRepFace.cast(changedInput.selection(changedInput.selectionCount -1).entity)
            changedInput.commandInputs.itemById('edgeSelect').isVisible = True  
            
            changedEntity = changedInput.selection(changedInput.selectionCount-1).entity
            if changedEntity.assemblyContext:
                activeOccurrenceName = changedEntity.assemblyContext.name
            else:
                activeOccurrenceName = changedEntity.body.name
                
            if changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext:
                changedEntityName = changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext.name.split(':')[-1]
            else:
                changedEntityName = changedEntity.body.name
            
            faceId = str(changedEntity.tempId) + ":" + changedEntityName 
            faces = []
            faces = self.selectedOccurrences.get(activeOccurrenceName, faces)
            faces.append(faceId)
            self.selectedOccurrences[activeOccurrenceName] = faces # adds a face to a list of faces associated with this occurrence
            self.selectedFaces[faceId] = [face, adsk.core.ObjectCollection.create(), face.nativeObject.pointOnFace if face.assemblyContext else face.pointOnFace]  # creates a collecton (of edges) associated with a faceId
            
            faceNormal = dbUtils.getFaceNormal(face)
#==============================================================================
#             this is where inside corner edges, dropping down from the face are processed
#==============================================================================
            for edge in face.body.edges:
                if edge.isDegenerate:
                    continue
                if edge in self.edges:
                    continue
                try:
                    if edge.geometry.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
                        continue
                    vector = edge.startVertex.geometry.vectorTo(edge.endVertex.geometry)
                    if vector.isPerpendicularTo(faceNormal):
                        continue
                    if edge.faces.item(0).geometry.objectType != adsk.core.Plane.classType():
                        continue
                    if edge.faces.item(1).geometry.objectType != adsk.core.Plane.classType():
                        continue              
                    if edge.startVertex not in face.vertices:
                        if edge.endVertex not in face.vertices:
                            continue
                        else:
                            vector = edge.endVertex.geometry.vectorTo(edge.startVertex.geometry)
                    if vector.dotProduct(faceNormal) >= 0:
                        continue
                    if dbUtils.getAngleBetweenFaces(edge) > math.pi:
                        continue
                    changedInput.commandInputs.itemById('edgeSelect').addSelection(edge)
                    self.selectedFaces[faceId][1].add(edge)

                    activeEdgeName = edge.assemblyContext.name.split(':')[-1] if edge.assemblyContext else edge.body.name

                    edgeId = str(edge.tempId)+':'+ activeEdgeName
                    self.selectedEdges[edgeId] = faceId
                except:
                    dbUtils.messageBox('Failed at edge:\n{}'.format(traceback.format_exc()))

                 #end of processing faces
#==============================================================================
#         Processing changed edge selection            
#==============================================================================
        if changedInput.id != 'edgeSelect':
            return
        if len(self.selectedEdges) > changedInput.selectionCount:
#==============================================================================
#             an edge has been removed
#==============================================================================
        # only need to do something if there are no edges left associated with a face
         #have to work backwards edge to faceId, then remove face from selection if associated edges == 0
        # This is complicated because all selected edges are mixed together, you can't simply find the edges that are associated
            if changedInput.selectionCount == 0:
#       All the edges have been deleted (selectionCount - 1) is negative
                changedInput.isVisible = False
                changedInput.commandInputs.itemById('select').hasFocus = True
                self.selectedFaces.clear
                self.ui.activeSelections.clear()
                return
            
            changedSelections = changedInput.selection

            calcEdgeId = lambda x: str(x.tempId) + ':' + x.assemblyContext.name.split(':')[-1] if x.assemblyContext else str(x.tempId) + ':' + x.body.name
            lookupEdge = lambda x: self.selectedEdges[x]

            changedSelectionList = [changedInput.selection(i).entity for i in range(changedInput.selectionCount)]
            changedEdgeIdList = map(calcEdgeId, changedSelectionList) # creates list of 
            changedEdge_FaceIdList = map(lookupEdge, changedEdgeIdList)
            consolidatedFaceList = set(changedEdge_FaceIdList)
#       find set of faces associated with all edges - if the face is missing, then all edges of the associated edges have been unselected
            try:
                missingFace = [face for face in self.selectedFaces.keys() if face not in consolidatedFaceList]
#                will be [] if no missing face
            except Exception as e:
#               get here because last edge of an associated face has been unselected 
                changedInput.commandInputs.itemById('select').hasFocus = True
                self.ui.activeSelections.removeByEntity(self.selectedFaces[0])
                changedInput.commandInputs.itemById('edgeSelect').hasFocus = True
                return
            if len(missingFace) :
                changedInput.commandInputs.itemById('select').hasFocus = True
                self.ui.activeSelections.removeByEntity(self.selectedFaces[missingFace[0]][0])
                changedInput.commandInputs.itemById('edgeSelect').hasFocus = True
                del self.selectedFaces[missingFace[0]]    
                return
            for face in self.selectedFaces.values():
                missingEdge = [edge for edge in iter(face[1]) if edge not in changedSelectionList]
                if not missingEdge:
                    continue
                face[1].removeByItem(missingEdge[0])
            return
#==============================================================================
#         end of processing removed edge
#TODO:         start of processing added edge
#==============================================================================
      
#==============================================================================
# put the selections into variables that can be accessed by the main routine            
#==============================================================================
    def parseInputs(self, inputs):
        inputs = {inp.id: inp for inp in inputs}

        self.circStr = inputs['circDiameter'].expression
        self.circVal = inputs['circDiameter'].value
        self.offStr = inputs['offset'].expression
        self.offVal = inputs['offset'].value
        self.benchmark = inputs['benchmark'].value

        self.edges = []
        self.faces = []
        
        for i in range(inputs['edgeSelect'].selectionCount):
            entity = inputs['edgeSelect'].selection(i).entity
            if entity.objectType == adsk.fusion.BRepEdge.classType():
                self.edges.append(entity)
        for i in range(inputs['select'].selectionCount):
            entity = inputs['select'].selection(i).entity
            if entity.objectType == adsk.fusion.BRepFace.classType():
                self.faces.append(entity)


    def onExecute(self, args):
        start = time.time()

        self.parseInputs(args.firingEvent.sender.commandInputs)
        self.createConsolidatedDogbones()

        if self.benchmark:
            dbUtils.messageBox("Benchmark: {:.02f} sec processing {} edges".format(
                time.time() - start, len(self.edges)))

    def onValidate(self, args):
        cmd = adsk.core.ValidateInputsEventArgs.cast(args)
        cmd = args.firingEvent.sender

        for input in cmd.commandInputs:
            if input.id == 'select':
                if input.selectionCount < 1:
                    args.areInputsValid = False
            elif input.id == 'circDiameter':
                if input.value <= 0:
                    args.areInputsValid = False
#==============================================================================
#  Routine gets called with every mouse movement, if a commandInput select is active                   
#==============================================================================
    def onFaceSelect(self, args):
        eventArgs = adsk.core.SelectionEventArgs.cast(args)
        # Check which selection input the event is firing for.
        activeIn = eventArgs.firingEvent.activeInput
        if activeIn.id != 'select' and activeIn.id != 'edgeSelect':
            return # jump out if not dealing with either of the two selection boxes

        if activeIn.id == 'select':
#==============================================================================
# processing activities when faces are being selected
#        selection filter is limited to planar faces
#        makes sure only valid occurrences and components are selectable
#==============================================================================

            if not len( self.selectedOccurrences): #get out if the face selection list is empty
                eventArgs.isSelectable = True
                return
 
            if not eventArgs.selection.entity.assemblyContext:
#                dealing with a root component body
                activeBodyName = eventArgs.selection.entity.body.name
                try:            
                    primaryFaceId = self.selectedOccurrences[activeBodyName]
                    primaryFace = self.selectedFaces[primaryFaceId[0]][0] #get actual BrepFace from its ID
                except KeyError as e:
#                    self.selectedFaces.clear()
#                    self.selectedOccurrences.clear()
                    return
                primaryFaceNormal = dbUtils.getFaceNormal(primaryFace)
                if primaryFaceNormal.isParallelTo(dbUtils.getFaceNormal(eventArgs.selection.entity)):
                    eventArgs.isSelectable = True
                    return
                eventArgs.isSelectable = False
                return
#           End of root component face processing
#==============================================================================
# Start of occurrence face processing              
#==============================================================================

            activeOccurrence = eventArgs.selection.entity.assemblyContext
            activeOccurrenceName = activeOccurrence.name
            activeComponent = activeOccurrence.component

                 
#           we got here because the face is either not in root or is on the existing selected list    
#           at this point only need to check for duplicate component selection - Only one component allowed, to save on conflict checking
            filtered = filter(lambda x: self.selectedFaces[x[0]][0].assemblyContext, self.selectedOccurrences.values())
            try:
                selectedComponentList = [self.selectedFaces[x[0]][0].assemblyContext.component for x in self.selectedOccurrences.values() if self.selectedFaces[x[0]][0].assemblyContext]
            except KeyError:
                eventArgs.isSelectable = True
                return

            if activeComponent not in selectedComponentList:
                    eventArgs.isSelectable = True
                    return

            if activeOccurrenceName not in self.selectedOccurrences:  #check if mouse is over a face that is not already selected
                eventArgs.isSelectable = False
                return
                
            faceId = str(eventArgs.selection.entity.tempId)+":"+ activeOccurrenceName

            textResult = activeIn.parentCommand.commandInputs.itemById('TextBox') #Debugging
            textResult.text = 'faceId: ' + str(faceId)+':'+str(eventArgs.isSelectable) #Debugging

            
            try:            
                primaryFaceId = self.selectedOccurrences[activeOccurrenceName]
                primaryFace = self.selectedFaces[primaryFaceId[0]][0] #get actual BrepFace from its ID
            except KeyError:
                self.selectedFaces.clear()
                self.selectedOccurrences.clear()
                return
            primaryFaceNormal = dbUtils.getFaceNormal(primaryFace)
            if primaryFaceNormal.isParallelTo(dbUtils.getFaceNormal(eventArgs.selection.entity)):
                eventArgs.isSelectable = True
                return
            eventArgs.isSelectable = False
            return
#        end selecting faces
            
        else:
#==============================================================================
#             processing edges associated with face - edges selection has focus
#==============================================================================
            selected = eventArgs.selection
            currentEdge = adsk.fusion.BRepEdge.cast(selected.entity)
            
            activeOccurrence = eventArgs.selection.entity.assemblyContext
            if eventArgs.selection.entity.assemblyContext:
                activeOccurrenceName = activeOccurrence.name
            else:
                activeOccurrenceName = eventArgs.selection.entity.body.name 
            
            try:            
                primaryFaceId = self.selectedOccurrences[activeOccurrenceName]
                primaryFace = self.selectedFaces[primaryFaceId[0]][0] #get actual BrepFace from its ID
            except KeyError:
                return # means edge >primaryFaceId is not in the selection list - so we can escape 
            primaryFaceNormal = dbUtils.getFaceNormal(primaryFace)
            
            edgeVector = currentEdge.startVertex.geometry.vectorTo(currentEdge.endVertex.geometry)
#==============================================================================
#             make sure only edges perpendicular to the primary face can be selected
#==============================================================================
            if not edgeVector.isParallelTo(primaryFaceNormal):
                eventArgs.isSelectable = False
                return
            eventArgs.isSelectable = True            
            return
            
        
#        selected = eventArgs.selection
#        selectedEntity = selected.entity

    @property
    def design(self):
        return self.app.activeProduct

    @property
    def rootComp(self):
        return self.design.rootComponent

    @property
    def originPlane(self):
        return self.rootComp.xZConstructionPlane if self.yUp else self.rootComp.xYConstructionPlane

    # The main algorithm
    def createConsolidatedDogbones(self):
        self.errorCount = 0
        if not self.design:
            raise RuntimeError('No active Fusion design')
        holeInput = adsk.fusion.HoleFeatureInput.cast(None)
        userParams = adsk.fusion.UserParameters.cast(self.design.userParameters)
#set up parameters, so that changes can be easily made after dogbones have been inserted
        if not userParams.itemByName('dbToolDia'):
            dValIn = adsk.core.ValueInput.createByString(self.circStr)
            dParameter = userParams.add('dbToolDia',dValIn, self.design.unitsManager.defaultLengthUnits, '')
            dParameter.isFavorite = True
        else:
            uParam = userParams.itemByName('dbToolDia')
            uParam.isFavorite = True
            
        if not userParams.itemByName('dbOffset'):
            rValIn = adsk.core.ValueInput.createByString(self.offStr)
            rParameter = userParams.add('dbOffset',rValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
        else:
            uParam = userParams.itemByName('dbOffset')
            uParam.comment = 'Do NOT change formula'

        if not userParams.itemByName('dbRadius'):
            rValIn = adsk.core.ValueInput.createByString('dbToolDia/2 + dbOffset')
            rParameter = userParams.add('dbRadius',rValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
        else:
            uParam = userParams.itemByName('dbRadius')
            uParam.expression = 'dbToolDia/2 + dbOffset'
            uParam.comment = 'Do NOT change formula'


        if not userParams.itemByName('dbHoleOffset'):
            oValIn = adsk.core.ValueInput.createByString('dbRadius / sqrt(2)')
            oParameter = userParams.add('dbHoleOffset', oValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
        else:
            uParam = userParams.itemByName('dbHoleOffset')
            uParam.expression = 'dbRadius / sqrt(2)'
            uParam.comment = 'Do NOT change formula'

        radius = userParams.itemByName('dbRadius').value
        offset = adsk.core.ValueInput.createByString('dbOffset')
        offset = adsk.core.ValueInput.createByReal(userParams.itemByName('dbHoleOffset').value)
        
        for occurrenceFace in self.selectedOccurrences.values():
            startTlMarker = self.design.timeline.markerPosition

            for faceId in occurrenceFace:
                face = self.selectedFaces[faceId][0]
                edges = self.selectedFaces[faceId][1]
                facePoint = self.selectedFaces[faceId][2]
    #            Holes created in Occurrences don't appear to work correctly 
    #            components created by mirroring will fail!! - they use the coordinate space of the original, but I haven't 
    #            figured out how to work around this.
    #            face in an assembly context needs to be treated differently to a face that is at rootComponent level
    #        
                if face.assemblyContext:
                   comp = face.assemblyContext.component
                   occ = face.assemblyContext  
                   entityName = occ.name.split(':')[-1]
    
                else:
                   comp = self.rootComp
                   occ = None
                   entityName = face.body.name
    
                
                if not face.isValid:
                   face = comp.findBRepUsingPoint(facePoint, adsk.fusion.BRepEntityTypes.BRepFaceEntityType).item(0)
    
                faceId = str(face.tempId) + ':' + entityName 
     
                sketch = adsk.fusion.Sketch.cast(comp.sketches.add(face, occ))  #used for fault finding
#                holes = adsk.fusion.HoleFeatures.cast(comp.features.holeFeatures)
#                sketch = adsk.fusion.Sketch.cast(sketch.createForAssemblyContext(occ))
    #            sketch.sketchPoints.add(facePoint)        #for debugging 
                
                faceNormal = dbUtils.getFaceNormal(face)
                                
                for edge in iter(edges):
    
                    if not face.isValid:
                        face = comp.findBRepUsingPoint(facePoint, adsk.fusion.BRepEntityTypes.BRepFaceEntityType ).item(0).createForAssemblyContext(occ)
#                        edge = edge.nativeObject
                        
                    if not edge.isValid:
                        continue # edges that have been processed already will not be valid any more - at the moment this is easier than removing the 
    #                    affected edge from self.edges after having been processed
                        
                    try:
                        if not dbUtils.isEdgeAssociatedWithFace(face, edge):
                            continue  # skip if edge is not associated with the face currently being processed
                    except:
                        pass
                    
                    startVertex = adsk.fusion.BRepVertex.cast(dbUtils.getVertexAtFace(face, edge))
#                    sketch.project(startVertex)
#                    startRef = adsk.fusion.SketchPoint.cast(sketch.project(startVertex))
                    corner = sketch.modelToSketchSpace(startVertex.nativeObject.geometry)
                    try:
                        (edge1, edge2) = dbUtils.getCornerEdgesAtFace(face, edge)
                    except: 
                        dbUtils.messageBox('Failed at findAdjacentFaceEdges:\n{}'.format(traceback.format_exc()))

                    occTransform = occ.transform                        
                        
                    edge1Vec = dbUtils.correctedEdgeVector(edge1.nativeObject, startVertex.nativeObject)
                    edge1Vec.normalize()
                    edge2Vec = dbUtils.correctedEdgeVector(edge2.nativeObject, startVertex.nativeObject)
                    edge2Vec.normalize()
                    
                    midVector = edge1Vec.copy()
                    midVector.add(edge2Vec)
                    midVector.normalize()
                    midVector.scaleBy(self.circVal/2*1.1)
                                        
                    endPoint = corner.copy()
                    endPoint.translateBy(midVector) 

                    midlineConstr1 = sketch.sketchCurves.sketchLines.addByTwoPoints(corner, endPoint)
                    midlineConstr1.isConstruction = True
                    midlineConstr1.isFixed = True
                    
                    midlineConstr1.startSketchPoint.isFixed = True
                    
                    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(midlineConstr1.endSketchPoint, self.circVal/2)  #as the centre is placed on midline endPoint, it automatically gets constrained
                    
                    lastProfile = sketch.profiles.count-1
                    profile = sketch.profiles.item(lastProfile)
                    
                    textPoint = midlineConstr1.endSketchPoint.geometry.copy()
                    
                    lineDim = sketch.sketchDimensions.addDistanceDimension(midlineConstr1.startSketchPoint,midlineConstr1.endSketchPoint, adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, textPoint)
                    lineDim.parameter.expression = "dbToolDia/2*1.1"  #the 1.1 factor should be a parameter
                    
                    extentToEntity = dbUtils.findExtent(face, edge)
                    endExtentDef = adsk.fusion.ToEntityExtentDefinition.create(extentToEntity, False)
                    startExtentDef = adsk.fusion.ProfilePlaneStartDefinition.create()
                    profile = profile.createForAssemblyContext(occ) if face.assemblyContext else profile
                    
                    
                    extrInput = adsk.fusion.ExtrudeFeatureInput.cast(None)
                    extrInput = comp.features.extrudeFeatures.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)
                    extrInput.creationOccurrence = occ
                    extrInput.participantBodies = [face.body]
                    extrInput.startExtent = startExtentDef
                    extrInput.setOneSideExtent(endExtentDef,adsk.fusion.FeatureOperations.CutFeatureOperation)
#                    comp.features.extrudeFeatures.add(extrInput)
                    
                    
                    #determine directions to translate the initGuess - needs to be inside the corner, not on the face
#                    for edgeFace in edge.faces:
##                        dirVect = dbUtils.getFaceNormal(edgeFace.nativeObject).copy()
#                        dirVect = dbUtils.getFaceNormal(edgeFace).copy()
#                        dirVect.normalize()
#                        dirVect.scaleBy(radius/math.sqrt(2))  #ideally radius should be linked to parameters, 
#                                                              # but hole start point still is the right quadrant
#                        initGuess.translateBy(dirVect)
                    #create hole attributes
#                    holeInput = holes.createSimpleInput(adsk.core.ValueInput.createByString('dbToolDia'))
#                    holeInput.tipAngle = adsk.core.ValueInput.createByString('180 deg')
#                    holeInput.isDefaultDirection = True
#                    holeInput.creationOccurrence = occ  #this parameter doesn't appear to work!!
##                    holeInput.participantBodies = [face.body.createForAssemblyContext(occ)] if face.assemblyContext else [face.body]
#                    holeInput.participantBodies = [face.body]
#                    holeInput.setPositionByPlaneAndOffsets(face, initGuess, edge1, offset, edge2, offset)
#                    holeInput.setOneSideToExtent(extentToEntity,True)
#                    try: 
##                        hole = holes.add(holeInput)
##                        hole = hole.createForAssemblyContext(occ) if face.assemblyContext else hole
#    #                    hole.participantBodies = [face.body.createForAssemblyContext(occ)] if face.assemblyContext else [face.body]
#                        adsk.doEvents()
#                        hole.name = 'dogbone'
    
#                    except Exception as e:
#                        self.errorCount += 1
#                        continue
            endTlMarker = self.design.timeline.markerPosition-1
            if endTlMarker - startTlMarker >0:
                timelineGroup = self.design.timeline.timelineGroups.add(startTlMarker,endTlMarker)
                timelineGroup.name = 'dogbone'
            adsk.doEvents()
        if self.errorCount >0:
            dbUtils.messageBox('Reported errors:{}\nYou may not need to do anything, \nbut check holes have been created'.format(self.errorCount))

                
                

dog = DogboneCommand()


def run(context):
    try:
        dog.addButton()
    except:
        dbUtils.messageBox(traceback.format_exc())


def stop(context):
    try:
        dog.removeButton()
    except:
        dbUtils.messageBox(traceback.format_exc())
