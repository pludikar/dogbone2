import  logging
import adsk.core, adsk.fusion
from .register import Register
from .dataclasses import DbParams
from ..common import dbutils as util
from math import sqrt, pi
from .dbEdge import DbEdge
from .dbFace import DbFace

app = adsk.core.Application.get()  #might be better to put the next few lines into global!!
ui = app.userInterface
product = app.activeProduct
design: adsk.fusion.Design = product
rootComp = product.rootComponent

logger = logging.getLogger('dogbone.static')

def createStaticDogbones():
    dbParams = DbParams()
    register = Register()
    radius = (dbParams.toolDia + dbParams.toolDiaOffset) / 2
    offset = radius / sqrt(2)  * (1 + dbParams.minimalPercent/100) if dbParams.dbType == 'Minimal Dogbone' else radius if dbParams.dbType == 'Mortise Dogbone' else radius / sqrt(2)

    logger.info('Creating static dogbones')
    errorCount = 0
    if not design:
        raise RuntimeError('No active Fusion design')
    minPercent = 1+dbParams.minimalPercent/100 if dbParams.dbType == 'Minimal Dogbone' else  1
    component_hash_list = register.registeredOccurrenceHashesAsList
    logger.debug(f'component_hash_list = {component_hash_list}')
    toolBodies = None
                    
    toolCollection = adsk.core.ObjectCollection.create()
    tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
            
    for componentHash in component_hash_list:

        logger.debug(f'Processing Component {componentHash}')
    
        edge_list = register.selectedObjectsByComponentAsList(DbEdge, componentHash)
        logger.debug(f'edge_list = {[edge.entity.tempId for edge in edge_list]}')
        for edgeObject in edge_list:
            
            edge = edgeObject.entity
            logger.debug(f'Processing edge - {type(edge)} is Valid={edge.isValid}')
            logger.debug(f'edgeId = {edge.tempId}')

            dbToolBody = edgeObject.getdbTool(dbParams)
            if not toolBodies:
                toolBodies = dbToolBody
                continue
            tempBrepMgr.booleanOperation(toolBodies, dbToolBody, adsk.fusion.BooleanTypes.UnionBooleanType)  #combine all the dogbones into a single toolbody
                
        baseFeatures = rootComp.features.baseFeatures
        baseFeature = baseFeatures.add()
        baseFeature.startEdit()
        baseFeature.name = 'dogboneTool'

        dbB = rootComp.bRepBodies.add(toolBodies, baseFeature)
        dbB.name = 'dbHole'
        baseFeature.finishEdit()
        baseFeature.name = 'dbBaseFeat'
        
        targetBody = edge_list[0].entity.body
        toolCollection.add(baseFeature.bodies.item(0))
                    
        combineInput = rootComp.features.combineFeatures.createInput(targetBody, toolCollection)
        combineInput.isKeepToolBodies = False
        combineInput.isNewComponent = False
        combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        combine = rootComp.features.combineFeatures.add(combineInput)
        combine.name = 'dbCombine'
                                
    adsk.doEvents()
    
    if errorCount >0:
        util.messageBox('Reported errors:{}\nYou may not need to do anything, \nbut check holes have been created'.format(errorCount))
