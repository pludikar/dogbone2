import logging
import os, sys
import adsk.core, adsk.fusion
from typing import List

from math import sqrt, pi
import json
import time

from ..common import dbutils as util
from ..common import common as g 
from ..common.decorators import eventHandler, HandlerCollection

from ..dbClasses import dataclasses as dc, dbEdge, dbFace
from ..dbClasses.register import Register

from ..dbClasses.dbController import DbController
from ..dbClasses.staticDogbones import createStaticDogbones

makeNative = lambda x: x.nativeObject if x.nativeObject else x
reValidateFace = lambda comp, x: comp.findBRepUsingPoint(x, adsk.fusion.BRepEntityTypes.BRepFaceEntityType,-1.0 ,False ).item(0)
faceSelections = lambda selectionObjects: list(filter(lambda face: face.objectType == adsk.fusion.BRepFace.classType(), selectionObjects))
edgeSelections = lambda selectionObjects: list(filter(lambda edge: edge.objectType == adsk.fusion.BRepEdge.classType(), selectionObjects))

logger = logging.getLogger('dogbone.command')

class DogboneCommand(object):
    
    register = Register()
    controller = DbController()
    _customFeatureDef: adsk.fusion.CustomFeatureDefinition

    def __init__(self):
        
        logger.info('dogbone.command')

        self.dbParams = dc.DbParams()
        self.faceSelections = adsk.core.ObjectCollection.create()
        self.offsetStr = "0"
        self.toolDiaStr = str(self.dbParams.toolDia) + " in"
        self.edges = []
        self.benchmark = False
        self.errorCount = 0

        self.addingEdges = 0
        self.logging = logging.DEBUG
        # {'Notset':0,'Debug':10,'Info':20,'Warning':30,'Error':40}

        self.expandModeGroup = True
        self.expandSettingsGroup = False
        self.levels = {}



        self.registeredEntities = adsk.core.ObjectCollection.create()
        
    def __del__(self):
        HandlerCollection.remove()  #clear event handers

    def writeDefaults(self):
        logger.info('config file write')

        json_file = open(os.path.join(g._appPath, 'defaults.dat'), 'w', encoding='UTF-8')
        json.dump(self.dbParams.dict(), json_file, ensure_ascii = False)
        json_file.close()
    
    def readDefaults(self): 
        logger.info('config file read')
        if not os.path.isfile(os.path.join(g._appPath, 'defaults.dat')):
            return
        json_file = open(os.path.join(g._appPath, 'defaults.dat'), 'r', encoding='UTF-8')
        try:
            resultStr = json.load(json_file)
            self.dbParams= dc.DbParams(**resultStr)
        except ValueError:
            logger.error('default.dat error')
            json_file.close()
            json_file = open(os.path.join(g._appPath, 'defaults.dat'), 'w', encoding='UTF-8')
            json.dump(self.dbParams.dict(), json_file, ensure_ascii = False)
            return

        json_file.close()
            
    def debugFace(self, face):
        if logger.level < logging.DEBUG:
            return
        for edge in face.edges:
            logger.debug(f'edge {edge.tempId};'\
                        'startVertex: {edge.startVertex.geometry.asArray()};'\
                        ' endVertex: {edge.endVertex.geometry.asArray()}')

        return

    def addButtons(self):
        # clean up any crashed instances of the button if existing
        try:
            self.removeButtons()
        except:
            return -1
        
        # add add-in to UI
        buttonDogbone = g._ui.commandDefinitions.addButtonDefinition(
                    g.COMMAND_ID,
                    'Dogbone',
                    'Creates dogbones at all inside corners of a face',
                    'Resources')

        buttonDogboneEdit = g._ui.commandDefinitions.addButtonDefinition(
                    g.EDIT_ID,
                    'Edit Dogbone',
                    'Edits dogbones',
                    '')

        
        createPanel = g._ui.allToolbarPanels.itemById('SolidCreatePanel')
        separatorControl = createPanel.controls.addSeparator()
        dropDownControl = createPanel.controls.addDropDown(
                    'Dogbone',
                    'Resources',
                    'dbDropDown',
                    separatorControl.id )

        buttonControl = dropDownControl.controls.addCommand(
                    buttonDogbone,
                    'dogboneBtn',
                    False)
        editButtonControl = dropDownControl.controls.addCommand(
                    buttonDogboneEdit,
                    'dogboneEditBtn',
                    False)

        # Make the button available in the panel.
        buttonControl.isPromotedByDefault = True
        buttonControl.isPromoted = True

        self._customFeatureDef = adsk.fusion.CustomFeatureDefinition.create(
                    g.FEATURE_ID,
                    'dogbone feature',
                    'Resources')
        self._customFeatureDef.editCommandId = g.EDIT_ID

        #attach event handlers

        self.onCreate(event = buttonDogbone.commandCreated)

        self.onEditCreate(event = buttonDogboneEdit.commandCreated)
        
        self.computeDogbones(event = self._customFeatureDef.customFeatureCompute)
        logger.debug(f'{HandlerCollection.str__()}')


    def removeButtons(self):
#        cleans up buttons and command definitions left over from previous instantiations
        cmdDef = g._ui.commandDefinitions.itemById(g.COMMAND_ID)
        cmdEditDef = g._ui.commandDefinitions.itemById(g.EDIT_ID)
        createPanel = g._ui.allToolbarPanels.itemById('SolidCreatePanel')
        dbDropDowncntrl = createPanel.controls.itemById('dbDropDown')
        if dbDropDowncntrl:
            dbButtoncntrl = dbDropDowncntrl.controls.itemById(g.COMMAND_ID)
            dbEditButtoncntrl = dbDropDowncntrl.controls.itemById(g.EDIT_ID)
            if dbButtoncntrl:
                dbButtoncntrl.isPromoted = False
                dbButtoncntrl.deleteMe()
            if dbEditButtoncntrl:
                dbEditButtoncntrl.isPromoted = False
                dbEditButtoncntrl.deleteMe()
            dbDropDowncntrl.deleteMe()
        if cmdDef:
            cmdDef.deleteMe()
        if cmdEditDef:
            cmdEditDef.deleteMe()

    @eventHandler(handler_cls = adsk.core.CommandCreatedEventHandler)
    def onCreate(self, inputs:adsk.core.CommandCreatedEventArgs):
        """
        important persistent variables:        
        self.selectedOccurrences  - Lookup dictionary 
        key: activeOccurrenceName 
        value: list of selectedFaces
            provides a quick lookup relationship between each occurrence and in particular which faces have been selected.  
            The 1st selected face in the list is always the primary face
        
        self.selectedFaces - Lookup dictionary 
        key: faceId = str(face tempId:occurrenceNumber) 
        value: [BrepFace, objectCollection of edges, reference point on nativeObject Face]
            provides fast method of getting Brep entities associated with a faceId

        self.selectedEdges - reverse lookup 
        key: edgeId = str(edgeId:occurrenceNumber) 
        value: str(face tempId:occurrenceNumber)
            provides fast method of finding face that owns an edge
        """
        
        logger.info("============================================================================================")
        logger.info("-----------------------------------dogbone started------------------------------------------")
        logger.info("============================================================================================")
            
        self.faces = []
        self.errorCount = 0
        self.faceSelections.clear()
        
        self.workspace = g._ui.activeWorkspace

        self.NORMAL_ID = 'dogboneNormalId'
        self.MINIMAL_ID = 'dogboneMinimalId'
                
        if g._design.designType != adsk.fusion.DesignTypes.ParametricDesignType :
            returnValue = g._ui.messageBox('DogBone only works in Parametric Mode \n Do you want to change modes?',
                                             'Change to Parametric mode',
                                             adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                                             adsk.core.MessageBoxIconTypes.WarningIconType)
            if returnValue != adsk.core.DialogResults.DialogYes:
                return
            g._design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        self.readDefaults()

        inputs :adsk.core.CommandInputs = inputs.command.commandInputs
        
        selInput0 = inputs.addSelectionInput(
                    'select',
                    'Face',
                    'Select a face to apply dogbones to all internal corner edges')
        selInput0.tooltip =\
            'Select a face to apply dogbones to all internal corner edges\n'\
            '*** Select faces by clicking on them. DO NOT DRAG SELECT! ***' 

        selInput0.addSelectionFilter('PlanarFaces')
        selInput0.setSelectionLimits(1,0)
        
        selInput1 = inputs.addSelectionInput(
                    'edgeSelect',
                    'DogBone Edges',
                    'Select or de-select any internal edges dropping down from a selected face (to apply dogbones to')

        selInput1.tooltip ='Select or de-select any internal edges dropping down from a selected face (to apply dogbones to)' 
        selInput1.addSelectionFilter('LinearEdges')
        selInput1.setSelectionLimits(1,0)
        selInput1.isVisible = False
                
        inp = inputs.addValueInput(
                    'toolDia',
                    'Tool Diameter               ',
                    g._design.unitsManager.defaultLengthUnits,
                    adsk.core.ValueInput.createByString(self.toolDiaStr))
        inp.tooltip = "Size of the tool with which you'll cut the dogbone."
        
        offsetInp = inputs.addValueInput(
                    'toolDiaOffset',
                    'Tool diameter offset',
                    g._design.unitsManager.defaultLengthUnits,
                    adsk.core.ValueInput.createByString(self.offsetStr))
        offsetInp.tooltip = "Increases the tool diameter"
        offsetInp.tooltipDescription = "Use this to create an oversized dogbone.\n"\
                                        "Normally set to 0.  \n"\
                                        "A value of .010 would increase the dogbone diameter by .010 \n"\
                                        "Used when you want to keep the tool diameter and oversize value separate"
        
        modeGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput('modeGroup', 'Mode')
        modeGroup.isExpanded = self.expandModeGroup
        modeGroupChildInputs = modeGroup.children
        
        typeRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs\
                .addButtonRowCommandInput(
                    'dogboneType',
                    'Type',
                    False)
        typeRowInput.listItems.add(
                    'Normal Dogbone',
                    self.dbParams.dbType == 'Normal Dogbone',
                    'resources/normal' )
        typeRowInput.listItems.add(
                    'Minimal Dogbone',
                    self.dbParams.dbType == 'Minimal Dogbone',
                    'resources/minimal' )
        typeRowInput.listItems.add(
                    'Mortise Dogbone',
                    self.dbParams.dbType == 'Mortise Dogbone',
                    'resources/hidden' )
        typeRowInput.tooltipDescription =\
                    "Minimal dogbones creates visually less prominent dogbones, but results in an interference fit " \
                    "that, for example, will require a larger force to insert a tenon into a mortise.\n" \
                    "\n"\
                    "Mortise dogbones create dogbones on the shortest sides, or the longest sides.\n" \
                    "A piece with a tenon can be used to hide them if they're not cut all the way through the workpiece."
        
        mortiseRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs\
                .addButtonRowCommandInput(
                    'mortiseType',
                    'Mortise Type',
                    False)
        mortiseRowInput.listItems.add(
                    'On Long Side',
                    self.dbParams.longSide,
                    'resources/hidden/longside' )
        mortiseRowInput.listItems.add(
                    'On Short Side',
                    not self.dbParams.longSide,
                    'resources/hidden/shortside' )
        mortiseRowInput.tooltipDescription = "Along Longest will have the dogbones cut into the longer sides." \
                                             "\nAlong Shortest will have the dogbones cut into the shorter sides."
        mortiseRowInput.isVisible = self.dbParams.dbType == 'Mortise Dogbone'

        minPercentInp = modeGroupChildInputs.addValueInput(
                    'minimalPercent',
                    'Percentage Reduction',
                    '',
                    adsk.core.ValueInput.createByReal(self.dbParams.minimalPercent))
        minPercentInp.tooltip = "Percentage of tool radius added to dogBone offset."
        minPercentInp.tooltipDescription =\
             "This should typically be left at 10%, but if the fit is too tight, it should be reduced"
        minPercentInp.isVisible = self.dbParams.dbType == 'Minimal Dogbone'

        depthRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs\
                .addButtonRowCommandInput(
                    'depthExtent',
                    'Depth Extent',
                    False)
        depthRowInput.listItems.add(
                    'From Selected Face',
                    not self.dbParams.fromTop,
                    'resources/fromFace' )
        depthRowInput.listItems.add(
                    'From Top Face',
                    self.dbParams.fromTop,
                    'resources/fromTop' )
        depthRowInput.tooltipDescription =\
             "When \"From Top Face\" is selected, all dogbones will be extended to the top most face\n"\
            "\nThis is typically chosen when you don't want to, or can't do, double sided machining."
 
        settingGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput(
                    'settingsGroup',
                    'Settings')
        settingGroup.isExpanded = self.expandSettingsGroup
        settingGroupChildInputs = settingGroup.children

        occurrenceTable: adsk.core.TableCommandInput = inputs.addTableCommandInput(
                    'occTable',
                    'OccurrenceTable',
                    2,
                    "1:1")
        occurrenceTable.isFullWidth = True

        rowCount = 0
        if not self.register.registeredFacesAsList():
            for faceObject in self.register.registeredFacesAsList():
                occurrenceTable.addCommandInput(
                    inputs.addImageCommandInput(
                        f"row{rowCount}", 
                        faceObject.component_hash, 
                        'resources/tableBody/16x16-normal.png'),
                        rowCount,
                        0)
                occurrenceTable.addCommandInput(
                    inputs.addTextBoxCommandInput(
                        f"row{rowCount}Name",
                        "          ",
                        faceObject.face.body.name,
                        1,
                        True),
                        rowCount,
                        1)
                rowCount+=1


        benchMark = settingGroupChildInputs.addBoolValueInput(
                    "benchmark",
                    "Benchmark time",
                    True,
                    "",
                    self.benchmark)
        benchMark.tooltip = "Enables benchmarking"
        benchMark.tooltipDescription = "When enabled, shows overall time taken to process all selected dogbones."

        logDropDownInp: adsk.core.DropDownCommandInput = settingGroupChildInputs.addDropDownCommandInput(
                    "logging",
                    "Logging level",
                    adsk.core.DropDownStyles.TextListDropDownStyle)
        logDropDownInp.tooltip = "Enables logging"
        logDropDownInp.tooltipDescription = "Creates a dogbone.log file. \n" \
                     "Location: " +  os.path.join(g._appPath, 'dogBone.log')

        logDropDownInp.listItems.add('Notset',
                                     self.logging == 0)
        logDropDownInp.listItems.add('Debug',
                                     self.logging == 10)
        logDropDownInp.listItems.add('Info',
                                     self.logging == 20)

        cmd:adsk.core.Command = inputs.command

        # Add handlers to this command.
        self.onExecute(event = cmd.execute)
        self.onPreSelect(event = cmd.preSelect)
        self.onValidate(event = cmd.validateInputs)
        self.onChange(event = cmd.inputChanged)
        self.setSelections(inputs, selInput0 )
        logger.debug(f'{HandlerCollection.str__()}')


    @eventHandler(handler_cls = adsk.core.CommandCreatedEventHandler)
    def onEditCreate(self, inputs:adsk.core.CommandCreatedEventArgs):
        logger.debug('onEditCreate')
        cmd:adsk.core.Command = inputs.command

        # Add handlers to this command.
        self.onEditExecute(event = cmd.execute)
        self.onEditActivate(event = cmd.activate)
        self.onPreSelect(event = cmd.preSelect)
        self.onChange(event = cmd.inputChanged)
        self.onExecutePreview(event = cmd.executePreview)
        self.onValidateInputs(event = cmd.validateInputs)
        logger.debug(f'{HandlerCollection.str__()}')
        pass

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onEditActivate(self, inputs:adsk.core.CommandEventArgs):
        logger.debug('onEditActivate')
        pass

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onEditExecute(self, inputs:adsk.core.CommandEventArgs):
        logger.debug('onEditActivate')
        pass

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onEdit(self, args:adsk.core.CommandEventArgs):
        logger.debug('onEdit')
        pass
            
    def setSelections(self, commandInputs:adsk.core.CommandInputs = None, activeCommandInput:adsk.core.CommandInput = None): #updates the selected entities on the UI
        collection = adsk.core.ObjectCollection.create()
        g._ui.activeSelections.clear()
        
        
        faceObjects = self.register.selectedFacesAsList()
        edgeObjects = self.register.selectedEdgesAsList()

        commandInputs.itemById('select').hasFocus = True        
        for faceObject in faceObjects:
            collection.add(faceObject.entity)
            
        g._ui.activeSelections.all = collection
        
        commandInputs.itemById('edgeSelect').isVisible = True
    
        commandInputs.itemById('edgeSelect').hasFocus = True        
        
        for edgeObject in edgeObjects:
            collection.add(edgeObject.entity)
            
        g._ui.activeSelections.all = collection
        
        activeCommandInput.hasFocus = True

    #==============================================================================
    #  routine to process any changed selections
    #  this is where selection and deselection management takes place
    #  also where eligible edges are determined
    #==============================================================================
    @eventHandler(handler_cls = adsk.core.InputChangedEventHandler)
    def onChange(self, args:adsk.core.InputChangedEventArgs):
        changedInput: adsk.core.CommandInput = args.input

        if changedInput.id == 'dogboneType':
            changedInput.commandInputs.itemById('minimalPercent').isVisible = \
                (changedInput.commandInputs.itemById('dogboneType').selectedItem.name == 'Minimal Dogbone')
            changedInput.commandInputs.itemById('mortiseType').isVisible = \
                (changedInput.commandInputs.itemById('dogboneType').selectedItem.name == 'Mortise Dogbone')
       

        if changedInput.id != 'select' and changedInput.id != 'edgeSelect':
            return
            
        activeSelections = g._ui.activeSelections.all #save active selections - selections are sensitive and fragile, any processing beyond just reading on live selections will destroy selection 

        logger.debug(f'input changed- {changedInput.id}')
        faces = faceSelections(activeSelections)
        edges = edgeSelections(activeSelections)
        
        if changedInput.id == 'select':

            #==============================================================================
            #            processing changes to face selections
            #==============================================================================            

            removedFaces = [face for face in map(lambda x: x.entity, self.register.selectedFacesAsList()) if face not in faces]
            addedFaces = [face for face in faces if face not in map(lambda x: x.entity, self.register.selectedFacesAsList())]
            
            for face in removedFaces:
                #==============================================================================
                #         Faces have/has been removed
                #==============================================================================
                logger.debug(f'face being removed {face}')
                self.controller.deSelectFace(face)
                            
            for face in addedFaces:
            #==============================================================================
            #             Faces have/has been added 
            #==============================================================================
                 
                logger.debug(f'face being added: {face.tempId}')

                self.controller.registerAllFaces(face) #.addFace(face)
                            
                if not changedInput.commandInputs.itemById('edgeSelect').isVisible:
                    changedInput.commandInputs.itemById('edgeSelect').isVisible = True
            self.setSelections(commandInputs= changedInput.commandInputs,
                    activeCommandInput= changedInput.commandInputs.itemById('select')) #update selections
            return

#==============================================================================
#                  end of processing faces
#==============================================================================


        #==============================================================================
        #         Processing changed edge selection            
        #==============================================================================
        if changedInput.id != 'edgeSelect':
            return
            
        removedEdges = [edge for edge in map(lambda x: x.entity, self.register.selectedEdgesAsList()) if edge not in edges]
        addedEdges = [edge for edge in edges if edge not in map(lambda x: x.entity, self.register.selectedEdgesAsList())]


        for edge in removedEdges:
            #==============================================================================
            #             Edges have been removed
            #==============================================================================
            dbEdge.deleteEdge(edge)

        for edge in addedEdges:
            #==============================================================================
            #         Edges have been added
            #==============================================================================
            dbEdge.addEdge(edge)
            edge.dbParams = self.dbParams
            
        self.setSelections(changedInput.commandInputs, changedInput.commandInputs.itemById('edgeSelect'))


    def parseInputs(self, inputs):
        '''==============================================================================
           put the selections into variables that can be accessed by the main routine            
           ==============================================================================
       '''
        inputs = {inp.id: inp for inp in inputs}

        logger.debug('Parsing inputs')

        self.toolDiaStr = inputs['toolDia'].expression
        self.dbParams.toolDia = inputs['toolDia'].value
        self.toolDiaOffsetStr = inputs['toolDiaOffset'].expression
        self.dbParams.toolDiaOffset = inputs['toolDiaOffset'].value
        self.benchmark = inputs['benchmark'].value
        self.dbParams.dbType = inputs['dogboneType'].selectedItem.name
        self.dbParams.minimalPercent = inputs['minimalPercent'].value
        self.dbParams.fromTop = (inputs['depthExtent'].selectedItem.name == 'From Top Face')
        self.dbParams.longSide = (inputs['mortiseType'].selectedItem.name == 'On Long Side')
        self.expandModeGroup = (inputs['modeGroup']).isExpanded
        self.expandSettingsGroup = (inputs['settingsGroup']).isExpanded

        logger.debug(f'self.fromTop = {self.dbParams.fromTop}')
        logger.debug(f'self.dbType = {self.dbParams.dbType}')
        logger.debug(f'self.toolDiaStr = {self.toolDiaStr}')
        logger.debug(f'self.toolDia = {self.dbParams.toolDia}')
        logger.debug(f'self.toolDiaOffsetStr = {self.toolDiaOffsetStr}')
        logger.debug(f'self.toolDiaOffset = {self.dbParams.toolDiaOffset}')
        logger.debug(f'self.benchmark = {self.benchmark}')
        logger.debug(f'self.mortiseType = {self.dbParams.longSide}')
        logger.debug(f'self.expandModeGroup = {self.expandModeGroup}')
        logger.debug(f'self.expandSettingsGroup = {self.expandSettingsGroup}')
        
        
    def closeLogger(self):
#        logging.shutdown()
        for handler in logger.handlers:
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onExecute(self, args:adsk.core.CommandEventArgs):
        start = time.time()

        logger.log(0, 'logging Level = %(levelname)')
        self.parseInputs(args.firingEvent.sender.commandInputs)
        logger.setLevel(self.logging)

        self.writeDefaults()
        defLengthUnits = g._design.unitsManager.defaultLengthUnits

        for component in self.register.registeredComponentEntitiesAsList:
            # targetBody = component.bRepBodies.item(0)
            custFeatInput = component.features.customFeatures.createInput(self._customFeatureDef)

            toolDiameter = adsk.core.ValueInput.createByReal(self.dbParams.toolDia)
            custFeatInput.addCustomParameter('toolDiameter',
                                                'ToolDiameter', 
                                                toolDiameter,
                                                defLengthUnits, 
                                                True)
            toolDiaOffset = adsk.core.ValueInput.createByReal(self.dbParams.toolDiaOffset)               
            custFeatInput.addCustomParameter('toolDiameterOffset', 
                                                'ToolDiameterOffset', 
                                                toolDiaOffset,
                                                defLengthUnits, 
                                                True)
            minAngle = adsk.core.ValueInput.createByReal(self.dbParams.minAngleLimit)             
            custFeatInput.addCustomParameter('minAngle', 
                                                'MinAngle', 
                                                minAngle,
                                                'deg',
                                                True) 
            maxAngle = adsk.core.ValueInput.createByReal(self.dbParams.maxAngleLimit)             
            custFeatInput.addCustomParameter('maxAngle',
                                                'MaxAngle',
                                                maxAngle,
                                                'deg',
                                                True) 
            minPercent = adsk.core.ValueInput.createByReal(self.dbParams.minimalPercent)             
            custFeatInput.addCustomParameter('minPercent',
                                                'MinPercent',
                                                minPercent,
                                                '',
                                                True)  

            toolCollection, targetBody = self.controller.getDogboneTool(component = component, 
                                                            params = self.dbParams)

            combineInput = g._rootComp.features.combineFeatures.createInput(targetBody = targetBody, 
                                                                            toolBodies = toolCollection)
            combineInput.isKeepToolBodies = False
            combineInput.isNewComponent = False
            combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine = g._rootComp.features.combineFeatures.add(combineInput)
            combine.name = 'dbCombine'

        # createStaticDogbones()
        
        logger.info('all dogbones complete\n-------------------------------------------\n')

        self.closeLogger()

        # self.register.clear()
        
        if self.benchmark:
            util.messageBox("Benchmark: {:.02f} sec processing {} edges".format(
                time.time() - start, len(self.edges)))

        if self.errorCount >0:
            util.messageBox(f'Reported errors:{self.errorCount}\nYou may not need to do anything, \nbut check holes have been created'.format())

    def createToolBodies(self):
        radius = (self.dbParams.toolDia + self.dbParams.toolDiaOffset) / 2
        offset = radius / sqrt(2)  * (1 + self.dbParams.minimalPercent/100) if self.dbParams.dbType == 'Minimal Dogbone' else radius if dbParams.dbType == 'Mortise Dogbone' else radius / sqrt(2)

        logger.info('Creating static dogbones')
        errorCount = 0
        if not g._design:
            raise RuntimeError('No active Fusion design')
        minPercent = 1+self.dbParams.minimalPercent/100 if self.dbParams.dbType == 'Minimal Dogbone' else  1
        component_hash_list = self.register.registeredComponentHashesAsList
        logger.debug(f'component_hash_list = {component_hash_list}')
        toolBodies = None
                        
        toolCollection = adsk.core.ObjectCollection.create()
        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
                
        for componentHash in component_hash_list:

            logger.debug(f'Processing Component {componentHash}')
        
            edge_list = self.register.selectedEdgesByComponentAsList(componentHash)
            logger.debug(f'edge_list = {[edge.entity.tempId for edge in edge_list]}')

            for edgeObject in edge_list:
                
                edge = edgeObject.entity
                logger.debug(f'Processing edge - {type(edge)} is Valid={edge.isValid}')
                logger.debug(f'edgeId = {edge.tempId}')

                dbToolBody = edgeObject.getdbTool(dbParams)
                if not toolBodies:
                    toolBodies = dbToolBody
                    continue
                tempBrepMgr.booleanOperation(
                    toolBodies,
                    dbToolBody,
                    adsk.fusion.BooleanTypes.UnionBooleanType)  #combine all the dogbones into a single toolbody
                    
            baseFeatures = g._rootComp.features.baseFeatures
            baseFeature = baseFeatures.add()
            baseFeature.startEdit()
            baseFeature.name = 'dogboneTool'

            dbB = g._rootComp.bRepBodies.add(toolBodies, baseFeature)
            dbB.name = 'dbHole'
            baseFeature.finishEdit()
            baseFeature.name = 'dbBaseFeat'
            
            targetBody = edge_list[0].entity.body
            toolCollection.add(baseFeature.bodies.item(0))

            combineInput = g._rootComp.features.combineFeatures.createInput(targetBody, toolCollection)
            combineInput.isKeepToolBodies = True
            combineInput.isNewComponent = False
            combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine = g._rootComp.features.combineFeatures.add(combineInput)
            combine.name = 'dbCombine'
                                
        # adsk.doEvents()
        

    @eventHandler(handler_cls = adsk.fusion.CustomFeatureEventHandler)
    def computeDogbones(self, args: adsk.fusion.CustomFeatureEventArgs):
        logger.debug('computeDogbones')

                        
        combineInput = g._rootComp.features.combineFeatures.createInput(targetBody, toolCollection)
        combineInput.isKeepToolBodies = False
        combineInput.isNewComponent = False
        combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        combine = g._rootComp.features.combineFeatures.add(combineInput)
        combine.name = 'dbCombine'
                                
        adsk.doEvents()
        
        # if errorCount >0:
        #     util.messageBox('Reported errors:{}\nYou may not need to do anything, \nbut check holes have been created'.format(errorCount))


    ################################################################################        
    @eventHandler(handler_cls = adsk.core.ValidateInputsEventHandler)
    def onValidate(self, args:adsk.core.ValidateInputsEventArgs):
        cmd: adsk.core.ValidateInputsEventArgs = args
        cmd = args.firingEvent.sender

        for input in cmd.commandInputs:
            if input.id == 'select':
                if input.selectionCount < 1:
                    args.areInputsValid = False
            elif input.id == 'circDiameter':
                if input.value <= 0:
                    args.areInputsValid = False
                    
    @eventHandler(handler_cls = adsk.core.SelectionEventHandler)
    def onPreSelect(self, args:adsk.core.SelectionEventArgs):
        '''==============================================================================
            Routine gets called with every mouse movement, if a commandInput select is active                   
           ==============================================================================
       '''
        eventArgs: adsk.core.SelectionEventArgs = args
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

            #if entity hasn't already been selected then make it selectable
            eventArgs.isSelectable = self.register.isEntitySelectable(eventArgs.selection.entity) if len(self.register.registerList) else True  

        return

    @property
    def originPlane(self):
        return g._rootComp.xZConstructionPlane if self.yUp else g._rootComp.xYConstructionPlane
