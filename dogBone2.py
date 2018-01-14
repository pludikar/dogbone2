#Author-Peter Ludikar
#Description-An Add-In for making dog-bone fillets.

# This version is a proof of concept 

# I've completely revamped the dogbone add-in by Casey Rogers and Patrick Rainsberry and David Liu
# some of the original utilities have remained, but mostly everything else has changed.

# The original add-in was based on creating points and extruding - I found using sketches and extrusion to be very heavy 
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

faceAssociations = {}


class DogboneCommand(object):
    COMMAND_ID = "dogboneBtn"

    def __init__(self):
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface

        self.offStr = "0"
        self.offVal = None
        self.circStr = "0.25 in"
        self.circVal = None
        self.edges = []
        self.benchmark = False

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
        argsCmd = adsk.core.Command.cast(args)

        inputs = inputs.command.commandInputs

        selInput0 = inputs.addSelectionInput(
            'select', 'Face',
            'Select a face to apply dogbones to all internal corner edges')
#        selInput0.addSelectionFilter('LinearEdges')
        selInput0.addSelectionFilter('Faces')
        selInput0.setSelectionLimits(1,0)

        inp = inputs.addValueInput(
            'circDiameter', 'Tool Diameter', self.design.unitsManager.defaultLengthUnits,
            adsk.core.ValueInput.createByString(self.circStr))
        inp.tooltip = "Size of the tool with which you'll cut the dogbone."

        inp = inputs.addValueInput(
            'offset', 'Additional Offset', self.design.unitsManager.defaultLengthUnits,
            adsk.core.ValueInput.createByString(self.offStr))
        inp.tooltip = "Additional increase to the radius of the dogbone."

        inputs.addBoolValueInput("benchmark", "Benchmark running time", True, "", self.benchmark)

        # Add handlers to this command.
        args.command.execute.add(self.handlers.make_handler(adsk.core.CommandEventHandler, self.onExecute))
        args.command.selectionEvent.add(self.handlers.make_handler(adsk.core.SelectionEventHandler, self.onFaceSelect))
        args.command.validateInputs.add(
            self.handlers.make_handler(adsk.core.ValidateInputsEventHandler, self.onValidate))
            
    def parseInputs(self, inputs):
        inputs = {inp.id: inp for inp in inputs}

        self.circStr = inputs['circDiameter'].expression
        self.circVal = inputs['circDiameter'].value
        self.offStr = inputs['offset'].expression
        self.offVal = inputs['offset'].value
        self.benchmark = inputs['benchmark'].value

        self.edges = []
        self.faces = []
        
        for i in range(inputs['select'].selectionCount):
            entity = inputs['select'].selection(i).entity
            if entity.objectType == adsk.fusion.BRepEdge.classType():
                self.edges.append(entity)
            elif entity.objectType == adsk.fusion.BRepFace.classType():
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
        if activeIn.id != 'select':
            return
        selected = eventArgs.selection
        selectedEntity = selected.entity
        faceEdges = adsk.core.ObjectCollection.create()

        if selectedEntity.objectType != adsk.fusion.BRepFace.classType():
            eventArgs.activeInput.clearSelectionFilter()
            eventArgs.activeInput.addSelectionFilter('Faces')

            return
        
        eventArgs.activeInput.addSelectionFilter('LinearEdges')
        face = adsk.fusion.BRepFace.cast(selectedEntity)
        faceNormal = dbutils.getFaceNormal(face)
        
        if not face.attributes.itemByName(DOGBONEGROUP, ID):
            faceId = uuid.uuid1()
            face.attributes.add(DOGBONEGROUP, ID, str(faceId))
            
        faceId = face.attributes.itemByName(DOGBONEGROUP, ID).value
        
        if not face.body.attributes.itemByName(DOGBONEGROUP, REV_ID):
            face.body.attributes.add(DOGBONEGROUP, REV_ID, str(face.body.revisionId))

        if face.body.revisionId != face.body.attributes.itemByName(DOGBONEGROUP, REV_ID).value:
#            if the body revisionID has changed - we can't be sure the attributes are correct 
#            - so we have to start over - once design is stable, we might need to improve this 
#               if the performance is poor
            return
        faceEdges = faceAssociations.get(face.attributes.itemByName(DOGBONEGROUP, ID).value, adsk.core.ObjectCollection.create())
            
        if faceEdges.count >0:
        # if faceAttributes exist then only need to get the associated edges
            eventArgs.additionalEntities = faceEdges
            return
            
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
                faceEdges.add(edge)
                edge.attributes.add(DOGBONEGROUP,faceId, '')
            except:
                dbutils.messageBox('Failed at edge:\n{}'.format(traceback.format_exc()))
        faceAssociations[faceId] = faceEdges
        eventArgs.additionalEntities = faceEdges
    

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
#            face in an assembly context needs to be treated differently to a face that is at rootComponent level
            if face.assemblyContext:
               comp = face.assemblyContext.sourceComponent
               name = face.assemblyContext.name.split(':')[0]+':1'  #occurrence is supposed to take care of positioning
               occ = self.rootComp.occurrences.itemByName(name)  # this is a work around - use 1st occurrence as proxy
               face = face.nativeObject.createForAssemblyContext(occ)

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
                    edge = edge.nativeObject.createForAssemblyContext(occ)
                    face = face.nativeObject.createForAssemblyContext(occ)
                    
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
                    dirVect.scaleBy(radius/math.sqrt(2))
                    initGuess.translateBy(dirVect)
#                sketch.sketchPoints.add(initGuess)        #for debugging 

                #create hole attributes
                holeInput = holes.createSimpleInput(adsk.core.ValueInput.createByString('dbToolDia'))
                holeInput.tipAngle = adsk.core.ValueInput.createByString('180 deg')
                holeInput.isDefaultDirection = True
                holeInput.creationOccurrence = face.assemblyContext
                holeInput.participantBodies = [face.body]
                holeInput.setPositionByPlaneAndOffsets(face, initGuess, edge1, offset, edge2, offset)
                holeInput.setOneSideToExtent(extentToEntity,False)
                try: 
                    hole = holes.add(holeInput)
                    hole.name = 'dogbone'

                except:
                    dbutils.messageBox('Failed at create hole add:\n{}'.format(traceback.format_exc()))
                    continue
            endTlMarker = self.design.timeline.markerPosition-1
            if endTlMarker - startTlMarker >0:
                timelineGroup = self.design.timeline.timelineGroups.add(startTlMarker,endTlMarker)
                timelineGroup.name = 'dogbone'
                
                

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
