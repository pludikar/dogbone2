import logging
import os, sys
from . import dbFace
import adsk.core, adsk.fusion

from collections import defaultdict

import json

import time
from ..common import dbutils as util
from ..common import decorators as d
from ..dbClasses import dataclasses as dc, dbEdge, dbFace
from ..dbClasses.register import Register
from ..dbClasses.dbController import DbController
from ..dbClasses.parametricDogbones import createParametricDogbones
from ..dbClasses.staticDogbones import createStaticDogbones

makeNative = lambda x: x.nativeObject if x.nativeObject else x
reValidateFace = lambda comp, x: comp.findBRepUsingPoint(x, adsk.fusion.BRepEntityTypes.BRepFaceEntityType,-1.0 ,False ).item(0)
faceSelections = lambda selectionObjects: list(filter(lambda face: face.objectType == adsk.fusion.BRepFace.classType(), selectionObjects))
edgeSelections = lambda selectionObjects: list(filter(lambda edge: edge.objectType == adsk.fusion.BRepEdge.classType(), selectionObjects))

logger = logging.getLogger('dogbone.command')


class DogboneCommand(object):
    RADIOBUTTONLIST_ID = 'dbButtonList' 
    COMMAND_ID = "dogboneBtn"
    RESTORE_ID = "dogboneRestoreBtn"
    
    register = Register()
    dbController = DbController()

    def __init__(self):
        
        logger.info('dogbone.command')

        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface

        self.dbParams = dc.DbParams()
        self.faceSelections = adsk.core.ObjectCollection.create()
        self.offsetStr = "0"
        self.toolDiaStr = str(self.dbParams.toolDia) + " in"
        self.edges = []
        self.benchmark = False
        self.errorCount = 0

        self.addingEdges = 0
        self.parametric = False
        self.loggingLevels = dc.LoginLevels() #Utility 
        self.logging = self.loggingLevels.Debug
        # {'Notset':0,'Debug':10,'Info':20,'Warning':30,'Error':40}

        self.expandModeGroup = True
        self.expandSettingsGroup = False
        self.levels = {}

        self.appPath = os.path.dirname(os.path.abspath(__file__))
        self.registeredEntities = adsk.core.ObjectCollection.create()
        
    def __del__(self):
        d.HandlerCollection.handlers = []  #clear event handers
        # for handler in logger.handlers:
        #     handler.flush()
        #     handler.close()

    def writeDefaults(self):
        logger.info('config file write')

        json_file = open(os.path.join(self.appPath, 'defaults.dat'), 'w', encoding='UTF-8')
        json.dump(self.dbParams.dict(), json_file, ensure_ascii=False)
        json_file.close()
    
    def readDefaults(self): 
        logger.info('config file read')
        if not os.path.isfile(os.path.join(self.appPath, 'defaults.dat')):
            return
        json_file = open(os.path.join(self.appPath, 'defaults.dat'), 'r', encoding='UTF-8')
        try:
            resultStr = json.load(json_file)
            self.dbParams= dc.DbParams(**resultStr)
        except ValueError:
            logger.error('default.dat error')
            json_file.close()
            json_file = open(os.path.join(self.appPath, 'defaults.dat'), 'w', encoding='UTF-8')
            json.dump(self.dbParams.dict(), json_file, ensure_ascii=False)
            return

        json_file.close()
        # try:
        #     self.offsetStr = self.defaultData['offsetStr']
        #     self.toolDiaStr = self.defaultData['toolDiaStr']
        #     self.benchmark = self.defaultData['benchmark']

        #     self.dbParams.offset = self.defaultData['offset']
        #     self.dbParams.toolDia = self.defaultData['toolDia']
        #     self.dbParams.dbType = self.defaultData['dbType']
        #     self.dbParams.minimalPercent = self.defaultData['minimalPercent']
        #     self.dbParams.fromTop = self.defaultData['fromTop']
        #     self.dbParams.minAngleLimit = self.defaultData['minAngleLimit']
        #     self.dbParams.maxAngleLimit = self.defaultData['maxAngleLimit']

        #     self.parametric = self.defaultData['parametric']
        #     self.logging = self.defaultData['logging']
        #     self.dbParams.longside = self.defaultData['mortiseType']
        #     self.expandModeGroup = self.defaultData['expandModeGroup']
        #     self.expandSettingsGroup = self.defaultData['expandSettingsGroup']

        # except KeyError: 
        
        #     logger.error('Key error on read config file')
        # #if there's a keyError - means file is corrupted - so, rewrite it with known existing defaultData - it will result in a valid dict, 
        # # but contents may have extra, superfluous  data
        #     json_file = open(os.path.join(self.appPath, 'defaults.dat'), 'w', encoding='UTF-8')
        #     json.dump(self.defaultData, json_file, ensure_ascii=False)
        #     json_file.close()
        #     return
            
    def debugFace(self, face):
        if logger.level < logging.DEBUG:
            return
        for edge in face.edges:
            logger.debug('edge {}; startVertex: {}; endVertex: {}'.format(edge.tempId, edge.startVertex.geometry.asArray(), edge.endVertex.geometry.asArray()))

        return

    def addButtons(self):
        # clean up any crashed instances of the button if existing
        try:
            self.removeButtons()
        except:
            return -1
        
        buttonRestore = self.ui.commandDefinitions.addButtonDefinition(self.RESTORE_ID,
                                                                       'Refresh',
                                                                       'quick way to refresh dogbones',
                                                                       'Resources')

        # add add-in to UI
        buttonDogbone = self.ui.commandDefinitions.addButtonDefinition( self.COMMAND_ID,
                                                                       'Dogbone',
                                                                       'Creates dogbones at all inside corners of a face',
                                                                       'Resources')
        self.onCreate(event=buttonDogbone.commandCreated)
        self.onRestore(event=buttonRestore.commandCreated)

        createPanel = self.ui.allToolbarPanels.itemById('SolidCreatePanel')
        separatorControl = createPanel.controls.addSeparator()
        dropDownControl = createPanel.controls.addDropDown('Dogbone',
                                                           'Resources',
                                                           'dbDropDown',
                                                           separatorControl.id )
        buttonControl = dropDownControl.controls.addCommand(buttonDogbone,
                                                            'dogboneBtn')
        restoreBtnControl = dropDownControl.controls.addCommand(buttonRestore,
                                                             'dogboneRestoreBtn')

        # Make the button available in the panel.
        buttonControl.isPromotedByDefault = True
        buttonControl.isPromoted = True
        

    def removeButtons(self):
#        cleans up buttons and command definitions left over from previous instantiations
        cmdDef = self.ui.commandDefinitions.itemById(self.COMMAND_ID)
        restoreDef = self.ui.commandDefinitions.itemById(self.RESTORE_ID)
        createPanel = self.ui.allToolbarPanels.itemById('SolidCreatePanel')
        dbDropDowncntrl = createPanel.controls.itemById('dbDropDown')
        if dbDropDowncntrl:
            dbButtoncntrl = dbDropDowncntrl.controls.itemById('dogboneBtn')
            if dbButtoncntrl:
                dbButtoncntrl.isPromoted = False
                dbButtoncntrl.deleteMe()
            dbRestoreBtncntrl = dbDropDowncntrl.controls.itemById('dogboneRestoreBtn')
            if dbRestoreBtncntrl:
                dbRestoreBtncntrl.deleteMe()
            dbDropDowncntrl.deleteMe()
        if restoreDef:
            restoreDef.deleteMe()
        if cmdDef:
            cmdDef.deleteMe()

    @d.eventHandler(handler_cls=adsk.core.CommandCreatedEventHandler)
    def onCreate(self, args:adsk.core.CommandCreatedEventArgs):
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
        inputs: adsk.core.CommandCreatedEventArgs = args
        
        logger.info("============================================================================================")
        logger.info("-----------------------------------dogbone started------------------------------------------")
        logger.info("============================================================================================")
            
        self.faces = []
        self.errorCount = 0
        self.faceSelections.clear()
        
        # self.register = Register
        
        self.workspace = self.ui.activeWorkspace

        self.NORMAL_ID = 'dogboneNormalId'
        self.MINIMAL_ID = 'dogboneMinimalId'
                
        argsCmd: adsk.core.Command = args
        
        # self.registry.preLoad()
        
        if self.design.designType != adsk.fusion.DesignTypes.ParametricDesignType :
            returnValue = self.ui.messageBox('DogBone only works in Parametric Mode \n Do you want to change modes?',
                                             'Change to Parametric mode',
                                             adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                                             adsk.core.MessageBoxIconTypes.WarningIconType)
            if returnValue != adsk.core.DialogResults.DialogYes:
                return
            self.design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        self.readDefaults()

        inputs :adsk.core.CommandInputs = inputs.command.commandInputs
        
        selInput0 = inputs.addSelectionInput('select',
                                             'Face',
                                             'Select a face to apply dogbones to all internal corner edges')
        selInput0.tooltip ='Select a face to apply dogbones to all internal corner edges\n*** Select faces by clicking on them. DO NOT DRAG SELECT! ***' 

        selInput0.addSelectionFilter('PlanarFaces')
        selInput0.setSelectionLimits(1,0)
        
        selInput1 = inputs.addSelectionInput(
            'edgeSelect', 'DogBone Edges',
            'Select or de-select any internal edges dropping down from a selected face (to apply dogbones to')

        selInput1.tooltip ='Select or de-select any internal edges dropping down from a selected face (to apply dogbones to)' 
        selInput1.addSelectionFilter('LinearEdges')
        selInput1.setSelectionLimits(1,0)
        selInput1.isVisible = False
                
        inp = inputs.addValueInput(
            'toolDia', 'Tool Diameter               ', self.design.unitsManager.defaultLengthUnits,
            adsk.core.ValueInput.createByString(self.toolDiaStr))
        inp.tooltip = "Size of the tool with which you'll cut the dogbone."
        
        offsetInp = inputs.addValueInput(
            'toolDiaOffset', 'Tool diameter offset', self.design.unitsManager.defaultLengthUnits,
            adsk.core.ValueInput.createByString(self.offsetStr))
        offsetInp.tooltip = "Increases the tool diameter"
        offsetInp.tooltipDescription = "Use this to create an oversized dogbone.\n"\
                                        "Normally set to 0.  \n"\
                                        "A value of .010 would increase the dogbone diameter by .010 \n"\
                                        "Used when you want to keep the tool diameter and oversize value separate"
        
        modeGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput('modeGroup', 'Mode')
        modeGroup.isExpanded = self.expandModeGroup
        modeGroupChildInputs = modeGroup.children
        
        modeRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs.addButtonRowCommandInput('modeRow', 'Mode', False)
        modeRowInput.listItems.add('Static',
                                   not self.parametric,
                                   'resources/staticMode' )
        modeRowInput.listItems.add('Parametric',
                                   self.parametric,
                                   'resources/parametricMode' )
        modeRowInput.tooltipDescription = "Static dogbones do not move with the underlying component geometry. \n" \
                                "\nParametric dogbones will automatically adjust position with parametric changes to underlying geometry. " \
                                "Geometry changes must be made via the parametric dialog.\nFusion has more issues/bugs with these!"
        
        typeRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs.addButtonRowCommandInput('dogboneType',
                                                                                                          'Type',
                                                                                                          False)
        typeRowInput.listItems.add('Normal Dogbone',
                                   self.dbParams.dbType == 'Normal Dogbone',
                                   'resources/normal' )
        typeRowInput.listItems.add('Minimal Dogbone',
                                   self.dbParams.dbType == 'Minimal Dogbone',
                                   'resources/minimal' )
        typeRowInput.listItems.add('Mortise Dogbone',
                                   self.dbParams.dbType == 'Mortise Dogbone',
                                   'resources/hidden' )
        typeRowInput.tooltipDescription = "Minimal dogbones creates visually less prominent dogbones, but results in an interference fit " \
                                            "that, for example, will require a larger force to insert a tenon into a mortise.\n" \
                                            "\nMortise dogbones create dogbones on the shortest sides, or the longest sides.\n" \
                                            "A piece with a tenon can be used to hide them if they're not cut all the way through the workpiece."
        
        mortiseRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs.addButtonRowCommandInput('mortiseType', 'Mortise Type', False)
        mortiseRowInput.listItems.add('On Long Side',
                                      self.dbParams.longSide,
                                      'resources/hidden/longside' )
        mortiseRowInput.listItems.add('On Short Side',
                                      not self.dbParams.longSide,
                                      'resources/hidden/shortside' )
        mortiseRowInput.tooltipDescription = "Along Longest will have the dogbones cut into the longer sides." \
                                             "\nAlong Shortest will have the dogbones cut into the shorter sides."
        mortiseRowInput.isVisible = self.dbParams.dbType == 'Mortise Dogbone'

        minPercentInp = modeGroupChildInputs.addValueInput('minimalPercent',
                                                           'Percentage Reduction',
                                                           '',
                                                           adsk.core.ValueInput.createByReal(self.dbParams.minimalPercent))
        minPercentInp.tooltip = "Percentage of tool radius added to dogBone offset."
        minPercentInp.tooltipDescription = "This should typically be left at 10%, but if the fit is too tight, it should be reduced"
        minPercentInp.isVisible = self.dbParams.dbType == 'Minimal Dogbone'

        depthRowInput: adsk.core.ButtonRowCommandInput = modeGroupChildInputs.addButtonRowCommandInput('depthExtent',
                                                                                                           'Depth Extent',
                                                                                                           False)
        depthRowInput.listItems.add('From Selected Face',
                                    not self.dbParams.fromTop,
                                    'resources/fromFace' )
        depthRowInput.listItems.add('From Top Face',
                                    self.dbParams.fromTop,
                                    'resources/fromTop' )
        depthRowInput.tooltipDescription = "When \"From Top Face\" is selected, all dogbones will be extended to the top most face\n"\
                                            "\nThis is typically chosen when you don't want to, or can't do, double sided machining."
 
        settingGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput('settingsGroup',
                                                                                    'Settings')
        settingGroup.isExpanded = self.expandSettingsGroup
        settingGroupChildInputs = settingGroup.children

        occurrenceTable: adsk.core.TableCommandInput = inputs.addTableCommandInput('occTable', 'OccurrenceTable', 2, "1:1")
        occurrenceTable.isFullWidth = True

        rowCount = 0
        if not self.register.registeredObjectsAsList(dbFace.DbFace):
            for faceObject in self.register.registeredObjectsAsList(dbFace.DbFace):
                occurrenceTable.addCommandInput(inputs.addImageCommandInput(f"row{rowCount}", 
                                                                            faceObject.component_hash, 
                                                                            'resources/tableBody/16x16-normal.png'),
                                                                            rowCount,
                                                                            0)
                occurrenceTable.addCommandInput(inputs.addTextBoxCommandInput(f"row{rowCount}Name",
                                                                            "          ",
                                                                            faceObject.face.body.name,
                                                                            1,
                                                                            True),
                                                                            rowCount,
                                                                            1)
                rowCount+=1


        benchMark = settingGroupChildInputs.addBoolValueInput("benchmark",
                                                              "Benchmark time",
                                                              True,
                                                              "",
                                                              self.benchmark)
        benchMark.tooltip = "Enables benchmarking"
        benchMark.tooltipDescription = "When enabled, shows overall time taken to process all selected dogbones."

        logDropDownInp: adsk.core.DropDownCommandInput = settingGroupChildInputs.addDropDownCommandInput("logging",
                                                                                                        "Logging level",
                                                                                                        adsk.core.DropDownStyles.TextListDropDownStyle)
        logDropDownInp.tooltip = "Enables logging"
        logDropDownInp.tooltipDescription = "Creates a dogbone.log file. \n" \
                     "Location: " +  os.path.join(self.appPath, 'dogBone.log')

        logDropDownInp.listItems.add('Notset',
                                     self.logging == 0)
        logDropDownInp.listItems.add('Debug',
                                     self.logging == 10)
        logDropDownInp.listItems.add('Info',
                                     self.logging == 20)

        cmd:adsk.core.Command = args.command

        # Add handlers to this command.
        self.onExecute(event=cmd.execute)
        self.onPreSelect(event=cmd.preSelect)
        self.onValidate(event=cmd.validateInputs)
        self.onChange(event=cmd.inputChanged)
        self.setSelections(inputs, selInput0 )
        
    @d.eventHandler(handler_cls=adsk.core.CommandCreatedEventHandler)
    def onRestore(self, args:adsk.core.CommandCreatedEventArgs):
        pass
            
    def setSelections(self, commandInputs:adsk.core.CommandInputs=None, activeCommandInput:adsk.core.CommandInput = None): #updates the selected entities on the UI
        collection = adsk.core.ObjectCollection.create()
        self.ui.activeSelections.clear()
        
        
        faceObjects = self.register.selectedObjectsAsList(dbFace.DbFace)
        edgeObjects = self.register.selectedObjectsAsList(dbEdge.DbEdge)

        commandInputs.itemById('select').hasFocus = True        
        for faceObject in faceObjects:
            collection.add(faceObject.entity)
            
        self.ui.activeSelections.all = collection
        
        commandInputs.itemById('edgeSelect').isVisible = True
    
        commandInputs.itemById('edgeSelect').hasFocus = True        
        
        for edgeObject in edgeObjects:
            collection.add(edgeObject.entity)
            
        self.ui.activeSelections.all = collection
        
        activeCommandInput.hasFocus = True

    #==============================================================================
    #  routine to process any changed selections
    #  this is where selection and deselection management takes place
    #  also where eligible edges are determined
    #==============================================================================
    @d.eventHandler(handler_cls=adsk.core.InputChangedEventHandler)
    def onChange(self, args:adsk.core.InputChangedEventArgs):
        changedInput: adsk.core.CommandInput = args.input

        if changedInput.id == 'dogboneType':
            changedInput.commandInputs.itemById('minimalPercent').isVisible = (changedInput.commandInputs.itemById('dogboneType').selectedItem.name == 'Minimal Dogbone')
            changedInput.commandInputs.itemById('mortiseType').isVisible = (changedInput.commandInputs.itemById('dogboneType').selectedItem.name == 'Mortise Dogbone')
       

        if changedInput.id != 'select' and changedInput.id != 'edgeSelect':
            return
            
        activeSelections = self.ui.activeSelections.all #save active selections - selections are sensitive and fragile, any processing beyond just reading on live selections will destroy selection 

        logger.debug(f'input changed- {changedInput.id}')
        faces = faceSelections(activeSelections)
        edges = edgeSelections(activeSelections)
        
        if changedInput.id == 'select':

            #==============================================================================
            #            processing changes to face selections
            #==============================================================================            

            removedFaces = [face for face in map(lambda x: x.entity, self.register.selectedObjectsAsList(dbFace.DbFace)) if face not in faces]
            addedFaces = [face for face in faces if face not in map(lambda x: x.entity, self.register.selectedObjectsAsList(dbFace.DbFace))]
            
            for face in removedFaces:
                #==============================================================================
                #         Faces have/has been removed
                #==============================================================================
                logger.debug(f'face being removed {face.entityToken}')
                self.dbController.deSelectFace(face)
                            
            for face in addedFaces:
            #==============================================================================
            #             Faces have/has been added 
            #==============================================================================
                 
                logger.debug('face being added {}'.format(face.entityToken))
                # faceOccurrence = util.getOccurrenceHash(face)

                self.dbController.registerAllFaces(face) #.addFace(face)
                            
                if not changedInput.commandInputs.itemById('edgeSelect').isVisible:
                    changedInput.commandInputs.itemById('edgeSelect').isVisible = True
            self.setSelections(commandInputs= changedInput.commandInputs, activeCommandInput= changedInput.commandInputs.itemById('select')) #update selections
            return

#==============================================================================
#                  end of processing faces
#==============================================================================


        #==============================================================================
        #         Processing changed edge selection            
        #==============================================================================
        if changedInput.id != 'edgeSelect':
            return
            
        removedEdges = [edge for edge in map(lambda x: x.edge, self.register.selectedObjectsAsList(dbEdge.DbEdge)) if edge not in edges]
        addedEdges = [edge for edge in edges if edge not in map(lambda x: x.edge, self.register.selectedObjectsAsList(dbEdge.DbEdge))]


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
        self.parametric = (inputs['modeRow'].selectedItem.name == 'Parametric')
        self.dbParams.longSide = (inputs['mortiseType'].selectedItem.name == 'On Long Side')
        self.expandModeGroup = (inputs['modeGroup']).isExpanded
        self.expandSettingsGroup = (inputs['settingsGroup']).isExpanded

        logger.debug('self.fromTop = {}'.format(self.dbParams.fromTop))
        logger.debug('self.dbType = {}'.format(self.dbParams.dbType))
        logger.debug('self.parametric = {}'.format(self.parametric))
        logger.debug('self.toolDiaStr = {}'.format(self.toolDiaStr))
        logger.debug('self.toolDia = {}'.format(self.dbParams.toolDia))
        logger.debug('self.toolDiaOffsetStr = {}'.format(self.toolDiaOffsetStr))
        logger.debug('self.toolDiaOffset = {}'.format(self.dbParams.toolDiaOffset))
        logger.debug('self.benchmark = {}'.format(self.benchmark))
        logger.debug('self.mortiseType = {}'.format(self.dbParams.longSide))
        logger.debug('self.expandModeGroup = {}'.format(self.expandModeGroup))
        logger.debug('self.expandSettingsGroup = {}'.format(self.expandSettingsGroup))
        
        # self.edges = []
        # self.faces = []
        
        #inputs are not iterable - so need to do this long hand
        # for i in range(inputs['edgeSelect'].selectionCount):
        #     entity = inputs['edgeSelect'].selection(i).entity
        #     if entity.objectType == adsk.fusion.BRepEdge.classType():
        #         self.edges.append(entity)
        # for i in range(inputs['select'].selectionCount):
        #     entity = inputs['select'].selection(i).entity
        #     if entity.objectType == adsk.fusion.BRepFace.classType():
        #         self.faces.append(entity)
        
    def closeLogger(self):
#        logging.shutdown()
        for handler in logger.handlers:
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    @d.eventHandler(handler_cls=adsk.core.CommandEventHandler)
    def onExecute(self, args:adsk.core.CommandEventArgs):
        start = time.time()
        
        
        # self.originWorkspace.activate()

        logger.log(0, 'logging Level = %(levelname)')
        self.parseInputs(args.firingEvent.sender.commandInputs)
        logger.setLevel(self.logging)

        self.writeDefaults()

        if self.parametric:
            userParams: adsk.fusion.UserParameters = self.design.userParameters
            
            #set up parameters, so that changes can be easily made after dogbones have been inserted
            if not userParams.itemByName('dbToolDia'):
                dValIn = adsk.core.ValueInput.createByString(self.toolDiaStr)
                dParameter = userParams.add('dbToolDia', dValIn, self.design.unitsManager.defaultLengthUnits, '')
                dParameter.isFavorite = True
            else:
                uParam = userParams.itemByName('dbToolDia')
                uParam.expression = self.toolDiaStr
                uParam.isFavorite = True
                
            if not userParams.itemByName('dbOffset'):
                rValIn = adsk.core.ValueInput.createByString(self.toolDiaOffsetStr)
                rParameter = userParams.add('dbOffset',rValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
            else:
                uParam = userParams.itemByName('dbOffset')
                uParam.expression = self.toolDiaOffsetStr
                uParam.comment = 'Do NOT change formula'

            if not userParams.itemByName('dbRadius'):
                rValIn = adsk.core.ValueInput.createByString('(dbToolDia + dbOffset)/2')
                rParameter = userParams.add('dbRadius',rValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
            else:
                uParam = userParams.itemByName('dbRadius')
                uParam.expression = '(dbToolDia + dbOffset)/2'
                uParam.comment = 'Do NOT change formula'

            if not userParams.itemByName('dbMinPercent'):
                rValIn = adsk.core.ValueInput.createByReal(self.dbParams.minimalPercent)
                rParameter = userParams.add('dbMinPercent',rValIn, '', '')
                rParameter.isFavorite = True
            else:
                uParam = userParams.itemByName('dbMinPercent')
                uParam.value = self.dbParams.minimalPercent
                uParam.comment = ''
                uParam.isFavorite = True

            if not userParams.itemByName('dbHoleOffset'):
                oValIn = adsk.core.ValueInput.createByString('dbRadius / sqrt(2)' + (' * (1 + dbMinPercent/100)') if self.dbParams.dbType == 'Minimal Dogbone' else 'dbRadius' if self.dbParams.dbType == 'Mortise Dogbone' else 'dbRadius / sqrt(2)')
                oParameter = userParams.add('dbHoleOffset', oValIn, self.design.unitsManager.defaultLengthUnits, 'Do NOT change formula')
            else:
                uParam = userParams.itemByName('dbHoleOffset')
                uParam.expression = 'dbRadius / sqrt(2)' + (' * (1 + dbMinPercent/100)') if self.dbParams.dbType == 'Minimal Dogbone' else 'dbRadius' if self.dbParams.dbType == 'Mortise Dogbone' else 'dbRadius / sqrt(2)'
                uParam.comment = 'Do NOT change formula'

            self.radius = userParams.itemByName('dbRadius').value
            self.offset = adsk.core.ValueInput.createByString('dbOffset')
            self.offset = adsk.core.ValueInput.createByReal(userParams.itemByName('dbHoleOffset').value)

            createParametricDogbones()

        else: #Static dogbones
           
            createStaticDogbones()
        
        logger.info('all dogbones complete\n-------------------------------------------\n')

        self.closeLogger()
        
        if self.benchmark:
            util.messageBox("Benchmark: {:.02f} sec processing {} edges".format(
                time.time() - start, len(self.edges)))

        if self.errorCount >0:
            util.messageBox(f'Reported errors:{self.errorCount}\nYou may not need to do anything, \nbut check holes have been created'.format())



    ################################################################################        
    @d.eventHandler(handler_cls=adsk.core.ValidateInputsEventHandler)
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
                    
    @d.eventHandler(handler_cls=adsk.core.SelectionEventHandler)
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

    def removeHandlers(self):
        adsk.terminate()

    @property
    def design(self):
        return self.app.activeProduct

    @property
    def rootComp(self):
        return self.design.rootComponent

    @property
    def originPlane(self):
        return self.rootComp.xZConstructionPlane if self.yUp else self.rootComp.xYConstructionPlane

    # The main algorithm for parametric dogbones
