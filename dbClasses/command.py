import logging
import os, sys
from tkinter.messagebox import RETRY
import adsk.core, adsk.fusion
from typing import List, Callable

from math import sqrt, pi
import json
import time

from ..common import dbutils as util
from ..common import common as g 
from ..common.decorators import eventHandler, HandlerCollection, timer

from ..dbClasses import dataclasses as dc, dbEdge, dbFace
from ..dbClasses.register import Register

from ..dbClasses.dbController import DbController
from .exceptionclasses import NoEdgesToProcess, EdgeNotRegistered, FaceNotRegistered

# from ..dbClasses.staticDogbones import createStaticDogbones

makeNative = lambda x: x.nativeObject if x.nativeObject else x
reValidateFace = lambda comp, x: comp.findBRepUsingPoint(x, adsk.fusion.BRepEntityTypes.BRepFaceEntityType,-1.0 ,False ).item(0)
faceSelections = lambda selectionObjects: list(filter(lambda face: face.objectType == adsk.fusion.BRepFace.classType(), selectionObjects))
edgeSelections = lambda selectionObjects: list(filter(lambda edge: edge.objectType == adsk.fusion.BRepEdge.classType(), selectionObjects))

logger = logging.getLogger('dogbone.command')

class DogboneCommand(object):
    
    register = Register()
    controller = DbController()
    _customFeatureDef: adsk.fusion.CustomFeatureDefinition = None
    controlKeyPressed: bool = False
    mouseClickAction: Callable = None
    _alreadyCreatedCustomFeature: adsk.fusion.CustomFeature = None
    handlerEnabled = True

    def __init__(self):
        
        logger.info('dogbone.command')

        self.dbParams = dc.DbParams()
        self.faceSelections = adsk.core.ObjectCollection.create()
        self.offsetStr = "0"
        self.toolDiaStr = f'{self.dbParams.toolDia} in'
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

        self.selectedges - reverse lookup 
        key: edgeId = str(edgeId:occurrenceNumber) 
        value: str(face tempId:occurrenceNumber)
            provides fast method of finding face that owns an edge
        """
        
        logger.info(f"\n{'='*80}\n{'-'*32}dogbone started{'-'*33}\n{'='*80}")
            
        self.register.registerList.clear()

        self.faces = []
        self.errorCount = 0
        self.faceSelections.clear()
        
        self.workspace = g._ui.activeWorkspace
                
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
        if not self.register.registeredFacesAsList:
            for faceObject in self.register.registeredFacesAsList:
                occurrenceTable.addCommandInput(
                    inputs.addImageCommandInput(
                        f"row{rowCount}", 
                        faceObject.body_hash, 
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
                     f"Location: {os.path.join(g._appPath, 'dogBone.log')}"

        logDropDownInp.listItems.add('Notset',
                                     self.logging == 0)
        logDropDownInp.listItems.add('Debug',
                                     self.logging == 10)
        logDropDownInp.listItems.add('Info',
                                     self.logging == 20)

        cmd:adsk.core.Command = inputs.command

        # Add handlers to this command.
        self.onExecute(event = cmd.execute)
        # self.onExecutePreview(event = cmd.executePreview)
        self.onDestroy(event = cmd.destroy)
        self.onDeactivate(event = cmd.deactivate)
        self.onPreSelect(event = cmd.preSelect)
        self.onValidate(event = cmd.validateInputs)
        self.onChange(event = cmd.inputChanged)
        self.onKeyDown(event = cmd.keyDown)
        self.onKeyUp(event = cmd.keyUp)
        self.onMouseDoubleClick(event = cmd.mouseDoubleClick)
        self.onMouseClick(event = cmd.mouseClick)

        self.setSelections(inputs, selInput0 )
        logger.debug(f'{HandlerCollection.str__()}')


    @eventHandler(handler_cls = adsk.core.CommandCreatedEventHandler)
    def onEditCreate(self, inputs:adsk.core.CommandCreatedEventArgs):
        logger.debug('onEditCreate')
        cmd:adsk.core.Command = inputs.command
        self.register.registerList.clear()

        self.faces = []
        self.errorCount = 0
        self.faceSelections.clear()
        
        self.workspace = g._ui.activeWorkspace

        self._alreadyCreatedCustomFeature = g._ui.activeSelections.item(0).entity
        if self._alreadyCreatedCustomFeature is None:
            return
                
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
        if not self.register.registeredFacesAsList:
            for faceObject in self.register.registeredFacesAsList:
                occurrenceTable.addCommandInput(
                    inputs.addImageCommandInput(
                        f"row{rowCount}", 
                        faceObject.body_hash, 
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
                     f"Location: {os.path.join(g._appPath, 'dogBone.log')}"

        logDropDownInp.listItems.add('Notset',
                                     self.logging == 0)
        logDropDownInp.listItems.add('Debug',
                                     self.logging == 10)
        logDropDownInp.listItems.add('Info',
                                     self.logging == 20)

        cmd:adsk.core.Command = inputs.command

        # Add handlers to this command.
        self.onEditExecute(event = cmd.execute)
        self.onEditActivate(event = cmd.activate)
        self.onPreSelect(event = cmd.preSelect)
        self.onChange(event = cmd.inputChanged)
        # self.onExecutePreview(event = cmd.executePreview)
        self.onValidate(event = cmd.validateInputs)
        logger.debug(f'{HandlerCollection.str__()}')
        pass

    @eventHandler(handler_cls = adsk.core.KeyboardEventHandler)
    def onKeyDown(self, args:adsk.core.KeyboardEventArgs):
        if args.keyCode & adsk.core.KeyCodes.ControlKeyCode:
            self.controlKeyPressed = True
            args.firingEvent.sender.doExecutePreview()

    @eventHandler(handler_cls = adsk.core.KeyboardEventHandler)
    def onKeyUp(self, args:adsk.core.KeyboardEventArgs):
        if args.keyCode & adsk.core.KeyCodes.ControlKeyCode:
            self.controlKeyPressed = False
            args.firingEvent.sender.doExecutePreview()

    @eventHandler(handler_cls = adsk.core.MouseEventHandler)
    def onMouseDoubleClick(self, args:adsk.core.MouseEvent):
        pass

    @eventHandler(handler_cls = adsk.core.MouseEventHandler)
    def onMouseClick(self, args:adsk.core.MouseEventArgs):
        if args.keyboardModifiers & adsk.core.KeyboardModifiers.AltKeyboardModifier:
            self.mouseClickAction = self.controller.selectAllFaces
            return
        self.mouseClickAction = self.controller.selectFace

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onExecutePreview(self, args: adsk.core.CommandEventArgs):
        if self.controlKeyPressed:
            return

        for body in self.register.registeredBodyEntitiesAsList:
            # targetBody = body.bRepBodies.item(0)
            toolCollection = adsk.core.ObjectCollection.create()
            # tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
            # toolBodies = None


            toolBodies = self.controller.getDogboneTool(bodyEntity = body, 
                                                            params = self.dbParams)

            baseFeatures = g._rootComp.features.baseFeatures
            baseFeature = baseFeatures.add()
            baseFeature.name = 'dogbone'

            baseFeature.startEdit()
            dbB = g._rootComp.bRepBodies.add(toolBodies, baseFeature)
            dbB.name = 'dogboneTool'
            baseFeature.finishEdit()

            toolCollection.add(baseFeature.bodies.item(0))
            targetBody = self.register.registeredFacesByBodyAsList(body.entityToken)[0].entity.body


            combineInput = g._rootComp.features.combineFeatures.createInput(targetBody = targetBody, 
                                                                            toolBodies = toolCollection)
            combineInput.isKeepToolBodies = False
            combineInput.isNewComponent = False
            combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine = g._rootComp.features.combineFeatures.add(combineInput)

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onEditActivate(self, eventArgs:adsk.core.CommandEventArgs):
        logger.debug('onEditActivate')

        # Save the current position of the timeline.
        timeline = g._design.timeline
        markerPosition = timeline.markerPosition
        global _restoreTimelineObject, _isRolledForEdit
        _restoreTimelineObject = timeline.item(markerPosition - 1)

        # Roll the timeline to just before the custom feature being edited.
        self._alreadyCreatedCustomFeature.timelineObject.rollTo(rollBefore = True)
        _isRolledForEdit = True
        self.register.clear()

        # Define a transaction marker so the the roll is not aborted with each change.
        eventArgs.command.beginStep()

        dependencies = self._alreadyCreatedCustomFeature.dependencies

        entityList = [d.entity for d in dependencies if 'selected' in d.id]
        faces = faceSelections(entityList)
        edges = edgeSelections(entityList)

        for face in faces:
            
            if face.entityToken in self.register.registeredFacesAsList:
                continue
            self.controller.registerAllFaces(face)

        for edge in edges:
            if edge.entityToken not in self.register.registeredEdgesAsList:
                raise EdgeNotRegistered
            self.controller.selectEdge(edge)

        self.handlerEnabled = False
        self.controlKeyPressed = True
        self.setSelections(commandInputs = eventArgs.firingEvent.sender.commandInputs,
        activeCommandInput = eventArgs.firingEvent.sender.commandInputs.itemById('select'))        
        self.controlKeyPressed = False
        self.handlerEnabled = True
        attribs = self._alreadyCreatedCustomFeature.attributes
        
        params = self._alreadyCreatedCustomFeature.parameters

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onDeactivate(self, inputs:adsk.core.CommandEventArgs):
        logger.debug('onDeactivate')
        self.register.clear()
        pass

    @eventHandler(handler_cls = adsk.core.ApplicationCommandEventHandler)
    def onTerminate(self, arg:adsk.core.ApplicationCommandEventArgs):
        pass

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onEditExecute(self, inputs:adsk.core.CommandEventArgs):
        logger.debug('onEditActivate')
        global _isRolledForEdit, _restoreTimelineObject
        if _isRolledForEdit:
            _restoreTimelineObject.rollTo(False)
            _isRolledForEdit = False
        pass

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onEdit(self, args:adsk.core.CommandEventArgs):
        logger.debug('onEdit')
        pass
            
    def setSelections(self, 
                    commandInputs:adsk.core.CommandInputs = None, 
                    activeCommandInput:adsk.core.CommandInput = None): 
        '''updates the UI selection with the selected entities'''
        collection = adsk.core.ObjectCollection.create()
        g._ui.activeSelections.clear()
        
        faceObjects = self.register.selectedFacesAsList
        edgeObjects = self.register.selectedgesAsList

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

        if not self.handlerEnabled:
            return

        changedInput: adsk.core.CommandInput = args.input

        if changedInput.id == 'dogboneType':
            changedInput.commandInputs.itemById('minimalPercent').isVisible = \
                (changedInput.commandInputs.itemById('dogboneType').selectedItem.name == 'Minimal Dogbone')
            changedInput.commandInputs.itemById('mortiseType').isVisible = \
                (changedInput.commandInputs.itemById('dogboneType').selectedItem.name == 'Mortise Dogbone')
       

        if changedInput.id != 'select' and changedInput.id != 'edgeSelect':
            # args.firingEvent.sender.doExecutePreview()
            return
            
        activeSelections = g._ui.activeSelections.all #save active selections
        # Note: selections are sensitive and fragile, any processing beyond just reading on live selections will destroy selection 

        logger.debug(f'input changed- {changedInput.id}')
        faces = faceSelections(activeSelections)
        edges = edgeSelections(activeSelections)
        
        if changedInput.id == 'select':

            #==============================================================================
            #            processing changes to face selections
            #==============================================================================            

            removedFaces = [face.entity for face in self.register.selectedFacesAsList if face.entity not in faces]
            addedFaces = [faceEntity for faceEntity in faces if hash(faceEntity.entityToken) not in self.register.selectedFacesAsList]
            
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
                 
                logger.debug(f'face being added: {face}')

                if face not in self.register.registeredFacesAsList :
                    self.controller.registerAllFaces(face)
                self.mouseClickAction(face)
                            
                if not changedInput.commandInputs.itemById('edgeSelect').isVisible:
                    changedInput.commandInputs.itemById('edgeSelect').isVisible = True
            self.setSelections(commandInputs = changedInput.commandInputs,
                    activeCommandInput = changedInput.commandInputs.itemById('select')) #update selections

            # args.firingEvent.sender.doExecutePreview()
            return

#==============================================================================
#                  end of processing faces
#==============================================================================


        #==============================================================================
        #         Processing changed edge selection            
        #==============================================================================
        if changedInput.id != 'edgeSelect':
            # args.firingEvent.sender.doExecutePreview()

            return
            
        removedEdges = [edge.entity for edge in self.register.selectedgesAsList if edge.entity not in edges]
        addedEdges = [edgeEntity for edgeEntity in edges if hash(edgeEntity.entityToken) not in self.register.selectedgesAsList]


        for edge in removedEdges:
            #==============================================================================
            #             Edges have been removed
            #==============================================================================
            self.controller.deSelectEdge(edge)

        for edge in addedEdges:
            #==============================================================================
            #         Edges have been added
            #==============================================================================
            self.controller.selectEdge(edge)
            # edge.dbParams = self.dbParams
            
        self.setSelections(commandInputs = changedInput.commandInputs, 
                            activeCommandInput = changedInput.commandInputs.itemById('edgeSelect'))
        # args.firingEvent.sender.doExecutePreview()


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
    def onDestroy(self, args:adsk.core.CommandEventArgs):
        self.register.clear()

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onExecute(self, args:adsk.core.CommandEventArgs):
        start = time.time()

        logger.log(0, 'logging Level = %(levelname)')
        self.parseInputs(args.firingEvent.sender.commandInputs)
        logger.setLevel(self.logging)
        self.writeDefaults()
        defLengthUnits = g._design.unitsManager.defaultLengthUnits
        custFeatInput:adsk.fusion.CustomFeatureInput  = g._rootComp.features.customFeatures.createInput(self._customFeatureDef)
        topFaces = json.dumps(self.register.topFacesByBodyasDict)
  
        featuresCreated = []

        for i, body in enumerate(self.register.registeredBodyEntitiesAsList):
            component = body.parentComponent
            # component = g._rootComp
            
            # custFeatInput:adsk.fusion.CustomFeatureInput  = component.features.customFeatures.createInput(self._customFeatureDef)
            edges = [edgeObject.entity for edgeObject in self.register.selectedgesByBodyAsList(body)]

            toolCollection = adsk.core.ObjectCollection.create()

            toolBodies = self.controller.getDogboneTool(bodyEntity = body, 
                                                            params = self.dbParams)

            baseFeatures = component.features.baseFeatures
            baseFeature = baseFeatures.add()
            featuresCreated.append(baseFeature)
            baseFeature.name = 'dogbone'

            baseFeature.startEdit()
            dbB = component.bRepBodies.add(toolBodies, baseFeature)
            dbB.name = 'dogboneTool'
            baseFeature.finishEdit()

            toolCollection.add(baseFeature.bodies.item(0))
            targetBody = self.register.registeredFacesByBodyAsList(body.entityToken)[0].entity.body


            combineInput = component.features.combineFeatures.createInput(targetBody = targetBody, 
                                                                            toolBodies = toolCollection)
            combineInput.isKeepToolBodies = False
            combineInput.isNewComponent = False
            combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine = component.features.combineFeatures.add(combineInput)
            featuresCreated.append(combine)
            # custFeat:adsk.fusion.CustomFeature = component.features.customFeatures.add(custFeatInput)


        toolDiameter = adsk.core.ValueInput.createByReal(self.dbParams.toolDia)
        _ = custFeatInput.addCustomParameter('toolDiameter',
                                            'ToolDiameter', 
                                            toolDiameter,
                                            defLengthUnits, 
                                            True)
        # custFeatInput.addDependency('toolDiameter', toolDiaPara)
        toolDiaOffset = adsk.core.ValueInput.createByReal(self.dbParams.toolDiaOffset)               
        _ = custFeatInput.addCustomParameter('toolDiameterOffset', 
                                            'ToolDiameterOffset', 
                                            toolDiaOffset,
                                            defLengthUnits, 
                                            True)
        minAngle = adsk.core.ValueInput.createByReal(self.dbParams.minAngleLimit)             
        _ = custFeatInput.addCustomParameter('minAngle', 
                                            'MinAngle', 
                                            minAngle,
                                            'deg',
                                            True) 
        maxAngle = adsk.core.ValueInput.createByReal(self.dbParams.maxAngleLimit)             
        _ = custFeatInput.addCustomParameter('maxAngle',
                                            'MaxAngle',
                                            maxAngle,
                                            'deg',
                                            True) 
        minPercent = adsk.core.ValueInput.createByReal(self.dbParams.minimalPercent)             
        _ = custFeatInput.addCustomParameter('minPercent',
                                            'MinPercent',
                                            minPercent,
                                            '',
                                            True)

        _ = custFeatInput.setStartAndEndFeatures(featuresCreated[0], featuresCreated[-1])
        custFeat:adsk.fusion.CustomFeature = g._rootComp.features.customFeatures.add(custFeatInput)

        timeline = g._design.timeline
        markerPosition = timeline.markerPosition
        timelineObject = timeline.item(markerPosition - 1)
        # Roll the timeline to just before the custom feature being edited.
        timelineObject.rollTo(rollBefore = True)

        dependency = custFeat.dependencies
        
        for i, entity in enumerate( self.register.allSelectedAsEntityList):
            _ = dependency.add(f'selected{i}', entity)

        # Roll the timeline to its previous position.
        timelineObject.rollTo(False)

        # custFeat.customNamedValues.addOrSetValue('Faces', topFaces)
        custFeat.customNamedValues.addOrSetValue('SelectedEntities', json.dumps(self.register.allSelectedAsTokenList))

        custFeat.customNamedValues.addOrSetValue('dbType', self.dbParams.dbType )
        custFeat.customNamedValues.addOrSetValue('fromTop', str(self.dbParams.fromTop) )
        custFeat.customNamedValues.addOrSetValue('longSide', str(self.dbParams.longSide) )

        logger.info(f'\n{"-"*80}\n{" "*29}all dogbones complete\n{"-"*80}\n')

        self.closeLogger()

        if self.benchmark:
            util.messageBox(f"Benchmark: {time.time() - start:.02f} sec processing {len(self.edges)} edges")

        if self.errorCount >0:
            util.messageBox(f'Reported errors:{self.errorCount}\nYou may not need to do anything, \nbut check holes have been created'.format())

    @eventHandler(handler_cls = adsk.fusion.CustomFeatureEventHandler)
    def computeDogbones(self, args: adsk.fusion.CustomFeatureEventArgs):
        logger.debug('computeDogbones')

        if not self.handlerEnabled:
            return

        customFeat:adsk.fusion.CustomFeature = args.customFeature

        dependencies = customFeat.dependencies
        parameters = customFeat.parameters
        attributes = customFeat.attributes

        targetBody = customFeat.dependencies.itemById('dbBody').entity
        combineInput = g._rootComp.features.combineFeatures.createInput(targetBody, toolCollection)
        combineInput.isKeepToolBodies = False
        combineInput.isNewComponent = False
        combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        combine = g._rootComp.features.combineFeatures.updateBody(combineInput)
        combine.name = 'dbCombine'
                                
        # adsk.doEvents()
        
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

        # if activeIn.id == 'select':
            #==============================================================================
            # processing activities when faces are being selected
            #        selection filter is limited to planar faces
            #        makes sure only valid occurrences and bodys are selectable
            #==============================================================================


        if not self.controlKeyPressed and len(self.register.registerList):
            eventArgs.isSelectable = False
            return
        
        eventArgs.isselectable = self.register.isEntitySelectable(eventArgs.selection.entity) if len(self.register.registerList) else True

        return

    @timer
    def test_compare(self, entity):
        for i in range(10000):
            et = entity.entityToken == entity.entityToken
    @timer
    def test_hash(self, entity):
        eh = hash(entity.entityToken)
        for i in range(10000):
             eh == hash(entity.entityToken)

    @property
    def originPlane(self):
        return g._rootComp.xZConstructionPlane if self.yUp else g._rootComp.xYConstructionPlane
