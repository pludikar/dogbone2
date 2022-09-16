import logging
import os, sys
import re
import pandas as pd
from tkinter.messagebox import RETRY
import adsk.core, adsk.fusion
from typing import List, Callable

from math import sqrt, pi
import json
import time, csv, io
from itertools import tee, chain, islice

from ..common import dbutils as util
from ..common import common as g
# from ..common.paramsClass import Params 
from ..common.decorators import eventHandler, HandlerCollection, timer

# from ..dbClasses import dataclasses as dc, dbEdge, dbFace
# from ..dbClasses.register import Register

# from ..dbClasses.dbController import DbController

logger = logging.getLogger('scribeEdge.command')

class ScribeEdgeCommand(object):
    
    _customFeatureDef: adsk.fusion.CustomFeatureDefinition = None
    controlKeyPressed: bool = False
    mouseClickAction: Callable = None
    _alreadyCreatedCustomFeature: adsk.fusion.CustomFeature = None
    handlerEnabled = True

    def __init__(self):
        
        logger.info('scribeEdge.command')

        self.face: adsk.fusion.BRepFace = None
        self.refEdge: adsk.fusion.BRepEdge = None
        self.scribedEdge: adsk.fusion.BRepEdge = None
        self.data = None
        self.edgeType =  0
        self.benchmark = False
        self.errorCount = 0

        self.expandModeGroup = True
        self.expandSettingsGroup = False
        self.levels = {}
        
    def __del__(self):
        HandlerCollection.remove()  #clear event handers
            
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
        buttonScribeEdge = g._ui.commandDefinitions.addButtonDefinition(
                    g.COMMAND_ID,
                    'ScribeEdge',
                    'Creates scribeEdges at all inside corners of a face',
                    'Resources')

        buttonScribeEdgeEdit = g._ui.commandDefinitions.addButtonDefinition(
                    g.EDIT_ID,
                    'Edit ScribeEdge',
                    'Edits scribeEdges',
                    '')

        
        createPanel = g._ui.allToolbarPanels.itemById('SolidCreatePanel')
        separatorControl = createPanel.controls.addSeparator()
        dropDownControl = createPanel.controls.addDropDown(
                    'ScribeEdge',
                    'Resources',
                    'dbDropDown',
                    separatorControl.id )

        buttonControl = dropDownControl.controls.addCommand(
                    buttonScribeEdge,
                    'scribeEdgeBtn',
                    False)
        editButtonControl = dropDownControl.controls.addCommand(
                    buttonScribeEdgeEdit,
                    'scribeEdgeEditBtn',
                    False)

        # Make the button available in the panel.
        buttonControl.isPromotedByDefault = True
        buttonControl.isPromoted = True

        self._customFeatureDef = adsk.fusion.CustomFeatureDefinition.create(
                    g.FEATURE_ID,
                    'scribeEdge feature',
                    'Resources')
        self._customFeatureDef.editCommandId = g.EDIT_ID

        #attach event handlers

        self.onCreate(event = buttonScribeEdge.commandCreated)

        self.onEditCreate(event = buttonScribeEdgeEdit.commandCreated)
        
        self.computeScribeEdges(event = self._customFeatureDef.customFeatureCompute)

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
        
        logger.info(f"\n{'='*80}\n{'-'*32}scribeEdge started{'-'*33}\n{'='*80}")
            
        # self.register.registerList.clear()

        self.errorCount = 0

        self.face = None
        self.refEdge = None
        self.scribedEdge = None
        
        self.workspace = g._ui.activeWorkspace
                

        inputs :adsk.core.CommandInputs = inputs.command.commandInputs
        
        selFaceInput = inputs.addSelectionInput(
                    'selectedFace',
                    'Face',
                    'Select a face to apply scribeEdges')
        selFaceInput.tooltip =\
            'Select a face to apply scribeEdges\n'\
            '*** Select faces by clicking on them. DO NOT DRAG SELECT! ***' 

        selFaceInput.addSelectionFilter('PlanarFaces')
        selFaceInput.setSelectionLimits(1,1)
        
        selStartPointInput = inputs.addSelectionInput(
                    'refEdge',
                    'Reference Edge',
                    'Edge from which measurements are started')

        selStartPointInput.tooltip ='Select or de-select any internal edges dropping down from a selected face (to apply scribeEdges to)' 
        selStartPointInput.addSelectionFilter('LinearEdges')
        selStartPointInput.setSelectionLimits(1,1)
        selStartPointInput.isVisible = False

        selScribedEdgeInput = inputs.addSelectionInput(
                    'scribedEdge',
                    'Scribed Edge',
                    'Select Edge to be scribed')

        selScribedEdgeInput.tooltip ='Select Edge to be scribed' 
        selScribedEdgeInput.addSelectionFilter('LinearEdges')
        selScribedEdgeInput.setSelectionLimits(1,1)
        selScribedEdgeInput.isVisible = False

        fileImportButton = inputs.addBoolValueInput('csvFile', 'Import File', False, 'resources/button', True)
        
        fileTextBox = inputs.addTextBoxCommandInput('fileTextBox', 'File:', 'No CSV file selected', 1, True)
                
        modeGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput('modeGroup', 'Mode')
        modeGroup.isExpanded = self.expandModeGroup
        # modeGroup.isVisible = False
        modeGroupChildInputs = modeGroup.children
        
        typeRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs\
                .addButtonRowCommandInput(
                    'scribeEdgeType',
                    'Type',
                    False)
        typeRowInput.listItems.add(
                    'Add ScribeEdge',
                    True,
                    'resources/addMaterial')
        typeRowInput.listItems.add(
                    'Subtract ScribeEdge',
                    False,
                    'resources/removeMaterial')
        # typeRowInput.isVisible = False

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

        benchMark = settingGroupChildInputs.addBoolValueInput(
                    "benchmark",
                    "Benchmark time",
                    True,
                    "",
                    self.benchmark)
        benchMark.tooltip = "Enables benchmarking"
        benchMark.tooltipDescription = "When enabled, shows overall time taken to process all selected scribeEdges."

        logDropDownInp: adsk.core.DropDownCommandInput = settingGroupChildInputs.addDropDownCommandInput(
                    "logging",
                    "Logging level",
                    adsk.core.DropDownStyles.TextListDropDownStyle)
        logDropDownInp.tooltip = "Enables logging"
        logDropDownInp.tooltipDescription = "Creates a scribeEdge.log file. \n" \
                     f"Location: {os.path.join(g._appPath, 'dogBone.log')}"

        cmd:adsk.core.Command = inputs.command

        # Add handlers to this command.
        self.onExecute(event = cmd.execute)
        # self.onExecutePreview(event = cmd.executePreview)
        # self.onDestroy(event = cmd.destroy)
        self.onDeactivate(event = cmd.deactivate)
        self.onPreSelect(event = cmd.preSelect)
        self.onValidate(event = cmd.validateInputs)
        self.onChange(event = cmd.inputChanged)
        self.onKeyDown(event = cmd.keyDown)
        self.onKeyUp(event = cmd.keyUp)
        self.onMouseDoubleClick(event = cmd.mouseDoubleClick)
        self.onMouseClick(event = cmd.mouseClick)

        # self.setSelections(inputs, selFaceInput )
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
        
        selFaceInput = inputs.addSelectionInput(
                    'select',
                    'Face',
                    'Select face used to measure scribeEdge offsets')
        selFaceInput.tooltip =\
            'Select face used to measure scribeEdge offsets\n'\
            '*** Select faces by clicking on them. DO NOT DRAG SELECT! ***' 

        selFaceInput.addSelectionFilter('PlanarFaces')
        selFaceInput.setSelectionLimits(1,0)
        
        selStartPointInput = inputs.addSelectionInput(
                    'edgeSelect',
                    'DogBone Edges',
                    'Select vertex used as start point of measurement')

        selStartPointInput.tooltip ='Select vertex used as start point of measurement' 
        selStartPointInput.addSelectionFilter('Vertex')
        selStartPointInput.setSelectionLimits(1,0)
        selStartPointInput.isVisible = False

        selStartPointInput = inputs.addSelectionInput(
                    'edgeSelect',
                    'DogBone Edges',
                    'Select vertex used as start point of measurement')

        selStartPointInput.tooltip ='Select vertex used as start point of measurement' 
        selStartPointInput.addSelectionFilter('Vertex')
        selStartPointInput.setSelectionLimits(1,0)
        selStartPointInput.isVisible = False
                
        inp = inputs.addValueInput(
                    'toolDia',
                    'Tool Diameter               ',
                    g._design.unitsManager.defaultLengthUnits,
                    adsk.core.ValueInput.createByString(self.toolDiaStr))
        inp.tooltip = "Size of the tool with which you'll cut the scribeEdge."
        
        offsetInp = inputs.addValueInput(
                    'toolDiaOffset',
                    'Tool diameter offset',
                    g._design.unitsManager.defaultLengthUnits,
                    adsk.core.ValueInput.createByString(self.offsetStr))
        offsetInp.tooltip = "Increases the tool diameter"
        offsetInp.tooltipDescription = "Use this to create an oversized scribeEdge.\n"\
                                        "Normally set to 0.  \n"\
                                        "A value of .010 would increase the scribeEdge diameter by .010 \n"\
                                        "Used when you want to keep the tool diameter and oversize value separate"
        
        modeGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput('modeGroup', 'Mode')
        modeGroup.isExpanded = self.expandModeGroup
        modeGroupChildInputs = modeGroup.children
        
        typeRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs\
                .addButtonRowCommandInput(
                    'scribeEdgeType',
                    'Type',
                    False)
        typeRowInput.listItems.add(
                    'Normal ScribeEdge',
                    self.dbParams.dbType == 'Normal ScribeEdge',
                    'resources/normal' )
        typeRowInput.listItems.add(
                    'Minimal ScribeEdge',
                    self.dbParams.dbType == 'Minimal ScribeEdge',
                    'resources/minimal' )
        typeRowInput.listItems.add(
                    'Mortise ScribeEdge',
                    self.dbParams.dbType == 'Mortise ScribeEdge',
                    'resources/hidden' )
        typeRowInput.tooltipDescription =\
                    "Minimal scribeEdges creates visually less prominent scribeEdges, but results in an interference fit " \
                    "that, for example, will require a larger force to insert a tenon into a mortise.\n" \
                    "\n"\
                    "Mortise scribeEdges create scribeEdges on the shortest sides, or the longest sides.\n" \
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
        mortiseRowInput.tooltipDescription = "Along Longest will have the scribeEdges cut into the longer sides." \
                                             "\nAlong Shortest will have the scribeEdges cut into the shorter sides."
        mortiseRowInput.isVisible = self.dbParams.dbType == 'Mortise ScribeEdge'

        minPercentInp = modeGroupChildInputs.addValueInput(
                    'minimalPercent',
                    'Percentage Reduction',
                    '',
                    adsk.core.ValueInput.createByReal(self.dbParams.minimalPercent))
        minPercentInp.tooltip = "Percentage of tool radius added to dogBone offset."
        minPercentInp.tooltipDescription =\
             "This should typically be left at 10%, but if the fit is too tight, it should be reduced"
        minPercentInp.isVisible = self.dbParams.dbType == 'Minimal ScribeEdge'

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
             "When \"From Top Face\" is selected, all scribeEdges will be extended to the top most face\n"\
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
        # if not self.register.registeredFacesAsList:
        #     for faceObject in self.register.registeredFacesAsList:
        #         occurrenceTable.addCommandInput(
        #             inputs.addImageCommandInput(
        #                 f"row{rowCount}", 
        #                 faceObject.body_hash, 
        #                 'resources/tableBody/16x16-normal.png'),
        #                 rowCount,
        #                 0)
        #         occurrenceTable.addCommandInput(
        #             inputs.addTextBoxCommandInput(
        #                 f"row{rowCount}Name",
        #                 "          ",
        #                 faceObject.face.body.name,
        #                 1,
        #                 True),
        #                 rowCount,
        #                 1)
        #         rowCount+=1


        benchMark = settingGroupChildInputs.addBoolValueInput(
                    "benchmark",
                    "Benchmark time",
                    True,
                    "",
                    self.benchmark)
        benchMark.tooltip = "Enables benchmarking"
        benchMark.tooltipDescription = "When enabled, shows overall time taken to process all selected scribeEdges."

        logDropDownInp: adsk.core.DropDownCommandInput = settingGroupChildInputs.addDropDownCommandInput(
                    "logging",
                    "Logging level",
                    adsk.core.DropDownStyles.TextListDropDownStyle)
        logDropDownInp.tooltip = "Enables logging"
        logDropDownInp.tooltipDescription = "Creates a scribeEdge.log file. \n" \
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
        pass
        # if args.keyboardModifiers & adsk.core.KeyboardModifiers.AltKeyboardModifier:
        #     self.mouseClickAction = self.controller.selectAllFaces
        #     return
        # self.mouseClickAction = self.controller.selectFace

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onExecutePreview(self, args: adsk.core.CommandEventArgs):
        if self.controlKeyPressed:
            return

        # for body in self.register.registeredBodyEntitiesAsList:
        toolCollection = adsk.core.ObjectCollection.create()

        toolBodies = self.controller.getScribeEdgeTool(bodyEntity = body, 
                                                        params = self.dbParams)

        baseFeatures = g._rootComp.features.baseFeatures
        baseFeature = baseFeatures.add()
        baseFeature.name = 'scribeEdge'

        baseFeature.startEdit()
        dbB = g._rootComp.bRepBodies.add(toolBodies, baseFeature)
        dbB.name = 'scribeEdgeTool'
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
        # self.register.clear()

        # Define a transaction marker so the the roll is not aborted with each change.
        eventArgs.command.beginStep()

        dependencies = self._alreadyCreatedCustomFeature.dependencies

        self.handlerEnabled = False
        self.controlKeyPressed = True
        # self.setSelections(commandInputs = eventArgs.firingEvent.sender.commandInputs,
        activeCommandInput = eventArgs.commandInputs.itemById('select')        
        self.controlKeyPressed = False
        self.handlerEnabled = True
        attribs = self._alreadyCreatedCustomFeature.attributes
        
        params = self._alreadyCreatedCustomFeature.parameters

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onDeactivate(self, inputs:adsk.core.CommandEventArgs):
        logger.debug('onDeactivate')
        # self.register.clear()
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
            
    #==============================================================================
    #  routine to process any changed selections
    #  this is where selection and deselection management takes place
    #  also where eligible edges are determined
    #==============================================================================
    @eventHandler(handler_cls = adsk.core.InputChangedEventHandler)
    def onChange(self, args:adsk.core.InputChangedEventArgs):

        changedInput: adsk.core.CommandInput = args.input
        unitsManager = g._design.unitsManager

        if changedInput.id == 'scribeEdgeType':
            self.edgeType = changedInput.selectedItem.index
            return

        if changedInput.id == 'csvFile':
            if not changedInput.value:
                dlg = g._ui.createFileDialog()
                dlg.title = 'Open CSV File'
                dlg.filter = 'Comma Separated Values (*.csv);;All Files (*.*)'
                # if dlg.showOpen() != adsk.core.DialogResults.DialogOK :
                #     return
                
                # filename = dlg.filename
                filename = g._appPath + '\Book1.csv'#'d:/documents/Book1.csv'
                # df = pd.read_csv(filename, usecols=['dist','offset'], dtype="string")
                df = pd.read_csv(filename, usecols=['dist','offset'], dtype="string")
                self.data = df.applymap(unitsManager.evaluateExpression) #convert everything to internal units.
                args.inputs.itemById('fileTextBox').text = filename
                return
            else:
                self.data = None
                args.inputs.itemById('fileTextBox').text = None
                return

        if changedInput.id != 'selectedFace' and changedInput.id != 'refEdge' and changedInput.id != 'scribedEdge':
            # args.firingEvent.sender.doExecutePreview()
            return
            
        logger.debug(f'input changed- {changedInput.id}')
        
        if changedInput.id == 'selectedFace':
            if args.input.selectionCount:
                self.face = changedInput.selection(0).entity
                args.inputs.itemById('refEdge').isVisible = True
                args.inputs.itemById('refEdge').hasFocus = True
            else:
                self.face = None
                args.inputs.itemById('refEdge').isVisible = False
                args.inputs.itemById('scribedEdge').isVisible = False
            return
            logger.debug(f'input changed- {changedInput.id}')

        if changedInput.id == 'refEdge':
            if changedInput.selectionCount:
                self.refEdge = changedInput.selection(0).entity
                args.inputs.itemById('scribedEdge').isVisible = True
                args.inputs.itemById('scribedEdge').hasFocus = True
            else:
                self.refEdge = None
                args.inputs.itemById('selectedFace').hasFocus = True
                args.inputs.itemById('refEdge').isVisible = False
                args.inputs.itemById('scribedEdge').isVisible = False
            return

        if changedInput.id == 'scribedEdge':
            if changedInput.selectionCount:
                self.scribedEdge = changedInput.selection(0).entity
            else:
                self.scribedEdge = None
                args.inputs.itemById('refEdge').hasFocus = True
                args.inputs.itemById('scribedEdge').isVisible = False
            return

    def closeLogger(self):
#        logging.shutdown()
        for handler in logger.handlers:
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    # @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    # def onDestroy(self, args:adsk.core.CommandEventArgs):
        # self.register.clear()

    @eventHandler(handler_cls = adsk.core.CommandEventHandler)
    def onExecute(self, args:adsk.core.CommandEventArgs):
        start = time.time()

        logger.log(0, 'logging Level = %(levelname)')
        defLengthUnits = g._design.unitsManager.defaultLengthUnits
        custFeatInput:adsk.fusion.CustomFeatureInput  = g._rootComp.features.customFeatures.createInput(self._customFeatureDef)
        featuresCreated = []
        body = self.face.body

        component = body.parentComponent
        
        # toolCollection = adsk.core.ObjectCollection.create()


        # self.baseFeatures = component.features.baseFeatures
        # self.baseFeature = self.baseFeatures.add()
        # featuresCreated.append(self.baseFeature)
        # self.baseFeature.name = 'scribeEdge'

        # self.baseFeature.startEdit()

        toolProfiles = self.getScribeProfiles()

        # extrudeFeatureInput:adsk.fusion.ExtrudeFeatureInput = g._rootComp.features.extrudeFeatures.createInput(toolProfiles, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        # extrudeFeatureInput.participantBodies = [body]
        
        # allExtentDefinition = adsk.fusion.ThroughAllExtentDefinition.create()
        # extrudeFeatureInput.setOneSideExtent(allExtentDefinition, adsk.fusion.ExtentDirections.NegativeExtentDirection)
        # extrudeDistance = adsk.fusion.DistanceExtentDefinition.create()
        # g._rootComp.features.extrudeFeatures.add(extrudeFeatureInput)


        # dbB = component.bRepBodies.add(toolBodies, self.baseFeature)
        # dbB.name = 'scribeEdgeTool'
        # self.baseFeature.finishEdit()

        return

        toolCollection.add(self.baseFeature.bodies.item(0))

        combineInput = component.features.combineFeatures.createInput(targetBody = body, 
                                                                        toolBodies = toolCollection)
        combineInput.isKeepToolBodies = False
        combineInput.isNewComponent = False
        combineInput.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation \
            if self.edgeType \
            else adsk.fusion.FeatureOperations.CutFeatureOperation
        combine = component.features.combineFeatures.add(combineInput)
        featuresCreated.append(combine)
            # custFeat:adsk.fusion.CustomFeature = component.features.customFeatures.add(custFeatInput)


        toolDiameter = adsk.core.ValueInput.createByReal(self.dbParams.toolDia)
        _ = custFeatInput.addCustomParameter('toolDiameter',
                                            'ToolDiameter', 
                                            toolDiamete_,
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
        
        # for i, entity in enumerate( self.register.allSelectedAsEntityList):
        #     _ = dependency.add(f'selected{i}', entity)

        # Roll the timeline to its previous position.
        timelineObject.rollTo(False)

        # custFeat.customNamedValues.addOrSetValue('Faces', topFaces)
        # custFeat.customNamedValues.addOrSetValue('SelectedEntities', json.dumps(self.register.allSelectedAsTokenList))

        custFeat.customNamedValues.addOrSetValue('face', self.face )
        custFeat.customNamedValues.addOrSetValue('refEdge', self.refEdge )
        custFeat.customNamedValues.addOrSetValue('scribedEdge', self.scribedEdge )
        custFeat.customNamedValues.addOrSetValue('edgeType', self.edgeType )

        logger.info(f'\n{"-"*80}\n{" "*29}all scribeEdges complete\n{"-"*80}\n')

        self.closeLogger()

        if self.benchmark:
            util.messageBox(f"Benchmark: {time.time() - start:.02f} sec processing {len(self.edges)} edges")

        if self.errorCount >0:
            util.messageBox(f'Reported errors:{self.errorCount}\nYou may not need to do anything, \nbut check holes have been created'.format())

    @eventHandler(handler_cls = adsk.fusion.CustomFeatureEventHandler)
    def computeScribeEdges(self, args: adsk.fusion.CustomFeatureEventArgs):
        logger.debug('computeScribeEdges')

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
                                
    ################################################################################        
    @eventHandler(handler_cls = adsk.core.ValidateInputsEventHandler)
    def onValidate(self, args:adsk.core.ValidateInputsEventArgs):
        cmd: adsk.core.ValidateInputsEventArgs = args
        cmd = args.firingEvent.sender

        args.areInputsValid = cmd.commandInputs.itemById('selectedFace').selectionCount \
                            and cmd.commandInputs.itemById('refEdge').selectionCount \
                            and cmd.commandInputs.itemById('scribedEdge').selectionCount \
                            and self.data is not None
                    
    @eventHandler(handler_cls = adsk.core.SelectionEventHandler)
    def onPreSelect(self, args:adsk.core.SelectionEventArgs):
        '''==============================================================================
            Routine gets called with every mouse movement, if a commandInput select is active                   
           ==============================================================================
       '''
        # Check which selection input the event is firing for.
        activeIn = args.activeInput
        selection = args.selection
        if not self.face and activeIn.id != 'refEdge' and activeIn.id != 'scribedEdge':
            return # jump out if not dealing with any of the selection boxes
        
        sameFace = selection.entity in self.face.loops.item(0).edges
        if not sameFace:
            args.isSelectable = False
            return
        
        if activeIn.id == 'refEdge':
            args.isSelectable = sameFace
            return

        if activeIn.id == 'scribedEdge':
            selection:adsk.fusion.BRepEdge
            self.refEdgeStart: adsk.fusion.BRepVertex
            self.refEdgeEnd: adsk.fusion.BRepVertex

            self.refEdgeStart = selection.entity.startVertex
            self.refEdgeEnd = selection.entity.endVertex

            # _, self.refEdgeStart, self.refEdgeEnd = selection.entity.geometry.evaluator.getEndPoints()

            args.isSelectable =  (selection.entity in self.refEdgeStart.edges) or (selection.entity in self.refEdgeEnd.edges)

            # allow select if edge is joined to refEdge (shares same start or end vertex)  
            # args.isSelectable = selection.entity.endVertex == self.refEdge.startVertex or \
            #                     selection.entity.startVertex == self.refEdge.endVertex
            #                     # selection.entity.startVertex == self.refEdge.startVertex or
            #                     # selection.entity.endVertex == self.refEdge.endVertex or
            return

        return


    def getScribeProfiles(self)->adsk.core.ObjectCollection:
        '''
        calculates and returns objectCollection of profiles for this scribe edged
        
        '''
        logger.debug(f'processing {self}-----------------------------')
        
        #   get the two faces associated with the edge

        def prev_and_next(iterable):
            prevs, items, nexts = tee(iterable, 3)
            prevs = chain([None], prevs)
            nexts = chain(islice(nexts, 1, None), [None])
            return zip(prevs, items, nexts)

        sketches = g._rootComp.sketches #get sketches variable

        if self.edgeType:
            startOffset = self.data.offset.min()
        else:
            startOffset = self.data.offset.max()

        minx = self.data.dist.min()
        maxx = self.data.dist.max()
        miny = self.data.offset.min()
        maxy = self.data.offset.max()

        self.data.offset = self.data.offset.apply(lambda x: x - startOffset)

        sketch: adsk.fusion.Sketch = sketches.addWithoutEdges(self.face)  #create new sketch object with selected face as plane

        refLine = sketch.project(self.refEdge).item(0)
        refLine.isConstruction = True

        scribedLineCollection = sketch.project(self.scribedEdge)
        scribedLine = scribedLineCollection.item(0)  #get actual scribed line
        scribedLine.isConstruction = True
        scribedEdgeCollecton = sketch.project(self.scribedEdge)
        
        _, _, intersectionPoint = refLine.intersections(scribedEdgeCollecton)  #find corner where refLine and scribed Line meet
        cornerPoint: adsk.core.Point3D = intersectionPoint.item(0)

        refDirStart = refStart = refLine.startSketchPoint
        refDirEnd = refEnd = refLine.endSketchPoint

        if not refEnd.geometry.isEqualTo(cornerPoint):  #check that refLine is the right way around
            refStart, refEnd = (refEnd, refStart)  #using unpacking to swap values, much easier than using temporary holding variables
        refLineVector: adsk.core.Vector3D = refStart.geometry.vectorTo(refEnd.geometry)

        scribeDirStart = scribeStart = scribedLine.startSketchPoint
        scribeDirEnd = scribeEnd = scribedLine.endSketchPoint

        if not scribeStart.geometry.isEqualTo(cornerPoint): #check that scribeLine is the right way around
            scribeStart, scribeEnd = (scribeEnd, scribeStart)
        scribedLineVector: adsk.core.Vector3D = scribeStart.geometry.vectorTo(scribeEnd.geometry)


        angle = refLineVector.crossProduct(scribedLineVector)
        angle.normalize()
        cw = angle.z <0 #cw is clockwise
        # side = -angle.z  #side will be 1 for left side, 1 for right side
        # if ref corner is on right side then we need to swap direction of vector
        # scribedLineVector always points away from corner, or ref line, which is needed to calculate side, via cross product
        # but now we need the direction compared to coordinate system
        x = 0
        if not cw:
            scribeStart, scribeEnd = (scribeEnd, scribeStart)
        scribedLineDirectionVector: adsk.core.Vector3D = scribeStart.geometry.vectorTo(scribeEnd.geometry)

        originPoint = sketch.originPoint.geometry
        xAxis = adsk.core.Vector3D.create(1,0,0)
        zAxis = adsk.core.Vector3D.create(0,0,1)

        angle = xAxis.angleTo(scribedLineDirectionVector)

        moveMatrix = adsk.core.Matrix3D.create()

        if not cw:
            self.data.dist = self.data.dist.apply(lambda x: -x) 

        moveMatrix.setToRotation(angle, zAxis, originPoint)
        logger.debug(f'after rotation: {moveMatrix.asArray()}')

        moveMatrix.translation = originPoint.vectorTo(cornerPoint)
        logger.debug(f'after move: {moveMatrix.asArray()}')

        data = self.data.to_dict('records')
        sketchLines = adsk.core.ObjectCollection.create()
        for previous, line, nxt in prev_and_next( data):
            try:
                startPoint = adsk.core.Point3D.create(line['dist'], line['offset'], 0 )
                endPoint = adsk.core.Point3D.create(nxt['dist'], nxt['offset'], 0 )
                sketchLines.add(sketch.sketchCurves.sketchLines.addByTwoPoints(startPoint, endPoint))
                # logger.debug(f'\rstart: {tmp.geometry.startPoint.asArray()}\r end: {tmp.geometry.endPoint.asArray()}')
            except:
                break


        sketch.move(sketchLines, moveMatrix)

        scribeLineStartPoint = sketchLines.item(0).startSketchPoint
        scribeLineEndPoint = sketchLines.item(sketchLines.count - 1).endSketchPoint

        if cw:
            sketch.sketchCurves.sketchLines.addByTwoPoints(scribeLineStartPoint, scribeStart)
            sketch.sketchCurves.sketchLines.addByTwoPoints(scribeStart, scribeEnd)
            sketch.sketchCurves.sketchLines.addByTwoPoints(scribeEnd, scribeLineEndPoint)
        else:
            sketch.sketchCurves.sketchLines.addByTwoPoints(scribeLineStartPoint, scribeEnd)
            sketch.sketchCurves.sketchLines.addByTwoPoints(scribeEnd, scribeStart)
            sketch.sketchCurves.sketchLines.addByTwoPoints(scribeStart, scribeLineEndPoint)

        profiles = sketch.profiles
        profileCollection = adsk.core.ObjectCollection.create()
        for profile in profiles:
            profileCollection.add(profile)

        return profileCollection
        
        extrudeFeatureInput = g._rootComp.features.extrudeFeatures.createInput(profileCollection, adsk.fusion.FeatureOperations.CutFeatureOperation)
        extrudeFeatureInput.targetBaseFeature = self.baseFeature
        extrudeFeatureInput.setOneSideExtent(adsk.fusion.AllExtentDefinition, adsk.fusion.ExtentDirections.NegativeExtentDirection)
        g._rootComp.features.extrudeFeatures.add(extrudeFeatureInput)

        return
        '''       
        
        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
        dbBody = tempBrepMgr.createCylinderOrCone(startPoint, toolRadius, endPoint, toolRadius)

        
        dbBox = None  #initialize temp brep box, incase it's going to be used - might not be needed
        #   TODO
        # if  cornerAngle != 0 and cornerAngle != pi/2:  # 0 means that the angle between faces is also 0 
        if  params.minAngleLimit < cornerAngle < params.maxAngleLimit:  # 0 means that the angle between faces is also 0 

            # creating a box that will be used to clear the path the tool takes to the dogbone hole
            # box width is toolDia
            # box height is same as edge length
            # box length is from the hole centre to the point where the tool starts cutting the sides


            #   find the orthogonal vector of the centreLine => make a copy then rotate by 90degrees
            logger.debug("Adding acute angle clearance box")
            cornerTan = tan(cornerAngle/2)

            moveMatrix = adsk.core.Matrix3D.create()
            moveMatrix.setToRotation(pi/2, edgeVecto_, startPoint)
            
            widthVectorDirection = centreLineVector.copy()
            widthVectorDirection.transformBy(moveMatrix)
        
            boxLength = toolRadius*minPercent/cornerTan - toolRadius
            boxCentre = startPoint.copy()
            boxWidth = params.toolDia
            
            boxCentreVector = centreLineVector.copy()
            boxCentreVector.normalize()
            boxCentreVector.scaleBy(boxLength/2)
            
            boxCentreHeightVect = edgeVector.copy()
            boxCentreHeightVect.normalize()
            boxHeight = startPoint.distanceTo(topPoint)
            #need to move Box centre point by height /2 to keep top and bottom aligned with cylinder 
            boxCentreHeightVect.scaleBy(boxHeight/2) 
            
            boxCentre.translateBy(boxCentreVector)
            boxCentre.translateBy(boxCentreHeightVect)

            if (boxLength < 0.001):
                boxLength = .001 
            
            boundaryBox = adsk.core.OrientedBoundingBox3D.create(centerPoint = boxCentre, 
                                                                lengthDirection = centreLineVecto_, 
                                                                widthDirection = widthVectorDirection, 
                                                                length = boxLength, 
                                                                width = boxWidth, 
                                                                height = boxHeight)
            
            dbBox = tempBrepMgr.createBox(boundaryBox)
            tempBrepMgr.booleanOperation(targetBody = dbBody, 
                                        toolBody = dbBox, 
                                        booleanType = adsk.fusion.BooleanTypes.UnionBooleanType)
        '''            
        return dbBody  #temporary body ready to be unioned to other bodies    


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
