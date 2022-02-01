import logging
from functools import reduce, lru_cache
from typing import List
from xml.dom.minidom import Attr
import adsk.core, adsk.fusion
from ..common import dbutils as u
from ..common.decorators import tokeniseEntity

app = adsk.core.Application.get()
ui = app.userInterface
product = app.activeProduct
design: adsk.fusion.Design = product

logger = logging.getLogger('dogbone.register')

class Register:

    registerList: List = []

    def __init__(self):
        pass

    def add(self, entity_object):
        Register.registerList.append(entity_object)       

    @tokeniseEntity
    def remove(self, objectHash:int)->None:
        try:
            Register.registerList.remove(objectHash)
        except ValueError:
            return False

    @lru_cache(maxsize=128)
    def getobject(self, dbobject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        return  Register.registerList[dbobject]

    
    @lru_cache(maxsize=128)
    def isSelected(self, dbobject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        return  Register.registerList[dbobject].isSelected
   
    
    @lru_cache(maxsize=128)
    def isSelectable(self, dbobject:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        if not len(Register.registerList):
            return True
        return  Register.registerList[dbobject]
  
    
    @tokeniseEntity
    @lru_cache(maxsize=128)
    def isEntitySelectable(self, objectToken:object)->object:  #needs hashable parameters in the arguments for lru_cache to work
        '''
        Checks if an entity is selectable - should return True is entity is already registered
        '''
        objectHash = hash(objectToken)
        component_hash = u.get_component_hash(objectToken)

        if not self.isOccurrenceRegistered(component_hash):
            return True
        result = objectHash in Register.registerList
        return  result
        
    
    def registeredObjectsAsList(self, cls: object )->List[object]:
        '''
        returns full list of objects filtered by type (dbFace or dbEdge) 
        '''
        return [obj for obj in Register.registerList if isinstance(obj, cls)]

    @tokeniseEntity
    def selectedObjectsByComponentAsList(self, cls: object, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if isinstance(obj, cls) and obj.component_hash == component_hash ]
    
    @tokeniseEntity
    def registeredObjectsByComponentAsList(self, cls: object, component_hash: int )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and component_hash 
        '''
        return [obj for obj in Register.registerList if isinstance(obj, cls) and obj.component_hash == component_hash ]

    @tokeniseEntity
    @lru_cache(maxsize=128)
    def registeredObjectsByParentAsList(self, cls: object, parentToken: object )->List[object]:
        '''
        returns list of objects filtered by type (dbFace or dbEdge) and parent
        is Only applicable to cls = DbEdge 
        '''
        #ideally should have been filtered by DbEdge, but that makes Register more coupled than I wanted
        objList = []
        fullOjectList = [obj for obj in Register.registerList if isinstance(obj, cls)]
        for obj in fullOjectList:
            try:
                # if obj doesn't have a parent attribute - will throw an error (ie it's an edge!)
                if obj.parent._hash == hash(parentToken):  
                    objList.append(obj)
            except AttributeError:
                continue
        return objList
    
    @property
    def registeredEntitiesAsList(self)->List[adsk.fusion.BRepFace]:
        '''
        Returns a full list of entities (BrepFaces and BrepEdges) that have been registered
        '''
        return [x.entity for x in Register.registerList]
    
    def selectedObjectsAsList(self, cls: object):
        return [obj for obj in Register.registerList if isinstance(obj, cls) and obj.isselected]
    
    @property
    def registeredOccurrenceHashesAsList(self):
        '''
        Returns a list of unique Occurrence hashes 
        '''
        return list(set([obj.component_hash for obj in self.registerList]))
   
    @tokeniseEntity
    @lru_cache(maxsize=128)
    def isOccurrenceRegistered(self, component_hash)->bool:
        '''
        Returns if an entity has been registered 
        '''
        return component_hash in list(set(obj.component_hash for obj in self.registerList))