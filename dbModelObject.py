# -*- coding: utf-8 -*-
import adsk.core, adsk.fusion
import weakref
from . import component_entities, root_entities
import logging

logger = logging.getLogger(__name__)

calcId = lambda x: str(x.tempId) + ":" + x.assemblyContext.name.split(":")[-1] if x.assemblyContext else str(x.tempId) + ":" + x.body.name


#==============================================================================
# The idea here is to create an object (or a series of objects) that 
#==============================================================================


class Model:
    BodyObject = namedtuple('bodyObject', ['id', 'object']) #experimenting!
    
    _bodyObjects = {}
    
    def __del__(self):
        for body in self._bodyObjects:
            del body
            
    def isCandidate(self, entity):
        """
        Checks that the candidate entity passes the eligibility checks
        
        entity can be face or edge
    
        returns:
            TRUE if:
                entity is in same Occurrence and parallel to primeFace
                entity is in an occurrence that does not already have a primeFace
            
        returns:
            FALSE if:
                entity is in same Component but different Occurrence
                entity is not parallel to primeFace
                entity is on bottom face of body that has a primeFace
            
        """
        pass        
    
                    
    def remove(self, entity):
        """
        Removes specific entity from the model registry
        
        returns TRUE if successful
        """
        pass
    
    def removeAll(self, entity):
        """
        removes all similar entities
        if entity = edge then all edges belonging to same face are removed from the model registry
        if entity = face then all faces, and associated edges are removed from the model registry
        returns TRUE if successful
        """
        pass
    
    def add(self, entity):
        """
        adds specific entity to the model registry
        if entity = face then all associated edge candidates are calculated and added too
        if entity = edge then specific edge is added, if not registered already
        returns TRUE if successful
        """
        pass
    
    def addAll(self, face):
        """
        adds all faces of a body that are parallel to the face parameter, calculates and adds edge candidates
        returns TRUE if successful
        """
        pass
    
    def select(self, entity):
        """
        adds entity to registry if not already registered
        removes entity from registry if registered
        entity can be a face or edge
        when face, adds or removes all edges
        returns TRUE if successful
        """
        if (entity.objectType != adsk.fusion.BRepEdge.classType()) and (entity.objectType != adsk.fusion.BRepFace.classType()):
            return False
        body = entity.body
        if not self._bodyObjects.get(body, False):
            self.add(entity)  #entity can be added immediately, because its body isnt registered
            return True
            
        bodyObject = self._bodyObjects[body]
        if entity.objectType == adsk.fusion.BRepFace.classType():
            if bodyObject.isRegistered(entity):
                pass
        pass
    
    def selectAdd(self, entity):
        """
        adds entity to ui.activeSelections
        entity can be face or edge
        when face, adds all edges
        updates registry with all added entities
        returns TRUE if successful
        """
        pass

    
    def selectAll(self, face):
        """
        selects all faces, and associated edges to ui.activeSelections
        returns TRUE if successful
        """
        pass

    def deSelect(self, entity):
        """
        removes entity to ui.activeSelections
        entity can be face or edge
        when face, adds all edges
        returns TRUE if successful
        """
        pass
    
    def deSelectAll(self, face):
        """
        deSelects all faces related to same body, and associated edges to ui.activeSelections
        returns TRUE if successful
        """
        pass
    
    def syncSelection(self):
        """
        forces ui selections to become the same as the registered selections
        returns TRUE if successful
        """
        pass
        
    def addBody(self, body):
        if body.objectType != adsk.fusion.BRepBody.classType():
            return False
        newBody = CompBody(self, body) if body.assemblyContext else RootBody(self, body) #make the choice here to create component body or root body

        self._bodyObjects[newBody.id] = newBody
        return newBody
        
    def include(self, entity):
        if entity.objectType != adsk.fusion.BRepFace.classType() or entity.objectType != adsk.fusion.BRepEdge.classType:
            return False
        isComponent = entity.assemblyContext
        body  = entity.body
        bodyName = body.assemblyContext.name if isComponent else body.name
        try:        
            activeBody = self._bodyObjects[bodyName]
        except KeyError:
            activeBody = CompBody(self, body) if isComponent else RootBody(self, body)
            self._bodyObjects[newBody.name] = activeBody

        if entity.objectType == adsk.fusion.BRepFace.classType():
            activeFace = activeBody.include(entity)
            
            return
        
    @property    
    def bodies(self):
        return self._bodyObjects
        
    @property
    def entity(self):
        return self._entity
        
    @property
    def name(self):
        return self._name
 
 