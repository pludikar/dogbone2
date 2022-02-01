import logging
from pprint import pformat
import adsk.core, adsk.fusion

from sys import getrefcount as grc

from functools import reduce, lru_cache

from ..common import dbutils as dbUtils, decorators as d
from math import sqrt, pi
from .register import Register
from .dbFace import DbFace
from .dbEdge import DbEdge

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

    def registerAllFaces(self, face):
        faceList = dbUtils.getAllParallelFaces(face)
        for face in faceList:
            face=DbFace(face)
            face.select()