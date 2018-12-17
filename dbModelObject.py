# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion
import weakref

import logging

logger = logging.getLogger(__name__)

calcId = lambda x: str(x.tempId) + ':' + x.assemblyContext.name.split(':')[-1] if x.assemblyContext else str(x.tempId) + ':' + x.body.name


class Model:
    
    _bodies = {}
    
    def __del__(self):
        for body in self._bodies:
            del body
        
    def addBody(self, body):
        if body.objectType != adsk.fusion.BRepBody.classType():
            return False
        newBody = CompBody(self, body) if body.assemblyContext else RootBody(self, body)

        self._bodies[newBody.name] = newBody
        return newBody
        
    def include(self, entity):
        if entity.objectType != adsk.fusion.BRepFace.classType() or entity.objectType != adsk.fusion.BRepEdge.classType:
            return False
        isComponent = entity.assemblyContext:
        body  = entity.body
        bodyName = body.assemblyContext name if isComponent else body.name
        try:        
            activeBody = self._bodies[bodyName]
        except KeyError:
            activeBody = CompBody(self, body) if isComponent else RootBody(self, body)
            self._bodies[newBody.name] = activeBody

        if entity.objectType == adsk.fusion.BRepFace.classType():
            activeFace = activeBody.include(entity)
            
            
            
            return
        
        
            
            
            
        
        
        
  @property    
    def bodies(self):
        return self._bodies
        
    @property
    def entity(self):
        return self._entity
        
    @property
    def name(self):
        return self._name
 
        
class RootBody():
    '''
    Object keeping data for rootComponent Bodies
    '''
    
    _faces = {}
    
    def __del__(self):
        for face in self._faces:
            del face
        
    
    def __init__(self, parent, body):
        logger.debug("adding rootBody")
        self._parent = weakref.ref(parent)
        self._entity = body
        self._isComponent = bool(body.assemblyContext) 
        self._name = body.name 
        
    def addFace(self, face):
        if face.objectType != adsk.fusion.BRepFace.classType():
            return False
        newFace = Face(self, face)
        self._faces[newFace.faceId] = newFace
        return newFace
        
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

        
  
        
class CompBody(RootBody):
    '''
    Object keeping data for Component Bodies
    '''
    

    
    def __init__(self, parent, body):
        super().__init__(parent, body)
        logger.debug("adding compBody")
        self.name = body.assemblyContext.name
        return


class Face:
    
    _edges = []
    _parent = None
    body = None
    entity = None
    faceId = None
    
    def __init__(self, parent, face):
        self._parent = weakref.ref(parent)
        self.body = parent._entity
        self.entity = face
        self.faceId = (str(face.tempId) + ":" + face.assemblyContext.name.split(':')[-1]) if parent.isComponent else (face.body.name)
        
    def __del__(self):
        for edge in self._edges:
            del edge

        
    def addEdge(self, edge):
        if edge.objectType != adsk.fusion.BRepEdge.classType():
            return False
        newEdge = Edge(self,edge)
        self.edges[newEdge.edgeId]
        return {self.faceId:newEdge}


class CompFace(Face):
    
    def __init__(self, parent, body):
        super().__init__(parent, body)
        pass
        
class Edge:
    _parent = None
    edgeId = None
    
    def __init__(self, parent):
        self._parent = weakref.ref(parent)
        
    def __del__(self):
        pass
        
    def parent(self):
        print (self.parent)
        
        
