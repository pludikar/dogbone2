import logging
from pprint import pformat
import adsk.core, adsk.fusion

from sys import getrefcount as grc

from collections import defaultdict, namedtuple
from math import pi, tan

import traceback
import weakref
import json
from functools import reduce, lru_cache

from ..common import dbutils as dbUtils
# from . import dataclasses
from . import dbEdge, register
from math import sqrt, pi



class DbFaces:

    def __init__(self):
    #     self.group = weakref.ref(parent)()
    #     self.dbFaces = self.group.dbFaces
    #     self.dbEdges = self.group.dbEdges
        # self.faces = []
        self.registry = register.Register()
    def __iter__(self):
        for face in self.faces:
            yield face

    # def addAllFaces(self, face):
    #     body = face.body
    #     for face in body.faces:

    def addFace(self, face):
        DbFace(face)

    def addAllFaces(self, face):
        faceList = dbUtils.getAllFaces(face)
        for face in faceList:
            DbFace(face)

class DbFace:
    """
    This class manages a single dogbone Face:
    keeps and makes a record of the viable edges, whether selected or not
    principle of operation: the first face added to a body/occurrence entity will find all other same facing faces, automatically finding eligible edges - they will all be selected by default.
    edges and faces have to be selected to be selected in the UI
    when all edges of a face have been deselected, the face becomes deselected
    when all faces of a body/entity have been deselected - the occurrence and all associated face and edge objects will be deleted and GC'd  (in theory)
    manages edges:
        edges can be selected or deselected individually
        faces can be selected or deselected individually
        first face selection will cause all other appropriate faces and corresponding edges on the body to be selected
        validEdges dict makes lists of candidate edges available
        each face or edge selection that is changed will reflect in the parent management object selectedOccurrences, selectedFaces and selectedEdges
    """

    def __init__(self, face):  #preload is used when faces are created from attributes.  preload will be a namedtuple of faceHash and occHash
        self.logger = logging.getLogger('dogbone.mgr.edge')

        self.logger.info('---------------------------------{}---------------------------'.format('creating face'))
        
        register.FaceObject(self)

        self.entity = face

        self.faceNormal = dbUtils.getFaceNormal(self.face)
        
        self.faceHash = hash(face.entityToken)

        self._selected = True # record of all valid faces are kept, but only ones that are selected==True are processed for dogbones???

        self.occurrence = face.assemblyContext if face.assemblyContext else None

        self.occurrenceHash = hash(face.assemblyContext.entityToken) if face.assemblyContext else face.body.entityToken
        
        self.topFacePlane, self.topFacePlaneHash = dbUtils.getTopFacePlane(face)
        
        self.logger.debug('{} - face initiated'.format(self.faceHash))           

        #==============================================================================
        #             this is where inside corner edges, dropping down from the face are processed
        #==============================================================================
        
        self.brepEdges = dbUtils.findInnerCorners(face) #get all candidate edges associated with this face
        if not self.brepEdges:
            self.logger.debug('no edges found on selected face '.format(self.faceHash))
            self._selected = False
            return

        self.logger.debug('{} - edges found on face creation'.format(len(self.brepEdges)))
        for edge in self.brepEdges:
            if edge.isDegenerate:
                continue
            try:
                dbEdge.DbEdge(edge, self) #create a new edgeObject
                self.logger.debug(' {} - edge object added'.format(edgeObject.edgeHash))
    
            except:
                dbUtils.messageBox('Failed at edge:\n{}'.format(traceback.format_exc()))

        self.logger.debug('registered component count = {}'.format(len(self.parent.registeredFaces.keys())))

    def __hash__(self):
        return self.faceHash
                
    def __del__(self):
        self.logger.debug("face {} deleted".format(self.faceHash))
        register.remove(self)
        self.logger.debug('registered Faces count = {}'.format(len(self.registeredFaces)))               
        self.logger.debug('selected Faces count = {}'.format(len(self.selectedFaces)))               
        self.logger.debug('registered edges count = {}'.format(len(self.registeredEdges)))               
        self.logger.debug('selected edges count = {}'.format(len(self.selectededEdges)))

    @property
    def entity(self):
        return self.entity
        
    def refreshAttributes(self):
        self.face.attributes.add(DBGROUP, 'faceId:'+self.faceHash, json.dumps(list(self.registeredEdges.keys())) if self.selected else '')
        for edgeObject in self.registeredEdges.values():
            edgeObject.refreshAttributes()

    def getAttributeValue(self):
        return self.face.attributes.itemByName(DBGROUP, 'faceId:'+self.occurrenceHash).value

    def setAttributeValue(self):
        
        self.face.attributes.add(DBGROUP, 'faceId:'+self.occurrenceHash, value)

    @property
    def entity(self):
        return self.entity

    @property
    def selected(self):
        return self._selected
        
    @selected.setter
    def selected(self, selected):  #property setter only accepts a single argument - so multiple argments are passed via a tuple - which if exists, will carry allEdges and selected flags separately
        allEdges = True
        if isinstance(selected, tuple):
            allEdges = selected[1]
            selected = selected[0]
        self._selected = selected
        if not selected:
            del self.selectedFaces[self.faceHash]
            attr = self.face.attributes.itemByName(DBGROUP, DBFACE_SELECTED).deleteMe()

            self.logger.debug(' {} - face object removed from selectedFaces'.format(self.faceHash))
        else:
            self.selectedFaces[self.faceHash] = self
            #   attr = self.face.attributes.add(DBGROUP, DBFACE_SELECTED, dbType)
            self.logger.debug(' {} - face object added to registeredFaces'.format(self.faceHash))

        if allEdges:
            self.logger.debug('{} all edges after face {}'.format('Selecting' if selected else 'Deselecting', 'Selected' if selected else 'Deselected'))
            for edge in self.registeredEdges.values():
                try:
                    edge.selected = selected
                except:
                    continue
            self.logger.debug(' {} - edge object {}'.format(edge.edgeHash, 'selected' if selected else 'deselected'))
        self._selected = selected