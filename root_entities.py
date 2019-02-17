# -*- coding: utf-8 -*-
import logging
import adsk.core, adsk.fusion
import weakref

logger = logging.getLogger(__name__)

calcId = lambda x: str(x.tempId) + ":" + x.assemblyContext.name.split(":")[-1] if x.assemblyContext else str(x.tempId) + ":" + x.body.name


class RootBody():
    """
    Object keeping data for rootComponent Bodies
    """
    
    _faces = {}
    _topFace = None
    _bottomFace = None
    
    def __del__(self):
        for face in self._faces:
            del face
        
    
    def __init__(self, parent, body):
        logger.debug("adding rootBody")
        self._parent = weakref.ref(parent)
        self._entity = body
        self._isComponent = False
        self._id =  str(body.tempId) + ':' + body.name
        
    def addFace(self, face):
        if face.objectType != adsk.fusion.BRepFace.classType():
            return False
        newFaceObject = RootFace(self, face)
        self._faces[newFaceObject.faceId] = newFaceObject
        return newFaceObject
        
    @property
    def name(self):
        return self._name
        
    @property
    def isComponent(self):
        return self._isComponent
        
    @property
    def entity(self):
        return self._entity

    @property
    def faces(self):
        return self._faces

        
  
        
class RootFace:
    
    _edges = []
    _parent = None
    body = None
    entity = None
    faceId = None
    
    def __init__(self, parent, face):
        self._parent = weakref.ref(parent)
        self.body = parent._entity
        self.entity = face
        self.faceId = str(face.tempId) + ":" + face.body.name
        
    def __del__(self):
        for edge in self._edges:
            del edge

        
    def addEdge(self, edge):
        if edge.objectType != adsk.fusion.BRepEdge.classType():
            return False
        newEdge = RootEdge(self,edge)
        self.edges[newEdge.edgeId]
        return {self.faceId:newEdge}

        
class RootEdge:
    _parent = None
    edgeId = None
    
    def __init__(self, parent):
        self._parent = weakref.ref(parent)
        
    def __del__(self):
        pass
        
    def parent(self):
        print (self.parent)
        
