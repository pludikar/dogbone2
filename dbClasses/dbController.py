import logging
from pprint import pformat
import adsk.core, adsk.fusion

from sys import getrefcount as grc

from functools import reduce, lru_cache

from ..common import dbutils as dbUtils, common as g
from .register import Register
from .dbFace import DbFace
from .dataclasses import DbParams
from .exceptionclasses import NoEdgesToProcess, EdgeNotRegistered, FaceNotRegistered

logger = logging.getLogger('dogbone.dbController')


class DbController:
    '''
    Responsible for performing series of macro level operations on Entities (dbFace and dbEdge)
    '''

    register = Register()

    def __init__(self):
        pass

    def selectFace(self, face):
        self.register.getobject(face).select()

    def deSelectFace(self, face):
        self.register.getobject(face).deselect()

    def deSelectAllFaces(self, face):
        pass

    def selectEdge(self,edge):
        try:
            edgeObject = self.register.getobject(edge)
            edgeObject.select()
            if edgeObject.parent not in self.register.selectedFacesAsList:
                edgeObject.parentObject.select()
        except EdgeNotRegistered:
            pass
        except FaceNotRegistered:
            pass


    def deSelectEdge(self,edge):
        edgeObject = self.register.getobject(edge)
        edgeObject.deselect()
        if not edgeObject.parentObject.hasEdges:
            edgeObject.parentObject.deselect()

    def selectAllFaces(self, face):
        faceList = self.register.registeredFacesByBodyAsList(face.body )
        for faceObject in faceList:
            faceObject.select()

    def registerAllFaces(self, faceEntity):
        faceEntities = dbUtils.getAllParallelFaces(faceEntity)
        for faceEntity in faceEntities:
            faceObj=DbFace(faceEntity)
            if not faceObj.hasEdges:
                continue
            # logger.debug(f'face being selected {faceObj}')
            # faceObj.select()

    def getDogboneTool(self, bodyEntity: adsk.fusion.BRepBody, params: DbParams = None):

        # toolCollection = adsk.core.ObjectCollection.create()
        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
        toolBodies = None

        representativeFaceObject = self.register.getobject(bodyEntity)

        for faceObj in self.register.selectedFacesByBodyAsList(representativeFaceObject.entity.body):
            if not faceObj.hasEdges:
                continue

            logger.debug(f'processing {faceObj} *****************')

            for edge in faceObj:
                if not edge.isselected:
                    continue
                dbToolBody = edge.getdbTool(params)
                if not toolBodies:
                    toolBodies = dbToolBody
                    continue
                tempBrepMgr.booleanOperation(
                    toolBodies,
                    dbToolBody,
                    adsk.fusion.BooleanTypes.UnionBooleanType)  #combine all the dogbones into a single toolbody

        if not toolBodies:
            raise NoEdgesToProcess('Empty Edge Collection')
        # baseFeatures = g._rootComp.features.baseFeatures
        # baseFeature = baseFeatures.add()
        # baseFeature.name = 'dogbone'

        # baseFeature.startEdit()
        # dbB = g._rootComp.bRepBodies.add(toolBodies, baseFeature)
        # dbB.name = 'dogboneTool'
        # baseFeature.finishEdit()

        # toolCollection.add(baseFeature.bodies.item(0))
        # targetBody = self.register.registeredFacesByBodyAsList(representativeFaceObject.body_token)[0].entity.body
        return toolBodies # toolCollection, targetBody
