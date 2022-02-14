import logging
from pprint import pformat
import adsk.core, adsk.fusion

from sys import getrefcount as grc

from functools import reduce, lru_cache

from ..common import dbutils as dbUtils, common as g
from .register import Register
from .dbFace import DbFace
from .dataclasses import DbParams

logger = logging.getLogger('dogbone.dbController')


class DbController:
    '''
    Responsible for performing series of macro level operations on Entities (dbFace and dbEdge)
    '''

    register = Register()

    def __init__(self):
        pass

    def selectFace(self, face):
        self.register.getObject(face).select()

    def deSelectFace(self, face):
        self.register.getObject(face).deselect()

    def deSelectAllFaces(self, face):
        pass

    def selectEdge(self,edge):
        self.register.getObject(edge).select()

    def deSelectEdge(self,edge):
        self.register.getObject(edge).deselect()

    def selectAllFaces(self, face):
        componentHash = dbUtils.get_component_hash(face)
        faceList = self.register.registeredObjectsByComponentAsList(DbFace, componentHash )
        for faceObject in faceList:
            faceObject.select()

    def registerAllFaces(self, faceEntity):
        faceEntities = dbUtils.getAllParallelFaces(faceEntity)
        for faceEntity in faceEntities:
            faceObj=DbFace(faceEntity)
            if not faceObj.hasEdges:
                continue
            logger.debug(f'face being selected {faceObj}')
            faceObj.select()

    def getDogboneTool(self, component: adsk.fusion.Component, params: DbParams = None):

        toolCollection = adsk.core.ObjectCollection.create()
        tempBrepMgr = adsk.fusion.TemporaryBRepManager.get()
        toolBodies = None

        for body in component.bRepBodies:

            body = self.register.getobject(body)
            if not body:
                continue

            for faceObj in self.register.registeredFacesByComponentAsList(component):
                if not faceObj.hasEdges:
                    continue

                logger.debug(f'processing {faceObj} *****************')

                for edge in faceObj:
                    dbToolBody = edge.getdbTool(params)
                    if not toolBodies:
                        toolBodies = dbToolBody
                        continue
                    tempBrepMgr.booleanOperation(
                        toolBodies,
                        dbToolBody,
                        adsk.fusion.BooleanTypes.UnionBooleanType)  #combine all the dogbones into a single toolbody

        baseFeatures = g._rootComp.features.baseFeatures
        baseFeature = baseFeatures.add()
        baseFeature.name = 'dogbone'

        baseFeature.startEdit()
        dbB = g._rootComp.bRepBodies.add(toolBodies, baseFeature)
        dbB.name = 'dogboneTool'
        baseFeature.finishEdit()

        toolCollection.add(baseFeature.bodies.item(0))
        targetBody = self.register.registeredFacesByComponentAsList(component)[0].entity.body
        return toolCollection, targetBody
