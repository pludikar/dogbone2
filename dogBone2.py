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

# to do:
# 1. Selection of multiple faces and selecting/deselecting target edges (intention is to use attributes to relate
#    edges to faces, probably collected during onFaceSelect events - that way the prepopulated entities don't have to be 
#    recalculated on every mouse move
# 2. ... who knows
 
from collections import defaultdict

import adsk.core, adsk.fusion
import math
import traceback
import uuid

import time
from . import utils as dbutils

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

        self.handlers = dbutils.HandlerHelper()

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

    def onChange(self, args:adsk.core.InputChangedEventArgs):
        
        changedInput = adsk.core.CommandInput.cast(args.input)
        if changedInput.id != 'select' and changedInput.id != 'edgeSelect':
            return
        if changedInput.id == 'select':
#            processing changes to face selections
            if len(self.selectedFaces) > changedInput.selectionCount:
                
                # a face has been removed
                newFaceList = self.selectedFaces.keys()
                faceOccurrenceId = changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext.name.split(':')[-1]
                selectionList = [str(changedInput.selection(i).entity.tempId) +':'+ faceOccurrenceId for i in range(changedInput.selectionCount)]
                missingFace = [select for select in newFaceList if select not in selectionList][0]
                edgeList = self.selectedFaces[missingFace][1]
                changedInput.commandInputs.itemById('edgeSelect').hasFocus = True
                del self.selectedFaces[missingFace]
                for edge in edgeList:
                    self.ui.activeSelections.removeByEntity(edge)
                changedInput.commandInputs.itemById('select').hasFocus = True
                return
             
#             Face has been added - assume that the last selection entity is the one added
            face = adsk.fusion.BRepFace.cast(changedInput.selection(changedInput.selectionCount -1).entity)
            changedInput.commandInputs.itemById('edgeSelect').isVisible = True  
            
            changedEntity = changedInput.selection(changedInput.selectionCount-1).entity
            if changedEntity.assemblyContext:
                activeOccurrenceName = changedEntity.assemblyContext.name
            else:
                activeOccurrenceName = 'root'
                
            if changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext:
                changedEntityName = changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext.name.split(':')[-1]
            else:
                changedEntityName = 'root'
            
            faceId = str(changedEntity.tempId) + ":" + changedEntityName
            faces = []
            faces = self.selectedOccurrences.get(activeOccurrenceName, faces)
            faces.append(faceId)
            self.selectedOccurrences[activeOccurrenceName] = faces
            self.selectedFaces[faceId] = [face, adsk.core.ObjectCollection.create()]
            
            faceNormal = dbutils.getFaceNormal(face)
            
            for edge in face.body.edges:
                if edge.isDegenerate:
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
                    if dbutils.getAngleBetweenFaces(edge) > math.pi:
                        continue
                    changedInput.commandInputs.itemById('edgeSelect').addSelection(edge)
                    self.selectedFaces[faceId][1].add(edge)
                    if edge.assemblyContext:
                        activeEdgeName = edge.assemblyContext.name.split(':')[-1]
                    else:
                        activeEdgeName = 'root'

                    edgeId = str(edge.tempId)+':'+ activeEdgeName
                    self.selectedEdges[edgeId] = faceId
                except:
                    dbutils.messageBox('Failed at edge:\n{}'.format(traceback.format_exc()))
                 #end of processing faces
        #proceesing changed edge selection            
        if changedInput.id != 'edgeSelect':
            return
        if len(self.selectedEdges) > changedInput.selectionCount:
            # an edge has been removed
        # only need to do something if there are no edges left associated with a face
         #have to work backwards edge to faceId, then remove face from selection if associated edges == 0
        # This is complicated because all selected edges are mixed together, you can't simply find the edges that are associated
#            oldEdgeList = self.selectedEdges.keys()
#            edgeOccurrenceId = changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext.name.split(':')[-1]
            try:
                occurrenceNumber = ':' + changedInput.selection(changedInput.selectionCount-1).entity.assemblyContext.name.split(':')[-1]
            except OverflowError:
                changedInput.isVisible = False
                changedInput.commandInputs.itemById('select').hasFocus = True
                self.selectedFaces.clear
                self.ui.activeSelections.clear()
                return

            calcEdgeId = lambda x: str(x.tempId) + occurrenceNumber
            lookupEdge = lambda x: self.selectedEdges[x]
#            newselectedList = [str(changedInput.selection(i).entity.tempId) +':'+ edgeOccurrenceId for i in range(changedInput.selectionCount)]
            changedSelectionList = [changedInput.selection(i).entity for i in range(changedInput.selectionCount)]
            changedEdgeIdList = map(calcEdgeId, changedSelectionList)
            changedEdge_FaceIdList = map(lookupEdge, changedEdgeIdList)
            consolidatedFaceList = set(changedEdge_FaceIdList)
            try:
                missingFace = [face for face in self.selectedFaces.keys() if face not in consolidatedFaceList]
            except Exception as e:
                changedInput.commandInputs.itemById('select').hasFocus = True
                self.ui.activeSelections.removeByEntity(self.selectedFaces[0])
                changedInput.commandInputs.itemById('edgeSelect').hasFocus = True
                return
        if not len(missingFace):
            return
        changedInput.commandInputs.itemById('select').hasFocus = True
        self.ui.activeSelections.removeByEntity(self.selectedFaces[missingFace[0]][0])
        changedInput.commandInputs.itemById('edgeSelect').hasFocus = True
        del self.selectedFaces[missingFace[0]]    
        return
      
#            eventArgs.additionalEntities = faceEdges
        
            
        #placeholder for future
           
    def refreshSelections(self, commandInput):
        cmdIn = adsk.core.SelectionCommandInput.cast(commandInput)
        cmdIn.clearSelection
        for selection in self.selections:
            cmdIn.addSelection(selection)
            
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
            dbutils.messageBox("Benchmark: {:.02f} sec processing {} edges".format(
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
                    
    def onFaceSelect(self, args):
        eventArgs = adsk.core.SelectionEventArgs.cast(args)
        # Check which selection input the event is firing for.
        activeIn = eventArgs.firingEvent.activeInput
        if activeIn.id != 'select' and activeIn.id != 'edgeSelect':
            return
        if activeIn.id == 'select':

            activeOccurrence = eventArgs.selection.entity.assemblyContext

            if eventArgs.selection.entity.assemblyContext:
                activeOccurrenceName = activeOccurrence.name
                activeComponent = activeOccurrence.component
            else:
                activeOccurrenceName = 'root'

            if activeOccurrenceName not in self.selectedOccurrences:
                if not activeOccurrence:
                    eventArgs.isSelectable = True
                    return
                if not self.selectedOccurrences: #check if its a rootComponent
                    eventArgs.isSelectable = True
                    return
                    
                #at this point only need to check for duplicate component selection - Only one component allowed, to save on conflict checking
                selectedFaceList = self.selectedOccurrences.values()
                sel = []
                for selFace in selectedFaceList:
                    sel.append(selFace[0])
                    selComp = self.selectedFaces[selFace[0]][0].assemblyContext.component
                    if selComp != activeComponent:
                        eventArgs.isSelectable = True
                        return
                eventArgs.isSelectable = False
                        
                    
#                    selectedFaces = [face[0].assemblyContext.component for face in selectedFaceList]   
                if activeOccurrence.component != eventArgs.selection.entity.assemblyContext.component:
                    eventArgs.isSelectable = True
                    return
                
                eventArgs.isSelectable = False
                return
                
            if eventArgs.selection.entity.assemblyContext:
                entityName = eventArgs.selection.entity.assemblyContext.name.split(':')[-1]
            else:
                entityName = 'root'

            faceId = str(eventArgs.selection.entity.tempId)+":"+ entityName

            textResult = activeIn.parentCommand.commandInputs.itemById('TextBox') #Debugging
            textResult.text = 'faceId: ' + str(faceId)+':'+str(eventArgs.isSelectable) #Debugging

            
            primaryFaceId = self.selectedOccurrences[activeOccurrenceName]
            primaryFace = self.selectedFaces[primaryFaceId[0]][0] #get actual BrepFace from its ID
            primaryFaceNormal = dbutils.getFaceNormal(primaryFace)
            if primaryFaceNormal.isParallelTo(dbutils.getFaceNormal(eventArgs.selection.entity)):
                eventArgs.isSelectable = True
#                textResult.text = 'faceId: ' + str(faceId)+':'+str(eventArgs.isSelectable)  #Debugging
                return
            eventArgs.isSelectable = False
#            textResult.text = 'faceId: ' + str(faceId)+':'+str(eventArgs.isSelectable)   #Debugging
#        selecting faces
            return
            
        else:
#            processing edges associated with face
            selected = eventArgs.selection
            currentEdge = adsk.fusion.BRepEdge.cast(selected.entity)
            
            activeOccurrence = eventArgs.selection.entity.assemblyContext
            if eventArgs.selection.entity.assemblyContext:
                activeOccurrenceName = activeOccurrence.name
            else:
                activeOccurrenceName = 'root' 
            
            primaryFaceId = self.selectedOccurrences[activeOccurrenceName]
            primaryFace = self.selectedFaces[primaryFaceId[0]][0] #get actual BrepFace from its ID
            primaryFaceNormal = dbutils.getFaceNormal(primaryFace)
            
            edgeVector = currentEdge.startVertex.geometry.vectorTo(currentEdge.endVertex.geometry)
            
            if not edgeVector.isParallelTo(primaryFaceNormal):
                eventArgs.isSelectable = False
                return
            eventArgs.isSelectable = True            
            return
            
        
        selected = eventArgs.selection
        selectedEntity = selected.entity
#        faceEdges = adsk.core.ObjectCollection.create()

#        if selectedEntity.objectType != adsk.fusion.BRepFace.classType():
#            eventArgs.activeInput.clearSelectionFilter()
#            eventArgs.activeInput.addSelectionFilter('Faces')
#
#            return
#        
#        eventArgs.activeInput.addSelectionFilter('LinearEdges')
#        face = adsk.fusion.BRepFace.cast(selectedEntity)
#        faceNormal = dbutils.getFaceNormal(face)
#            
#        faceId = face.tempId
#        
#        faceEdges = self.faceAssociations.get(face.tempId, adsk.core.ObjectCollection.create())
#            
#        if faceEdges.count >0:
#        # if faceAttributes exist then only need to get the associated edges
#        # this eliminates the need to do costly recalculation of edges each time mouse is moved
#            eventArgs.additionalEntities = faceEdges
#            return
#            
#        for edge in face.body.edges:
#            if edge.isDegenerate:
#                continue
#            try:
#                if edge.geometry.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
#                    continue
#                vector = edge.startVertex.geometry.vectorTo(edge.endVertex.geometry)
#                if vector.isPerpendicularTo(faceNormal):
#                    continue
#                if edge.faces.item(0).geometry.objectType != adsk.core.Plane.classType():
#                    continue
#                if edge.faces.item(1).geometry.objectType != adsk.core.Plane.classType():
#                    continue              
#                if edge.startVertex not in face.vertices:
#                    if edge.endVertex not in face.vertices:
#                        continue
#                    else:
#                        vector = edge.endVertex.geometry.vectorTo(edge.startVertex.geometry)
#                if vector.dotProduct(faceNormal) >= 0:
#                    continue
#                if dbutils.getAngleBetweenFaces(edge) > math.pi:
#                    continue
#                faceEdges.add(edge)
#            except:
#                dbutils.messageBox('Failed at edge:\n{}'.format(traceback.format_exc()))
#        self.faceAssociations[faceId] = faceEdges
#        eventArgs.additionalEntities = faceEdges
    

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

        if not userParams.itemByName('dbToolDia'):
            dValIn = adsk.core.ValueInput.createByString(self.circStr)
            dParameter = userParams.add('dbToolDia',dValIn, self.design.unitsManager.defaultLengthUnits, '')
            dParameter.isFavorite = True
        if not userParams.itemByName('dbRadius'):
            rValIn = adsk.core.ValueInput.createByString('dbToolDia/2 + ' + self.offStr)
            rParameter = userParams.add('dbRadius',rValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
        if not userParams.itemByName('dbOffset'):
            oValIn = adsk.core.ValueInput.createByString('dbRadius / sqrt(2)')
            oParameter = userParams.add('dbOffset', oValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')

        radius = userParams.itemByName('dbRadius').value
        offset = adsk.core.ValueInput.createByString('dbOffset')
        startTlMarker = self.design.timeline.markerPosition

        for face in self.faces:
#            Holes created in Occurrences don't appear to work correctly 
#            components created by mirroring will fail!! - they use the coordinate space of the original, but I haven't 
#            figured out how to work around this.
#            face in an assembly context needs to be treated differently to a face that is at rootComponent level
#        
#        This work around is limited to relatively simple models!!!
            if face.assemblyContext:
               comp = face.assemblyContext.component
#               name = face.assemblyContext.name.split(':')[0]+':1'  #occurrence is supposed to take care of positioning
               occ = face.assemblyContext  # this is a work around - use 1st occurrence as proxy
               face = face.nativeObject
#               lightState = occ.isLightBulbOn
#               occ.isLightBulbOn = True

            else:
               comp = self.rootComp
               occ = None

#            sketch = comp.sketches.add(comp.xYConstructionPlane, occ)  #used for fault finding
            holes = adsk.fusion.HoleFeatures.cast(comp.features.holeFeatures)
                
            dbutils.clearFaceAttribs(self.design)
            dbutils.setFaceAttrib(face)
                
            faceNormal = dbutils.getFaceNormal(face)
            
            for edge in self.edges:
                #face becomes invalid after a hole is added - use attributes to find the right face
                if not face.isValid:
                    face = dbutils.refreshFace(self.design)
                if edge.assemblyContext:
                    #put face and edge into right context (1st component) - create proxies
                    edge = edge.nativeObject
#                    face = face.nativeObject
                    
                startVertex = dbutils.getVertexAtFace(face, edge)
                if not dbutils.isEdgeAssociatedWithFace(face, edge):
                    continue
                extentToEntity = dbutils.defineExtent(face, edge)
                try:
                    (edge1, edge2) = dbutils.getCornerEdgesAtFace(face, edge)
                except: 
                    dbutils.messageBox('Failed at findAdjecentFaceEdges:\n{}'.format(traceback.format_exc()))

                initGuess = startVertex.geometry.copy()
                #determine directions to translate the initGuess - needs to be inside the corner, not on the face
                for edgeFace in edge.faces:
                    dirVect = dbutils.getFaceNormal(edgeFace).copy()
                    dirVect.normalize()
                    dirVect.scaleBy(radius/math.sqrt(2))  #ideally radius should be linked to parameters, 
                                                          # but hole start point still is the right quadrant
                    initGuess.translateBy(dirVect)
#                sketch.sketchPoints.add(initGuess)        #for debugging 

                #create hole attributes
                holeInput = holes.createSimpleInput(adsk.core.ValueInput.createByString('dbToolDia'))
                holeInput.tipAngle = adsk.core.ValueInput.createByString('180 deg')
                holeInput.isDefaultDirection = True
                holeInput.creationOccurrence = face.assemblyContext  #this parameter doesn't appear to work!!
                holeInput.participantBodies = [face.body]
                holeInput.setPositionByPlaneAndOffsets(face, initGuess, edge1, offset, edge2, offset)
                holeInput.setOneSideToExtent(extentToEntity,False)
                try: 
                    hole = holes.add(holeInput)
                    hole = hole.createForAssemblyContext(occ)
                    adsk.doEvents()
                    hole.name = 'dogbone'

                except:
                    self.errorCount += 1
                    continue
#            occ.isLightBulbOn = lightState
            endTlMarker = self.design.timeline.markerPosition-1
            if endTlMarker - startTlMarker >0:
                timelineGroup = self.design.timeline.timelineGroups.add(startTlMarker,endTlMarker)
                timelineGroup.name = 'dogbone'
            adsk.doEvents()
            if self.errorCount >0:
                dbutils.messageBox('reported errors:{}'.format(self.errorCount))
                
                

dog = DogboneCommand()


def run(context):
    try:
        dog.addButton()
    except:
        dbutils.messageBox(traceback.format_exc())


def stop(context):
    try:
        dog.removeButton()
    except:
        dbutils.messageBox(traceback.format_exc())
